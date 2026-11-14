#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { load as loadYaml } from 'js-yaml';
import { parse as parseToml } from 'smol-toml';
import { generatedFiles, isMapping, listFiles, readFrontmatter } from './ai-workflow-files.ts';

function mapping(value: unknown): Record<string, unknown> | undefined {
  return isMapping(value) ? value : undefined;
}

function array(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

export function validateWorkflow(root: string) {
  const errors: string[] = [];
  const check = (condition: boolean, message: string) => {
    if (!condition) errors.push(message);
  };
  const read = (relative: string) => fs.readFileSync(path.join(root, relative), 'utf8');
  const expected = generatedFiles(root);
  for (const [relative, content] of expected) {
    check(
      fs.existsSync(path.join(root, relative)) && fs.readFileSync(path.join(root, relative)).equals(typeof content === 'string' ? Buffer.from(content) : content),
      `Generated file missing or drifted: ${relative}; run yarn ai-workflow:sync`,
    );
  }
  for (const directory of ['.claude/skills', '.claude/agents', '.codex/agents']) {
    for (const relative of listFiles(path.join(root, directory))) {
      const target = path.posix.join(directory, relative);
      check(expected.has(target), `Obsolete generated file: ${target}`);
    }
  }
  check(!fs.existsSync(path.join(root, '.codex/skills')), 'Duplicate skill root: .codex/skills; use .agents/skills');

  let skills = 0;
  for (const relative of listFiles(path.join(root, '.agents/skills'))) {
    if (path.basename(relative) !== 'SKILL.md') continue;
    skills += 1;
    const file = path.join('.agents/skills', relative);
    const { metadata, body } = readFrontmatter(read(file), file);
    check(metadata.name === path.basename(path.dirname(file)), `Skill name does not match directory: ${file}`);
    check(typeof metadata.description === 'string' && metadata.description.trim().length > 0, `Missing skill description: ${file}`);
    check(body.length > 0, `Empty skill: ${file}`);
    check(!('model' in metadata) && !('effort' in metadata), `Skills must use runtime model settings: ${file}`);
    if (metadata['disable-model-invocation'] === true) {
      const policyFile = path.join(path.dirname(file), 'agents/openai.yaml');
      const policyDocument = fs.existsSync(path.join(root, policyFile)) ? mapping(loadYaml(read(policyFile))) : undefined;
      check(mapping(policyDocument?.policy)?.allow_implicit_invocation === false, `Manual skill needs Codex invocation policy: ${policyFile}`);
    }
    check(!/\.(?:codex|claude)\/skills\//.test(body), `Skill must reference canonical source paths: ${file}`);
  }

  const agents = mapping(parseToml(read('.codex/config.toml')).agents) ?? {};
  const maxThreads = agents.max_concurrent_threads_per_session;
  check(typeof maxThreads === 'number' && Number.isInteger(maxThreads) && maxThreads > 0, 'Codex needs a positive max_concurrent_threads_per_session');
  check(!('max_threads' in agents), 'Use the current Codex concurrency setting instead of max_threads');
  check(
    !Object.values(agents).some((value) => value && typeof value === 'object' && 'config_file' in value),
    'Use standalone Codex agent definitions instead of legacy config_file registrations',
  );
  let roles = 0;
  for (const [relative, content] of expected) {
    if (relative.startsWith('.codex/agents/')) {
      roles += 1;
      const agent = parseToml(content.toString());
      check(
        agent.name === path.basename(relative, '.toml') && typeof agent.description === 'string' && typeof agent.developer_instructions === 'string',
        `Invalid standalone Codex agent: ${relative}`,
      );
      check(!('model' in agent) && !('model_reasoning_effort' in agent), `Codex agents must inherit model settings: ${relative}`);
    } else if (relative.startsWith('.claude/agents/')) {
      const { metadata } = readFrontmatter(content.toString(), relative);
      check(!('model' in metadata) && !('effort' in metadata), `Agents must use runtime model settings: ${relative}`);
    }
  }

  const entries = [
    ['.codex', 'hooks.json', 'PostToolUse', 'bash "$(git rev-parse --show-toplevel)/.codex/hooks/format.sh"'],
    ['.claude', 'settings.json', 'PostToolUse', '"$CLAUDE_PROJECT_DIR"/.claude/hooks/format.sh'],
  ];
  const wrapper = '#!/bin/bash\n\nrepo_root="$(cd "$(dirname "$0")/../.." && pwd -P)" || exit 1\nexec node "$repo_root/scripts/agent-hooks/format.ts"\n';
  for (const [harness, filename, event, command] of entries) {
    const entry = `${harness}/${filename}`;
    const parsed: unknown = JSON.parse(read(entry));
    const document = mapping(parsed);
    const hooks = mapping(document?.hooks);
    check(hooks !== undefined && Object.keys(hooks).length === 1 && event in hooks, `Only lightweight edit hooks belong in ${entry}; no Stop or automatic install hooks`);
    const groups = array(hooks?.[event]);
    check(groups?.length === 1, `Expected one edit hook group in ${entry}`);
    if (!groups) continue;
    for (const value of groups) {
      const group = mapping(value);
      if (harness === '.codex') check(group?.matcher === 'apply_patch', 'Codex edit hook must match apply_patch');
      if (harness === '.claude') check(group?.matcher === 'Edit|Write|MultiEdit', 'Claude edit hook must match supported edit tools');
      const handlers = array(group?.hooks);
      check(handlers?.length === 1, `Expected one formatter handler in ${entry}`);
      if (!handlers) continue;
      for (const value of handlers) {
        const handler = mapping(value);
        check(handler?.command === command, `Hook must call only its formatter wrapper: ${entry}`);
        check(handler?.type === 'command' && handler.timeout === 10, `Invalid formatter handler schema: ${entry}`);
      }
    }
    check(listFiles(path.join(root, harness, 'hooks')).join(',') === 'format.sh', `Unexpected lifecycle wrapper in ${harness}/hooks`);
    check(read(`${harness}/hooks/format.sh`).replace(/\r\n/g, '\n') === wrapper, `Formatter wrapper must contain only the shared formatter invocation: ${harness}`);
  }
  check(read('CLAUDE.md').trim() === '@AGENTS.md', 'CLAUDE.md should import the shared root policy');
  return { errors, skills, roles, generated: expected.size };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
    const result = validateWorkflow(root);
    for (const error of result.errors) console.error(error);
    console.log(`AI workflow: ${result.skills} shared skills, ${result.roles} roles, ${result.generated} generated files; ${result.errors.length} error(s).`);
    process.exitCode = result.errors.length ? 1 : 0;
  } catch (error) {
    console.error(`AI workflow validation failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}

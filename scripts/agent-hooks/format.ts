#!/usr/bin/env node

import type { SpawnSyncOptionsWithStringEncoding } from 'node:child_process';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type crossSpawn from 'cross-spawn';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(import.meta.url);
const editTools = new Set(['Edit', 'Write', 'MultiEdit', 'apply_patch']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

export function editedPaths(payload: unknown): string[] {
  if (!isRecord(payload)) return [];
  const { hook_event_name: event, tool_name: tool, tool_input, tool_response, file_path } = payload;
  if (event && event !== 'PostToolUse') return [];
  if (tool && (typeof tool !== 'string' || !editTools.has(tool))) return [];
  if (isRecord(tool_response) && (tool_response.isError === true || tool_response.success === false)) return [];

  const input = isRecord(tool_input) ? tool_input : undefined;
  if (tool !== 'apply_patch') {
    const filePath = input?.file_path ?? file_path;
    if (typeof filePath === 'string') return [filePath];
  }
  if (tool && tool !== 'apply_patch') return [];
  if (typeof input?.command !== 'string') return [];

  const lines = input.command.trim().split(/\r?\n/);
  if (lines[0] !== '*** Begin Patch' || lines.at(-1) !== '*** End Patch') return [];

  const paths = [];
  let pendingPath: string | undefined;
  for (const line of lines.slice(1, -1)) {
    const file = /^\*\*\* (Add|Update|Delete) File: (.+)$/.exec(line);
    if (file) {
      if (pendingPath) paths.push(pendingPath);
      pendingPath = file[1] === 'Delete' ? undefined : file[2];
    } else if (line.startsWith('*** Move to: ') && pendingPath) {
      pendingPath = line.slice('*** Move to: '.length);
    }
  }
  if (pendingPath) paths.push(pendingPath);
  return paths;
}

function isInside(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative !== '' && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export function formattingPaths(payload: unknown, root = repoRoot): string[] {
  const realRoot = realpathSync(root);
  const cwd = isRecord(payload) ? payload.cwd : undefined;
  const editCwd = typeof cwd === 'string' && path.isAbsolute(cwd) ? cwd : root;
  const files = new Set<string>();
  for (const candidate of editedPaths(payload)) {
    if (!candidate || candidate.includes('\0') || !/\.(?:[cm]?js|jsx|[cm]?ts|tsx)$/.test(candidate)) continue;
    const absolute = path.resolve(editCwd, candidate);
    if (!isInside(path.resolve(root), absolute)) continue;
    try {
      // Resolve the final file too: a symlink in the repo may point outside it.
      const realFile = realpathSync(absolute);
      if (isInside(realRoot, realFile) && statSync(realFile).isFile()) files.add(realFile);
    } catch {
      // Deleted files and paths that do not exist are irrelevant to formatting.
    }
  }
  return [...files];
}

type FormatCommand = (executable: string, args: string[], options: SpawnSyncOptionsWithStringEncoding) => { status: number | null; error?: Error; stderr?: string };

export function formatEditedFiles(payload: unknown, root = repoRoot, run?: FormatCommand): void {
  const files = formattingPaths(payload, root);
  if (!files.length || !existsSync(path.join(root, 'node_modules/oxfmt/package.json'))) return;

  // Load only after the no-op checks, so a fresh checkout needs no dependencies.
  const spawnSync = run ?? (require('cross-spawn') as typeof crossSpawn).sync;
  const result = spawnSync('corepack', ['yarn', 'exec', 'oxfmt', '--write', ...files], {
    cwd: root,
    encoding: 'utf8',
    // Formatting must not bootstrap package managers or download dependencies.
    env: { ...process.env, COREPACK_ENABLE_NETWORK: '0' },
    stdio: ['ignore', 'ignore', 'pipe'],
    timeout: 8000,
  });
  if (result.error || result.status !== 0) {
    console.error(`[agent format] Formatting failed: ${result.error?.message || result.stderr?.trim() || `exit ${result.status}`}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let payload: unknown;
  try {
    payload = JSON.parse(readFileSync(0, 'utf8'));
  } catch {
    // Malformed or unknown hook input must not trigger work.
  }
  if (payload) formatEditedFiles(payload);
}

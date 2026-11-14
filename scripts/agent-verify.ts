#!/usr/bin/env node

import { spawnSync, type ChildProcess } from 'node:child_process';
import spawn from 'cross-spawn';
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, rmdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { constants, tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Every checkout uses the same slot; this is deliberately outside the repo.
export const verificationLockPath = path.join(tmpdir(), 'modelswarm-agent-verify.lock');
const workflowPaths = [
  '.agents/',
  '.claude/',
  '.codex/',
  'scripts/agent-hooks/',
  'scripts/ai-workflow-files.ts',
  'scripts/sync-ai-workflow.mjs',
  'scripts/sync-ai-workflow.ts',
  'scripts/validate-ai-workflow.ts',
  'CLAUDE.md',
];
const signalExitCode = (signal: NodeJS.Signals) => 128 + (constants.signals[signal] || 1);

type Command = [executable: string, ...args: string[]];
type VerificationCommand = Command | { command: Command; advisory?: boolean };

export interface VerificationOptions {
  cwd?: string;
  lockPath?: string;
  commands?: VerificationCommand[];
  log?: (message: string) => void;
  error?: (message: string) => void;
}

function hasErrorCode(error: unknown, code: string): boolean {
  return error instanceof Error && 'code' in error && error.code === code;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// Staged, unstaged, untracked, and committed-since-master paths. Returns undefined when Git
// cannot answer, so callers run the check instead of silently skipping it.
export function changedFiles(cwd: string): string[] | undefined {
  const git = (...args: string[]) => spawnSync('git', args, { cwd, encoding: 'utf8' });
  const lists = [
    ['diff', '--name-only', '--no-renames', '-z', '--cached'],
    ['diff', '--name-only', '--no-renames', '-z'],
    ['ls-files', '--others', '--exclude-standard', '-z'],
  ];
  const base = ['origin/master', 'master'].map((ref) => git('merge-base', ref, 'HEAD')).find((result) => result.status === 0);
  if (base) lists.push(['diff', '--name-only', '--no-renames', '-z', base.stdout.trim(), 'HEAD']);
  const files = new Set<string>();
  for (const args of lists) {
    const result = git(...args);
    if (result.error || result.status !== 0) return undefined;
    for (const file of result.stdout.split('\0')) if (file) files.add(file);
  }
  return [...files];
}

export function defaultCommands(cwd = repoRoot): VerificationCommand[] {
  const yarn = (...args: string[]): Command => ['corepack', 'yarn', ...args];
  const commands: VerificationCommand[] = [yarn('lint'), yarn('type-check'), yarn('build')];
  const files = changedFiles(cwd);
  if (!files || files.some((file) => workflowPaths.some((prefix) => file.startsWith(prefix)))) commands.push(yarn('ai-workflow:check'));
  // Knip reports unused files and dependencies for review; its findings never fail verification.
  commands.push({ command: yarn('knip'), advisory: true });
  return commands;
}

function acquireLock(lockPath: string, cwd: string): () => void {
  try {
    mkdirSync(lockPath, { mode: 0o700 });
  } catch (error) {
    if (!hasErrorCode(error, 'EEXIST')) throw error;
    let owner = 'owner details unavailable';
    try {
      const details: unknown = JSON.parse(readFileSync(path.join(lockPath, 'owner.json'), 'utf8'));
      if (
        details &&
        typeof details === 'object' &&
        'pid' in details &&
        typeof details.pid === 'number' &&
        'cwd' in details &&
        typeof details.cwd === 'string' &&
        'startedAt' in details &&
        typeof details.startedAt === 'string'
      ) {
        owner = `PID ${details.pid}, ${details.cwd}, started ${details.startedAt}`;
      }
    } catch {
      // A concurrent owner may still be writing its metadata. Do not steal it.
    }
    throw Object.assign(new Error(`Verification slot busy (${owner}). Lock: ${lockPath}. Retry after that run finishes; inspect stale locks before removing them.`), {
      code: 'LOCK_BUSY',
    });
  }

  const ownerPath = path.join(lockPath, 'owner.json');
  const token = randomUUID();
  try {
    writeFileSync(ownerPath, JSON.stringify({ pid: process.pid, cwd, startedAt: new Date().toISOString(), token }), { flag: 'wx' });
  } catch (error) {
    rmdirSync(lockPath);
    throw error;
  }
  return () => {
    // Never remove a lock that has been replaced by another invocation.
    const details: unknown = JSON.parse(readFileSync(ownerPath, 'utf8'));
    if (!details || typeof details !== 'object' || !('token' in details) || details.token !== token) {
      throw new Error(`Verification lock ownership changed: ${lockPath}`);
    }
    unlinkSync(ownerPath);
    rmdirSync(lockPath);
  };
}

export async function runVerification({
  cwd = repoRoot,
  lockPath = verificationLockPath,
  commands = defaultCommands(cwd),
  log = console.log,
  error = console.error,
}: VerificationOptions = {}): Promise<number> {
  let release: () => void;
  try {
    release = acquireLock(lockPath, cwd);
  } catch (failure) {
    error(`[agent verify] ${errorMessage(failure)}`);
    return hasErrorCode(failure, 'LOCK_BUSY') ? 75 : 1;
  }

  let child: ChildProcess | undefined;
  let interrupted: NodeJS.Signals | undefined;
  let exitCode = 0;
  const failures: string[] = [];
  const forwardSignal = (signal: NodeJS.Signals) => {
    interrupted = signal;
    if (!child?.pid) return;
    try {
      if (process.platform === 'win32') {
        const result = spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
        if (result.error || result.status !== 0) error(`[agent verify] Could not terminate command tree for PID ${child.pid}`);
      } else process.kill(-child.pid, signal);
    } catch (failure) {
      if (!hasErrorCode(failure, 'ESRCH')) error(`[agent verify] Could not forward ${signal}: ${errorMessage(failure)}`);
    }
  };
  const onInterrupt = () => forwardSignal('SIGINT');
  const onTerminate = () => forwardSignal('SIGTERM');
  process.on('SIGINT', onInterrupt);
  process.on('SIGTERM', onTerminate);

  try {
    for (const entry of commands) {
      if (interrupted) break;
      const { command, advisory = false } = Array.isArray(entry) ? { command: entry } : entry;
      const label = command.join(' ');
      log(`[agent verify] ${label} (${cwd})`);
      const [executable, ...args] = command;
      const result = await new Promise<{ code: number; detail: string }>((resolve) => {
        child = spawn(executable, args, { cwd, stdio: 'inherit', detached: process.platform !== 'win32' });
        child.on('error', (failure) => resolve({ code: hasErrorCode(failure, 'ENOENT') ? 127 : 1, detail: failure.message }));
        child.on('close', (code, signal) => resolve({ code: signal ? signalExitCode(signal) : (code ?? 1), detail: signal ? `signal ${signal}` : `exit ${code}` }));
      });
      child = undefined;
      if (result.code !== 0 && advisory) {
        log(`[agent verify] Advisory: ${label}: ${result.detail}; review relevant new findings.`);
      } else if (result.code !== 0) {
        exitCode ||= result.code;
        failures.push(`${label}: ${result.detail}`);
        error(`[agent verify] Failed: ${failures.at(-1)}`);
      }
    }
  } catch (failure) {
    error(`[agent verify] ${errorMessage(failure)}`);
    exitCode ||= 1;
  } finally {
    process.off('SIGINT', onInterrupt);
    process.off('SIGTERM', onTerminate);
    try {
      release();
    } catch (failure) {
      error(`[agent verify] Could not release lock: ${errorMessage(failure)}`);
      exitCode ||= 1;
    }
  }

  if (interrupted) return signalExitCode(interrupted);
  if (failures.length) error(`[agent verify] ${failures.length} check(s) failed; returning exit ${exitCode}.`);
  else if (exitCode === 0) log('[agent verify] Required checks passed.');
  return exitCode;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await runVerification();
}

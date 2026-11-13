#!/usr/bin/env node

import { spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const repoRoot = path.resolve(__dirname, '..');
export const isWindows = process.platform === 'win32';

function checkPort(port: number): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    const server = net.createServer();

    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port);
  });
}

export async function resolvePort(requestedPort: number) {
  let port = requestedPort;

  while (!(await checkPort(port))) {
    port += 1;
  }

  return port;
}

export async function waitForPort(host: string, port: number, timeoutMs = 30_000) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const ready = await new Promise<boolean>((resolve) => {
      const socket = net.connect({ host, port });

      socket.once('connect', () => {
        socket.destroy();
        resolve(true);
      });
      socket.once('error', () => resolve(false));
    });

    if (ready) {
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  throw new Error(`Timed out waiting for dev server on http://${host}:${port}`);
}

export function startVite(host: string, port: number) {
  const child = spawn('corepack', ['yarn', 'exec', 'vite', '--host', host, '--port', String(port), '--strictPort'], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PORTLESS: '0',
    },
    stdio: 'inherit',
  });

  const forwardSignal = (signal: NodeJS.Signals) => {
    if (!child.killed) {
      child.kill(signal);
    }
  };

  const onSigint = () => forwardSignal('SIGINT');
  const onSigterm = () => forwardSignal('SIGTERM');

  process.on('SIGINT', onSigint);
  process.on('SIGTERM', onSigterm);

  child.on('exit', (code, signal) => {
    process.off('SIGINT', onSigint);
    process.off('SIGTERM', onSigterm);

    if (signal) {
      process.kill(process.pid, signal);
      return;
    }

    process.exit(code ?? 0);
  });

  return child;
}

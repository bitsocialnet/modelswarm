import { execFileSync } from 'node:child_process';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The commit the footer links to: Vercel's for its builds, the checkout's locally, empty outside Git.
const commitRef = (() => {
  if (process.env.VERCEL_GIT_COMMIT_SHA) return process.env.VERCEL_GIT_COMMIT_SHA;
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
})();

export default defineConfig({
  // Relative asset paths so the static build also works from an IPFS gateway path.
  base: './',
  plugins: [react()],
  server: {
    port: 5191,
  },
  build: {
    outDir: 'build',
    emptyOutDir: true,
  },
  define: {
    'import.meta.env.VITE_COMMIT_REF': JSON.stringify(commitRef),
  },
  optimizeDeps: {
    // The dev-only inspectors in src/lib/dev-tools.ts. Discovered late, they were bundled in a second
    // optimizer pass with their own copy of React, which broke Agentation with an invalid hook call (seen in WeTube).
    include: ['react', 'react-dom/client', 'agentation', 'element-source'],
  },
});

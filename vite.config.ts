import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

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
  optimizeDeps: {
    // The dev-only inspectors in src/lib/dev-tools.ts. Discovered late, they were bundled in a second
    // optimizer pass with their own copy of React, which broke Agentation with an invalid hook call (seen in WeTube).
    include: ['react', 'react-dom/client', 'agentation', 'element-source'],
  },
});

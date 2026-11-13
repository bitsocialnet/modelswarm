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
});

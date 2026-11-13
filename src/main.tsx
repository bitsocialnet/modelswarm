import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { App } from './app';

// Development inspectors (Agentation, element-source); the guarded import is dropped from production builds.
if (import.meta.env.DEV) void import('./lib/dev-tools');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

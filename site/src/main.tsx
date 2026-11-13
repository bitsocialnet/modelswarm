import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { App } from './app';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

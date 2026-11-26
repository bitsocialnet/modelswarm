import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { Logo } from './components/logo/logo';
import { doc } from './data/content';
import { Footer } from './sections/footer';
import release from './data/demo-release.json';
import styles from './release.module.css';

const upstream = 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67';
const command = `cli/.venv/bin/modelswarm pull '${release.release_uri}' \\
  --peer ${release.peer} --no-discovery --timeout 900`;

function Release() {
  const [copyStatus, setCopyStatus] = useState('');

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(command);
      setCopyStatus('Command copied.');
    } catch {
      setCopyStatus('Copy failed. Select the command to copy it manually.');
    }
  }

  return (
    <>
      <a className='skip' href='#main'>
        Skip to content
      </a>
      <header className={styles.header}>
        <div className='wrap'>
          <a className={styles.brand} href='./'>
            <Logo size={30} />
            ModelSwarm
          </a>
        </div>
      </header>
      <main className={`wrap ${styles.main}`} id='main'>
        <header className={styles.intro}>
          <p className={styles.series}>Signed demo release · Q4_K_M</p>
          <h1>Qwen2.5-0.5B-Instruct</h1>
          <p>
            Qwen's 0.5B-parameter instruction-tuned language model, quantized to Q4_K_M for local inference. This release pairs the original GGUF with its Apache-2.0
            license.
          </p>
          <a href={upstream}>Upstream model card</a>
        </header>
        <dl className={styles.metadata}>
          <div>
            <dt>Format</dt>
            <dd>GGUF</dd>
          </div>
          <div>
            <dt>Download</dt>
            <dd>491 MB</dd>
          </div>
          <div>
            <dt>License</dt>
            <dd>Apache-2.0</dd>
          </div>
        </dl>
        <section className={styles.section} aria-labelledby='download'>
          <h2 id='download'>Download from the swarm</h2>
          <p>
            Set up the CLI, Node bridge and your own reader node using the <a href={doc('cli/demo/README.md#pull-from-the-public-seeder')}>signed demo instructions</a>.
            Then run this command using that node's RPC connection. The CLI verifies the signed announcement and prints the local snapshot path.
          </p>
          <pre aria-label='Signed release pull command'>
            <code>{command}</code>
          </pre>
          <div className={styles.copy}>
            <button type='button' className='button' onClick={() => void copyCommand()}>
              Copy command
            </button>
            <span role='status'>{copyStatus}</span>
          </div>
          <p>
            Want to try the CLI without a reader node? <a href={doc('README.md#getting-started')}>Use the HTTP quickstart</a>.
          </p>
        </section>
        <section className={styles.section} aria-labelledby='files'>
          <h2 id='files'>Files</h2>
          <ul className={styles.files}>
            {release.files.map((file) => (
              <li key={file.path}>
                <span>{file.path}</span>
                <span>{file.size.toLocaleString('en-US')} bytes</span>
              </li>
            ))}
          </ul>
        </section>
        <section className={styles.section} aria-labelledby='publisher'>
          <h2 id='publisher'>Publisher</h2>
          <p>ModelSwarm's demo publisher signed this release of Qwen's original files.</p>
          <dl className={styles.identifiers}>
            <div>
              <dt>Signing key</dt>
              <dd>
                <code>{release.publisher}</code>
              </dd>
            </div>
            <div>
              <dt>Release CID</dt>
              <dd>
                <code>{release.release_cid}</code>
              </dd>
            </div>
            <div>
              <dt>Manifest</dt>
              <dd>
                <a href='./demo/qwen-signed-manifest.json'>View release manifest</a>
              </dd>
            </div>
            <div>
              <dt>BitTorrent source</dt>
              <dd>
                <code>{release.peer}</code>
              </dd>
            </div>
          </dl>
        </section>
      </main>
      <Footer />
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Release />
  </StrictMode>,
);

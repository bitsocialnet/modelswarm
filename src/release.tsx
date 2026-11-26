import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { Topbar } from './components/topbar/topbar';
import { doc } from './data/content';
import { demoModel } from './data/demo-model';
import { Footer } from './sections/footer';
import { SplitDownload } from './components/split-download/split-download';
import { ArrowRightIcon, CheckIcon, FileIcon, KeyIcon } from './components/icons/icons';
import { formatBytes } from './data/catalogue';
import release from './data/demo-release.json';
import styles from './release.module.css';

const command = `cli/.venv/bin/modelswarm pull '${release.release_uri}' \\
  --peer ${release.peer} --no-discovery`;

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
      <Topbar />
      <main className={`wrap ${styles.main}`} id='main'>
        <header className={styles.intro}>
          <p className={styles.crumbs}>
            <a href='./catalogue.html'>Models</a>
            <span aria-hidden='true'>/</span>
            <span>{demoModel.publisher}</span>
          </p>
          <h1>{demoModel.title}</h1>
          <p className={styles.description}>{demoModel.description}</p>
          <ul className={styles.chips} aria-label='Details'>
            <li className='chip chip-verified'>
              <CheckIcon size={13} />
              Signed release
            </li>
            <li className='chip'>
              {demoModel.format} · {demoModel.quantization}
            </li>
            <li className='chip'>{demoModel.size}</li>
            <li className='chip'>{demoModel.license}</li>
            <li className='chip'>{release.version}</li>
          </ul>
          <div className={styles.actions}>
            <SplitDownload />
            <a className='button' href={demoModel.https}>
              Download over HTTPS
            </a>
          </div>
          <p className={styles.downloadHelp}>
            Open the .torrent in a BitTorrent v2 client such as qBittorrent with libtorrent 2.x. <a href={demoModel.modelCard}>Upstream model card</a>
          </p>
        </header>

        <div className={styles.layout}>
          <div className={styles.primary}>
            <section className={styles.section} aria-labelledby='files'>
              <h2 id='files'>Files</h2>
              <ul className={styles.files}>
                {release.files.map((file) => (
                  <li key={file.path}>
                    <span className={styles.fileName}>
                      <FileIcon size={14} />
                      {file.path}
                    </span>
                    <span>{formatBytes(file.size)}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className={styles.section} aria-labelledby='download'>
              <h2 id='download'>Verify and download with the CLI</h2>
              <p>
                Set up the CLI, Node bridge and your own reader node using the <a href={doc('cli/demo/README.md#pull-from-the-public-seeder')}>signed demo instructions</a>.
                Then run this command using that node's RPC connection. The CLI verifies the signed announcement and prints the local snapshot path.
              </p>
              <div className={styles.terminal}>
                <div className={styles.termBar}>
                  <span>~/modelswarm</span>
                  <button type='button' className='button button-small' onClick={() => void copyCommand()}>
                    Copy command
                  </button>
                </div>
                <pre aria-label='Signed release pull command'>
                  <code>{command}</code>
                </pre>
              </div>
              <p className={styles.copyStatus} role='status'>
                {copyStatus}
              </p>
              <p>
                On a slower connection, add <code>--timeout 900</code>. Rerun the pull to resume from the saved checkpoint.
              </p>
              <p>
                Want to try the CLI without a reader node? <a href={doc('README.md#getting-started')}>Use the HTTP quickstart</a>.
              </p>
            </section>
          </div>

          <aside className={styles.publisher} aria-labelledby='publisher'>
            <h2 id='publisher'>
              <KeyIcon size={15} />
              Publisher
            </h2>
            <p>The {demoModel.publisher} signed this release of Qwen’s original files.</p>
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
                <dt>Version</dt>
                <dd>
                  <code>{release.version}</code>
                </dd>
              </div>
              <div>
                <dt>BitTorrent v2 infohash</dt>
                <dd>
                  <code>{release.weights.infohash_v2}</code>
                </dd>
              </div>
              <div>
                <dt>GGUF SHA-256</dt>
                <dd>
                  <code>{release.weights.sha256}</code>
                </dd>
              </div>
              <div>
                <dt>License</dt>
                <dd>
                  <a href={demoModel.licenseUrl}>{demoModel.license}</a>
                </dd>
              </div>
            </dl>
            <a className='link-arrow' href='./demo/qwen-signed-manifest.json'>
              View release manifest
              <ArrowRightIcon size={14} />
            </a>
          </aside>
        </div>
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

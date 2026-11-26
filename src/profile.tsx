import { StrictMode, useRef, useState, type KeyboardEvent } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { Topbar } from './components/topbar/topbar';
import { Footer } from './sections/footer';
import { KeyAvatar } from './components/key-avatar/key-avatar';
import { ArrowRightIcon, CheckIcon, DownloadIcon, KeyIcon } from './components/icons/icons';
import { BSIP, doc } from './data/content';
import { demoModel } from './data/demo-model';
import release from './data/demo-release.json';
import styles from './profile.module.css';

const TABS = ['Releases', 'Discussion', 'Identity'] as const;
type Tab = (typeof TABS)[number];

const short = (value: string) => `${value.slice(0, 12)}…${value.slice(-6)}`;

// The demo publisher's author community (BSIP-14), drawn from the static demo release. A live profile
// page would load the community at the key over a Bitsocial connection; this one only shows the shape.
function Profile() {
  const [tab, setTab] = useState<Tab>('Releases');
  const [copied, setCopied] = useState('');
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(release.publisher);
      setCopied('Key copied.');
    } catch {
      setCopied('Copy failed. Select the key under Identity to copy it.');
    }
  }

  // Arrow keys move between tabs, as in a native tab list.
  function onTabKey(event: KeyboardEvent, index: number) {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + TABS.length) % TABS.length;
    setTab(TABS[next]);
    tabRefs.current[next]?.focus();
  }

  return (
    <>
      <a className='skip' href='#main'>
        Skip to content
      </a>
      <Topbar />
      <main className={`wrap ${styles.main}`} id='main'>
        <header className={styles.header}>
          <KeyAvatar value={release.publisher} size={96} className={styles.avatar} />
          <div className={styles.headText}>
            <p className={styles.crumbs}>
              <a href='./catalogue.html'>Models</a>
              <span aria-hidden='true'>/</span>
              <span>Publishers</span>
            </p>
            <h1>{demoModel.publisher}</h1>
            <p className={styles.handle}>
              <span className={styles.noName}>no .bso name yet</span>
              <span aria-hidden='true'>·</span>
              <button type='button' className={styles.key} onClick={() => void copyKey()} title='Copy the signing key'>
                <KeyIcon size={13} />
                {short(release.publisher)}
              </button>
              <span className={styles.copied} role='status'>
                {copied}
              </span>
            </p>
            <ul className={styles.chips} aria-label='Profile'>
              <li className='chip chip-verified'>
                <CheckIcon size={13} />
                Author community
              </li>
              <li className='chip'>Publisher</li>
              <li className='chip'>1 release</li>
            </ul>
          </div>
          <div className={styles.headActions}>
            <button type='button' className='button' disabled aria-describedby='follow-note'>
              Follow
            </button>
            <p id='follow-note'>Following needs the desktop client, which is not built yet.</p>
          </div>
        </header>

        <div className={styles.layout}>
          <div className={styles.primary}>
            <div className={styles.tabs} role='tablist' aria-label='Profile sections'>
              {TABS.map((name, i) => (
                <button
                  key={name}
                  ref={(node) => {
                    tabRefs.current[i] = node;
                  }}
                  id={`tab-${name}`}
                  type='button'
                  role='tab'
                  aria-selected={tab === name}
                  aria-controls={`panel-${name}`}
                  tabIndex={tab === name ? 0 : -1}
                  onClick={() => setTab(name)}
                  onKeyDown={(event) => onTabKey(event, i)}
                >
                  {name}
                  {name === 'Releases' && <span className={styles.count}>1</span>}
                </button>
              ))}
            </div>

            <div id={`panel-${tab}`} role='tabpanel' aria-labelledby={`tab-${tab}`} className={styles.panel} tabIndex={0}>
              {tab === 'Releases' && (
                <ul className={styles.releases}>
                  <li>
                    <div className={styles.releaseHead}>
                      <h2>
                        <a href={demoModel.page}>{demoModel.title}</a>
                      </h2>
                      <span className='chip chip-verified'>{release.version}</span>
                    </div>
                    <p className={styles.dim}>{demoModel.description}</p>
                    <ul className={styles.releaseChips} aria-label='Details'>
                      <li className='chip'>
                        {demoModel.format} · {demoModel.quantization}
                      </li>
                      <li className='chip'>{demoModel.size}</li>
                      <li className='chip'>{demoModel.license}</li>
                    </ul>
                    <p className={styles.cid}>release CID {short(release.release_cid)}</p>
                    <div className={styles.releaseActions}>
                      <a className='button button-small button-primary' href={demoModel.torrent} download>
                        <DownloadIcon size={14} />
                        Download .torrent
                      </a>
                      <a className='link-arrow' href={demoModel.page}>
                        Release page
                        <ArrowRightIcon size={14} />
                      </a>
                    </div>
                  </li>
                </ul>
              )}

              {tab === 'Discussion' && (
                <div className={styles.empty}>
                  <h2>Discussion lives in the hubs</h2>
                  <p>
                    Hubs crosspost releases and host the replies, each under its own rules. This page does not load them yet; the CLI can reply from your own node.
                  </p>
                  <a className='link-arrow' href={doc('catalogue/README.md#publish-and-discuss-in-a-community')}>
                    Publish and discuss in a community
                    <ArrowRightIcon size={14} />
                  </a>
                </div>
              )}

              {tab === 'Identity' && (
                <dl className={styles.identity}>
                  <div>
                    <dt>Signing key</dt>
                    <dd>
                      <code>{release.publisher}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Profile address</dt>
                    <dd>
                      The same key. A profile is an author community addressed by its author's key (<a href={BSIP(14)}>BSIP-14</a>).
                    </dd>
                  </div>
                  <div>
                    <dt>.bso name</dt>
                    <dd>
                      None. Publishers work as bare keys until <code>.bso</code> names launch (<a href={BSIP(13)}>BSIP-13</a>).
                    </dd>
                  </div>
                  <div>
                    <dt>Linked accounts</dt>
                    <dd>None yet. A publisher ties its key to a name the way projects publish a GPG key: on its website, its GitHub organization or a .bso name.</dd>
                  </div>
                </dl>
              )}
            </div>
          </div>

          <aside className={styles.side} aria-label='About this profile'>
            <div className={styles.sideCard}>
              <h2>Profile node</h2>
              <p>Run by the ModelSwarm project with the public demo. Publishers without an always-on node can wait for hosted profiles from Forge RPC or another provider.</p>
              <a className='link-arrow' href={doc('how-it-could-work.md#publishers-and-profiles')}>
                Publishers and profiles
                <ArrowRightIcon size={14} />
              </a>
            </div>
            <div className={styles.sideCard}>
              <h2>A preview of profile pages</h2>
              <p>
                This page is built from the static demo release. A live profile page would load the author community at this key through your own node or an RPC
                provider.
              </p>
              <a className='link-arrow' href='./#handles'>
                Preview a handle
                <ArrowRightIcon size={14} />
              </a>
            </div>
          </aside>
        </div>
      </main>
      <Footer />
    </>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Profile />
  </StrictMode>,
);

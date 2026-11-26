import { StrictMode, Suspense, use, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/oxanium/index.css';
import '@fontsource-variable/red-hat-mono/index.css';
import './index.css';
import { Topbar } from './components/topbar/topbar';
import { Footer } from './sections/footer';
import { doc } from './data/content';
import { demoModel } from './data/demo-model';
import { demoEntry, formatBytes, formatCount, loadCatalogue, type CommunityFile, type Model } from './data/catalogue';
import { groupVariants, modelFamily, starterPicks } from './data/catalogue-selection';
import { communityHttpsLink, communityTorrentLink } from './lib/community-links';
import styles from './catalogue.module.css';

const pageSize = 30;
const catalogue = loadCatalogue().catch(() => null);

const SOURCE = {
  demo: 'Signed demo',
  import: 'Pirate Face index',
  community: 'Signed release',
};

function Catalogue() {
  return (
    <>
      <a className='skip' href='#main'>
        Skip to content
      </a>
      <Topbar catalogue />
      <main id='main'>
        <header className={`wrap ${styles.intro}`}>
          <div>
            <h1>Open-weight models</h1>
            <p>Find weights for running AI locally and download them from BitTorrent swarms.</p>
          </div>
          <div className={styles.introLinks}>
            <a href='#model-search'>Search models</a>
            <a href='#self-host'>Run your own catalogue</a>
          </div>
        </header>
        <section className={`wrap ${styles.browse}`} aria-labelledby='browse-title'>
          <Suspense fallback={<ModelDirectory models={[demoEntry]} loading />}>
            <LoadedDirectory />
          </Suspense>
        </section>
        <section className={`wrap ${styles.explain}`} id='self-host' aria-labelledby='self-host-title'>
          <h2 id='self-host-title'>Your catalogue. The same swarms.</h2>
          <div className={styles.explainGrid}>
            <div>
              <h3>Keep seeding</h3>
              <p>
                Imported magnets retain their original infohashes. If your torrent client already has the files, leave it seeding. Anyone opening the same magnet can join
                that swarm.
              </p>
            </div>
            <div>
              <h3>Run your own instance</h3>
              <p>Host the static site and build your own index from public torrent snapshots and the Bitsocial communities you choose.</p>
            </div>
            <div>
              <h3>Publish and discuss</h3>
              <p>
                Publishers sign releases from their own Bitsocial profiles. Communities can share those releases, set their own rules and discuss them using their own
                nodes.
              </p>
            </div>
          </div>
          <div className={styles.explainLinks}>
            <a className='button' href={doc('catalogue/README.md')}>
              Self-hosting guide
            </a>
            <a href='./#how'>How ModelSwarm works</a>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

function LoadedDirectory() {
  const snapshot = use(catalogue);
  return <ModelDirectory models={snapshot?.models ?? [demoEntry]} observedAt={snapshot?.observedAt} failed={!snapshot} />;
}

function ModelDirectory({ models, observedAt, loading, failed }: { models: Model[]; observedAt?: string; loading?: boolean; failed?: boolean }) {
  const [query, setQuery] = useState('');
  const [format, setFormat] = useState('');
  const [limit, setLimit] = useState('');
  const [order, setOrder] = useState('catalogue');
  const [visible, setVisible] = useState(pageSize);
  const words = query.trim().toLowerCase().split(/\s+/);
  const matches = models.filter((model) => {
    const haystack = `${model.name} ${modelFamily(model.id) ?? ''} ${model.format} ${model.license} ${model.community?.publisher ?? ''}`.toLowerCase();
    return (!format || model.format === format) && (!limit || (model.bytes !== null && model.bytes <= Number(limit))) && words.every((word) => haystack.includes(word));
  });
  if (order === 'seeders') matches.sort((a, b) => (b.seeders ?? -1) - (a.seeders ?? -1));
  if (order === 'size') matches.sort((a, b) => (a.bytes ?? Infinity) - (b.bytes ?? Infinity));
  const formats = Array.from(new Set(models.map((model) => model.format))).sort();
  const groups = Array.from(groupVariants(matches));

  return (
    <>
      {!loading && <StarterPicks models={models} />}
      <div className={styles.directoryHeading}>
        <h2 id='browse-title'>Browse all models</h2>
        <p role='status'>{loading ? 'Loading index…' : `${formatCount(matches.length)} ${matches.length === 1 ? 'model' : 'models'}`}</p>
      </div>
      <search className={styles.filters} aria-label='Model catalogue'>
        <label className={styles.search}>
          <span>Search models</span>
          <input
            id='model-search'
            type='search'
            value={query}
            placeholder='Search by model, publisher or license'
            disabled={loading}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisible(pageSize);
            }}
          />
        </label>
        <label>
          <span>Format</span>
          <select
            value={format}
            disabled={loading}
            onChange={(event) => {
              setFormat(event.target.value);
              setVisible(pageSize);
            }}
          >
            <option value=''>All formats</option>
            {formats.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Download size</span>
          <select
            value={limit}
            disabled={loading}
            onChange={(event) => {
              setLimit(event.target.value);
              setVisible(pageSize);
            }}
          >
            <option value=''>Any size</option>
            <option value='1000000000'>Up to 1 GB</option>
            <option value='10000000000'>Up to 10 GB</option>
            <option value='50000000000'>Up to 50 GB</option>
          </select>
        </label>
        <label>
          <span>Sort by</span>
          <select
            value={order}
            disabled={loading}
            onChange={(event) => {
              setOrder(event.target.value);
              setVisible(pageSize);
            }}
          >
            <option value='catalogue'>Default</option>
            <option value='seeders'>Most seeders</option>
            <option value='size'>Smallest first</option>
          </select>
        </label>
      </search>
      {failed && (
        <p className={styles.note} role='status'>
          The index could not load. Reload to try again.
        </p>
      )}
      <p className={styles.note}>Seeder counts reflect the last observation{observedAt ? ` (${observedAt.slice(0, 10)})` : ''}.</p>
      {matches.length ? (
        <>
          <div className={styles.columnHeads} aria-hidden='true'>
            <span>Model / source</span>
            <span>Format</span>
            <span>Size</span>
            <span>Seeders</span>
            <span>Download</span>
          </div>
          <ul className={styles.results} aria-label='Models'>
            {groups.slice(0, visible).map(({ name, models }) =>
              name && models.length > 1 ? (
                <li key={name} className={styles.variantGroup}>
                  <details>
                    <summary>
                      <strong>{name}</strong> <span>{models.length} GGUF variants</span>
                    </summary>
                    <ul className={styles.results} aria-label={`${name} variants`}>
                      {models.map((model) => (
                        <ModelRow key={model.id} model={model} />
                      ))}
                    </ul>
                  </details>
                </li>
              ) : (
                <ModelRow key={models[0].id} model={models[0]} />
              ),
            )}
          </ul>
          {visible < groups.length && (
            <button className={`${styles.more} button`} type='button' onClick={() => setVisible((count) => count + pageSize)}>
              Show more models
            </button>
          )}
        </>
      ) : (
        <p className={styles.empty}>No models match. Try a shorter search or change the filters.</p>
      )}
    </>
  );
}

function StarterPicks({ models }: { models: Model[] }) {
  const picks = starterPicks.flatMap((pick) => {
    const model = models.find(({ id }) => id === pick.id);
    return model?.download ? [{ pick, model }] : [];
  });

  return (
    <section className={styles.starters} aria-labelledby='starter-title'>
      <h2 id='starter-title'>Start with a small model</h2>
      <ul>
        {picks.map(({ pick, model }) => (
          <li key={model.id}>
            <div>
              <h3>{model.kind === 'demo' ? <a href={demoModel.page}>{pick.name}</a> : pick.name}</h3>
              <p>{pick.description}</p>
              <p className={styles.pickMeta}>
                {pick.format} · {formatBytes(model.bytes)} · {SOURCE[model.kind]}
                {model.kind === 'demo' && (
                  <>
                    {' '}
                    · <a href={demoModel.https}>HTTPS download</a>
                  </>
                )}
              </p>
            </div>
            <TorrentAction model={model} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function TorrentAction({ model }: { model: Model }) {
  if (!model.download) return null;
  const isFile = model.kind === 'demo';
  return (
    <div className={styles.torrentAction}>
      <a className='button' href={model.download} download={isFile || undefined}>
        {isFile ? 'Download .torrent' : 'Open in torrent client'}
      </a>
      {isFile && <span>Open the file in a BitTorrent v2 client.</span>}
    </div>
  );
}

function ModelRow({ model }: { model: Model }) {
  const discussion = useRef<HTMLDetailsElement>(null);
  return (
    <li className={styles.row}>
      <div className={styles.rowGrid}>
        <div className={styles.modelName}>
          <h3>{model.kind === 'demo' ? <a href={demoModel.page}>{model.name}</a> : model.name}</h3>
          <p>
            <span className={model.kind === 'import' ? undefined : styles.verified}>{SOURCE[model.kind]}</span>
            {' · '}
            {model.license}
          </p>
        </div>
        <p className={styles.metric}>
          <span>Format</span>
          {model.format}
        </p>
        <p className={styles.metric}>
          <span>Size</span>
          {formatBytes(model.bytes)}
        </p>
        <p className={`${styles.metric} ${styles.seeders}`}>
          <span>Seeders</span>
          {model.seeders === null ? 'Unknown' : formatCount(model.seeders)}
        </p>
        <div className={styles.download}>
          {model.community && (
            <a
              className='button'
              href={`#${model.id}`}
              onClick={() => {
                if (discussion.current) discussion.current.open = true;
              }}
            >
              View files
            </a>
          )}
          <TorrentAction model={model} />
        </div>
      </div>
      {model.kind === 'import' && (
        <details className={styles.details}>
          <summary>Release details</summary>
          <p>Magnet indexed by Pirate Face. Check publisher provenance and terms at the original source.</p>
          {model.peerOnly && (
            <p>
              <a href={model.peerOnly}>Open peer-only magnet</a> · Uses DHT without Pirate Face’s tracker
            </p>
          )}
          {model.revision && (
            <p>
              Source revision <code>{model.revision}</code>
            </p>
          )}
          <p>
            <a href={`https://pirateface.co/${model.name.split('/').map(encodeURIComponent).join('/')}`}>Pirate Face listing</a>
            {model.upstream?.startsWith('https://') && (
              <>
                {' '}
                · <a href={model.upstream}>Original source</a>
              </>
            )}
          </p>
        </details>
      )}
      {model.community && (
        <details className={styles.details} id={model.id} ref={discussion}>
          <summary>Files and discussion ({model.community.replies.length})</summary>
          <p>
            Version {model.community.version} · Signed by <code>{model.community.publisher}</code>
          </p>
          <p>
            Release CID <code>{model.community.releaseCid}</code>
          </p>
          <ul>
            {model.community.files.map((file) => (
              <CommunityFileRow key={file.path} file={file} />
            ))}
          </ul>
          <p>
            Community key <code>{model.community.key}</code>
          </p>
          <p>
            Community post <code>{model.community.postCid}</code>
          </p>
          {model.community.replies.map((reply) => (
            <blockquote key={reply.cid}>
              <p>{reply.text}</p>
              <footer>{reply.author}</footer>
            </blockquote>
          ))}
          <a href={doc('catalogue/README.md#publish-and-discuss-in-a-community')}>Reply from your node</a>
        </details>
      )}
    </li>
  );
}

function CommunityFileRow({ file }: { file: CommunityFile }) {
  const https = file.flagged ? null : communityHttpsLink(file.https);
  const torrent = file.flagged ? null : communityTorrentLink(file.torrent);
  return (
    <li>
      <strong>{file.path}</strong> · {formatBytes(file.bytes)}
      {file.flagged && <> · Download via CLI with explicit approval</>}
      {torrent && (
        <>
          {' '}
          ·{' '}
          <a href={torrent} download>
            Download .torrent
          </a>{' '}
          (open in a BitTorrent v2 client)
        </>
      )}
      {https && (
        <>
          {' '}
          · <a href={https.href}>HTTPS ({https.hostname})</a>
        </>
      )}
      <p>
        SHA-256 <code>{file.sha256}</code>
      </p>
    </li>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Catalogue />
  </StrictMode>,
);

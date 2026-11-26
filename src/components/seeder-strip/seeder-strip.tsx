import { Suspense, use } from 'react';
import { catalogueSearch, catalogueSnapshot, formatBytes, formatCount, mostSeeded, type Model } from '../../data/catalogue';
import { ArrowRightIcon, SeedIcon } from '../icons/icons';
import styles from './seeder-strip.module.css';

const SHOWN = 14;

// The most seeded torrents in the bundled index, drifting along the foot of the hero console.
export function SeederStrip() {
  return (
    <div className={styles.strip}>
      <div className={styles.label}>
        <h2>Most seeded</h2>
        <p>Pirate Face index</p>
      </div>
      <Suspense fallback={<p className={styles.loading}>Loading the index…</p>}>
        <Loaded />
      </Suspense>
      <a className={`link-arrow ${styles.all}`} href='./catalogue.html'>
        All models
        <ArrowRightIcon size={14} />
      </a>
    </div>
  );
}

function Loaded() {
  const snapshot = use(catalogueSnapshot());
  const models = snapshot ? mostSeeded(snapshot.models, SHOWN) : [];
  if (!models.length) return <p className={styles.loading}>The index could not load.</p>;
  const observed = snapshot?.observedAt?.slice(0, 10);

  return (
    <div className={styles.track} tabIndex={0} role='region' aria-label={`Most seeded models${observed ? `, observed ${observed}` : ''}. Scrolls sideways.`}>
      <div className={styles.belt}>
        <Entries models={models} />
        {/* The second copy closes the loop for the drift; screen readers and keyboards get the first only. */}
        <Entries models={models} hidden />
      </div>
    </div>
  );
}

function Entries({ models, hidden }: { models: Model[]; hidden?: boolean }) {
  return (
    <ul className={styles.list} aria-hidden={hidden || undefined}>
      {models.map((model) => (
        <li key={model.id}>
          <a href={catalogueSearch(model.name)} tabIndex={hidden ? -1 : undefined}>
            <span className={styles.name}>{model.name}</span>
            <span className={styles.count}>
              <SeedIcon size={13} />
              {formatCount(model.seeders ?? 0)}
              <span className='visually-hidden'> seeders,</span>
            </span>
            <span className={styles.size}>{formatBytes(model.bytes)}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

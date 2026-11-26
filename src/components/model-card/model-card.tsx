import { demoModel } from '../../data/demo-model';
import { catalogueSearch, formatBytes, formatCount, type Model } from '../../data/catalogue';
import { DownloadIcon, SeedIcon } from '../icons/icons';
import styles from './model-card.module.css';

const SOURCE = {
  demo: 'Signed release',
  import: 'Pirate Face index',
  community: 'Signed release',
};

type ModelCardProps = {
  model: Model;
  name: string;
  description: string;
  format: string;
};

// A model from the catalogue as a card: what it is, the facts that decide a download, and the download itself.
export function ModelCard({ model, name, description, format }: ModelCardProps) {
  const signed = model.kind !== 'import';
  const isFile = model.kind === 'demo';
  const page = isFile ? demoModel.page : catalogueSearch(model.name);
  return (
    <article className={styles.card} data-signed={signed}>
      <header className={styles.head}>
        <h3 className={styles.name}>
          <a href={page}>{name}</a>
        </h3>
        <p className={styles.repo}>{isFile ? 'Qwen/Qwen2.5-0.5B-Instruct-GGUF' : model.name}</p>
      </header>
      <p className={styles.description}>{description}</p>
      <ul className={styles.chips} aria-label='Details'>
        <li className={signed ? 'chip chip-verified' : 'chip'}>{SOURCE[model.kind]}</li>
        <li className='chip'>{format}</li>
        <li className='chip'>{formatBytes(model.bytes)}</li>
        <li className='chip'>{model.license}</li>
        {model.seeders !== null && (
          <li className='chip'>
            <SeedIcon size={13} />
            {formatCount(model.seeders)}
            <span className='visually-hidden'> seeders</span>
          </li>
        )}
      </ul>
      {model.download && (
        <div className={styles.actions}>
          <a className={`button button-small ${signed ? 'button-primary' : ''}`} href={model.download} download={isFile || undefined}>
            <DownloadIcon size={14} />
            {isFile ? 'Download .torrent' : 'Open magnet'}
          </a>
          <a className={styles.details} href={page}>
            {isFile ? 'Release page' : 'In the catalogue'}
          </a>
        </div>
      )}
    </article>
  );
}

import type { ReactNode } from 'react';
import { doc } from '../../data/content';
import styles from './section-head.module.css';

type SectionHeadProps = {
  // The repository document this section summarises; the tab links to the full text.
  source: string;
  id: string;
  children: ReactNode;
  lede?: ReactNode;
};

export function SectionHead({ source, id, children, lede }: SectionHeadProps) {
  const file = source.split('#')[0];
  return (
    <header className={styles.head}>
      <h2 id={id} className={styles.title}>
        {children}
      </h2>
      <a className={styles.source} href={doc(source)}>
        <FileGlyph />
        <span>{file}</span>
        <span className={styles.visuallyHidden}> (full text on GitHub)</span>
      </a>
      {lede && <p className={styles.lede}>{lede}</p>}
    </header>
  );
}

function FileGlyph() {
  return (
    <svg width='12' height='14' viewBox='0 0 12 14' aria-hidden='true' focusable='false'>
      <path d='M1 .5h6.5L11 4v9.5H1z' fill='none' stroke='currentColor' />
      <path d='M7.5.5V4H11M3 7h6M3 9.5h6' fill='none' stroke='currentColor' />
    </svg>
  );
}

import { HUGGINGSOCIAL, NEW_ISSUE, REPO, doc } from '../data/content';
import { Logo } from '../components/logo/logo';
import styles from './footer.module.css';

type FooterLink = { label: string; href: string };

// Grouped like directories, the way the section tabs name the repository files.
const GROUPS: { name: string; links: FooterLink[] }[] = [
  {
    name: 'docs/',
    links: [
      { label: 'README.md', href: REPO },
      { label: 'how-it-could-work.md', href: doc('how-it-could-work.md') },
      { label: 'open-questions.md', href: doc('open-questions.md') },
      { label: 'roadmap.md', href: doc('roadmap.md') },
    ],
  },
  {
    name: 'project/',
    links: [
      { label: 'GitHub repository', href: REPO },
      { label: 'Open an issue', href: NEW_ISSUE },
      { label: 'License', href: doc('LICENSE') },
    ],
  },
  {
    name: 'built-on/',
    links: [
      { label: 'Bitsocial', href: 'https://bitsocial.net' },
      { label: 'Bitsocial proposals', href: 'https://bsips.bitsocial.net' },
      { label: 'BitTorrent v2', href: 'https://www.bittorrent.org/beps/bep_0052.html' },
      { label: 'HuggingSocial by Rinse12', href: HUGGINGSOCIAL },
    ],
  },
  {
    name: 'follow/',
    links: [{ label: '@bitsocialnet on X', href: 'https://x.com/bitsocialnet' }],
  },
];

const COMMIT = import.meta.env.VITE_COMMIT_REF;

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`wrap ${styles.top}`}>
        <div className={styles.brand}>
          <a className={styles.mark} href='./' aria-label='Modelswarm home'>
            <Logo size={34} />
            <span>modelswarm</span>
          </a>
          <p>Open-weight AI models, distributed by a swarm of peers as in a BitTorrent swarm.</p>
          <a className={`button ${styles.star}`} href={REPO}>
            <StarGlyph />
            Star on GitHub
          </a>
        </div>
        <nav className={styles.groups} aria-label='Footer'>
          {GROUPS.map((group) => (
            <div key={group.name} className={styles.group}>
              <h2 className={styles.groupName}>{group.name}</h2>
              <ul>
                {group.links.map((link) => (
                  <li key={link.label}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>
      <div className={`wrap ${styles.bottom}`}>
        <p>
          Free software under <a href={doc('LICENSE')}>GPL-3.0-or-later</a>. The project would publish a client and tooling. It hosts no models.
        </p>
        {COMMIT && (
          <a className={styles.build} href={`${REPO}/commit/${COMMIT}`}>
            build {COMMIT.slice(0, 7)}
          </a>
        )}
      </div>
    </footer>
  );
}

function StarGlyph() {
  return (
    <svg width='14' height='14' viewBox='0 0 16 16' aria-hidden='true' focusable='false'>
      <path
        fill='none'
        stroke='currentColor'
        strokeWidth='1.3'
        strokeLinejoin='round'
        d='M8 1.4l1.98 4.02 4.44.64-3.21 3.13.76 4.42L8 11.53l-3.97 2.08.76-4.42L1.58 6.06l4.44-.64z'
      />
    </svg>
  );
}

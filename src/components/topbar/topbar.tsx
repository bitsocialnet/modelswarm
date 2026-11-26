import { useEffect, useRef } from 'react';
import { REPO } from '../../data/content';
import { catalogueSearch } from '../../data/catalogue';
import { Logo } from '../logo/logo';
import { GitHubMark, SearchIcon } from '../icons/icons';
import styles from './topbar.module.css';

const LINKS = [
  { href: './#how', label: 'How it works', primary: true },
  { href: './#compare', label: 'Compared' },
  { href: './#faq', label: 'FAQ' },
];

// On the catalogue the page has its own search, so the bar leaves it out.
export function Topbar({ catalogue = false }: { catalogue?: boolean }) {
  return (
    <header className={styles.topbar}>
      <div className={`wrap ${styles.inner}`}>
        <a className={styles.brand} href='./' aria-label='ModelSwarm home'>
          <Logo size={30} />
          <span>ModelSwarm</span>
        </a>
        {!catalogue && <ModelSearch />}
        <nav className={styles.nav} aria-label='Main'>
          <a className={styles.models} href='./catalogue.html' aria-current={catalogue ? 'page' : undefined}>
            Models
          </a>
          {LINKS.map((link) => (
            <a key={link.href} className={link.primary ? styles.about : styles.link} href={link.href}>
              {link.label}
            </a>
          ))}
          <a className={styles.github} href={REPO}>
            <GitHubMark />
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}

// Searching opens the catalogue with the query. The site's CSP forbids form submission, so navigation happens in script.
function ModelSearch() {
  const inputRef = useRef<HTMLInputElement>(null);

  // "/" focuses the search from anywhere except another text field.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      if (target.closest('input, textarea, select, [contenteditable="true"]')) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <search className={styles.search}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const query = inputRef.current?.value.trim() ?? '';
          window.location.assign(query ? catalogueSearch(query) : './catalogue.html');
        }}
      >
        <label htmlFor='topbar-search' className='visually-hidden'>
          Search models
        </label>
        <SearchIcon size={14} className={styles.searchIcon} />
        <input ref={inputRef} id='topbar-search' type='search' placeholder='Search models' autoComplete='off' enterKeyHint='search' />
        <kbd className={styles.kbd} aria-hidden='true'>
          /
        </kbd>
      </form>
    </search>
  );
}

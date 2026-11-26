import { useEffect, useId, useRef } from 'react';
import { demoModel } from '../../data/demo-model';
import { ChevronDownIcon, DownloadIcon } from '../icons/icons';
import styles from './split-download.module.css';

// The signed demo's main download, with the other ways to get the same file behind the chevron.
export function SplitDownload({ size = 'large' }: { size?: 'large' | 'small' }) {
  const menuRef = useRef<HTMLDetailsElement>(null);
  const menuId = useId();

  // <details> has no light dismiss: close it on an outside press or Escape.
  useEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const onPointer = (event: PointerEvent) => {
      if (menu.open && !menu.contains(event.target as Node)) menu.open = false;
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menu.open) {
        menu.open = false;
        menu.querySelector('summary')?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  return (
    <div className={styles.split} data-size={size}>
      <a className={`button button-primary ${styles.main}`} href={demoModel.torrent} download>
        <DownloadIcon />
        Download .torrent
      </a>
      <details ref={menuRef} className={styles.more}>
        <summary className={`button button-primary ${styles.toggle}`} aria-label='More ways to download' aria-controls={menuId}>
          <ChevronDownIcon />
        </summary>
        <ul id={menuId} className={styles.menu}>
          <li>
            <a href={demoModel.torrent} download>
              <strong>BitTorrent v2 .torrent</strong>
              <span>Open it in a client such as qBittorrent with libtorrent 2.x</span>
            </a>
          </li>
          <li>
            <a href={demoModel.https}>
              <strong>HTTPS from Hugging Face</strong>
              <span>The same pinned file, {demoModel.size}</span>
            </a>
          </li>
          <li>
            <a href={`${demoModel.page}#download`}>
              <strong>Verify with the CLI</strong>
              <span>Checks the publisher signature and every piece</span>
            </a>
          </li>
        </ul>
      </details>
    </div>
  );
}

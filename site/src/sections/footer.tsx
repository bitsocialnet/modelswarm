import { REPO, doc } from '../data/content';
import { Logo } from '../components/logo/logo';
import styles from './footer.module.css';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`wrap ${styles.inner}`}>
        <Logo size={18} className={styles.logo} />
        <p>
          Free software under <a href={doc('LICENSE')}>GPL-3.0-or-later</a>, built on <a href='https://bitsocial.net'>Bitsocial</a>. The project would publish a client
          and tooling. It hosts no models.
        </p>
        <a className={styles.repo} href={REPO}>
          github.com/bitsocialnet/modelswarm
        </a>
      </div>
    </footer>
  );
}

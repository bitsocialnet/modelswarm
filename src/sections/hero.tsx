import { doc } from '../data/content';
import { PullTerminal } from '../components/pull-terminal/pull-terminal';
import styles from './hero.module.css';

export function Hero() {
  return (
    <section className={styles.hero} aria-labelledby='hero-title'>
      <div className={`wrap ${styles.inner}`}>
        <div className={styles.copy}>
          <h1 id='hero-title' className={styles.title}>
            The hub of <span className={styles.nowrap}>open-weight</span> AI models that nobody owns
          </h1>
          <p className={styles.lede}>
            Find open-weight models already shared by BitTorrent swarms. Run your own catalogue and choose which communities to follow. Publishers sign releases from
            their own Bitsocial profiles.
          </p>
          <p className={styles.stage}>
            <span className={styles.stageMark} aria-hidden='true' />
            Already seeding an imported model? Keep seeding from the same client.
          </p>
          <div className={styles.actions}>
            <a className='button button-primary' href='./catalogue.html'>
              Browse models
            </a>
            <a className='button' href={doc('catalogue/README.md')}>
              Self-host ModelSwarm
            </a>
          </div>
        </div>
        <PullTerminal />
      </div>
    </section>
  );
}

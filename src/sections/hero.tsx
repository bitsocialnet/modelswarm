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
            ModelSwarm takes its name from the BitTorrent swarms of peers that share open-weight models. Run your own catalogue, follow communities, and find releases
            signed by their Bitsocial publishers.
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

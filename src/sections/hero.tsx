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
            Models served by a swarm of peers, as in a BitTorrent swarm: people who seed a model share the work of hosting it. Every piece is checked against the
            publisher's signed release while it downloads.
          </p>
          <p className={styles.stage}>
            <span className={styles.stageMark} aria-hidden='true' />
            Try the experimental CLI or inspect the first signed release served by a public swarm.
          </p>
          <div className={styles.actions}>
            <a className='button button-primary' href={doc('README.md#getting-started')}>
              Try ModelSwarm
            </a>
            <a className='button' href='./release.html'>
              View the signed release
            </a>
          </div>
        </div>
        <PullTerminal />
      </div>
    </section>
  );
}

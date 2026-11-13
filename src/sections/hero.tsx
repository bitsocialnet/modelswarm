import { NEW_ISSUE, REPO } from '../data/content';
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
            Models served by a swarm of peers, as in a BitTorrent swarm: everyone who downloads a model seeds it, so no company has to host it. Every piece is checked
            against the publisher's signed release while it downloads.
          </p>
          <p className={styles.stage}>
            <span className={styles.stageMark} aria-hidden='true' />
            Modelswarm has an experimental CLI for making, verifying and pulling unsigned releases. The full hub is not built yet.
          </p>
          <div className={styles.actions}>
            <a className='button button-primary' href={REPO}>
              Contribute on GitHub
            </a>
            <a className='button' href={NEW_ISSUE}>
              Open an issue
            </a>
          </div>
        </div>
        <PullTerminal />
      </div>
    </section>
  );
}

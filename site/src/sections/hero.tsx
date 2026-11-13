import { NEW_ISSUE, REPO } from '../data/content';
import { PullTerminal } from '../components/pull-terminal/pull-terminal';
import styles from './hero.module.css';

export function Hero() {
  return (
    <section className={styles.hero} aria-labelledby='hero-title'>
      <div className={`wrap ${styles.inner}`}>
        <div className={styles.copy}>
          <h1 id='hero-title' className={styles.title}>
            The hub of open AI models that nobody owns
          </h1>
          <p className={styles.lede}>
            Publishers sign their releases. The weights move over BitTorrent. Every piece of every file is checked against the signed release while it downloads.
          </p>
          <p className={styles.stage}>
            <span className={styles.stageMark} aria-hidden='true' />
            Modelswarm is an idea, not a product yet. The design is public and looking for people to pick it apart.
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

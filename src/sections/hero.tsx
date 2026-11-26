import { doc } from '../data/content';
import { demoModel } from '../data/demo-model';
import { PullTerminal } from '../components/pull-terminal/pull-terminal';
import { SplitDownload } from '../components/split-download/split-download';
import { SeederStrip } from '../components/seeder-strip/seeder-strip';
import { ArrowRightIcon } from '../components/icons/icons';
import styles from './hero.module.css';

export function Hero() {
  return (
    <section className={styles.hero} aria-labelledby='hero-title'>
      <div className='wrap'>
        <div className={styles.console}>
          <div className={styles.body}>
            <div className={styles.copy}>
              <h1 id='hero-title' className={styles.title}>
                The hub of <span className={styles.nowrap}>open-weight</span> AI models that nobody owns
              </h1>
              <p className={styles.lede}>
                ModelSwarm is named for the BitTorrent swarms of peers that share open-weight models. Publishers sign releases from their own Bitsocial profiles, and
                every piece is checked against the signed release as it arrives.
              </p>
              <div className={styles.download}>
                <SplitDownload />
                <a className={styles.model} href={demoModel.page}>
                  <strong>{demoModel.title}</strong>
                  <span>
                    {demoModel.format} · {demoModel.size} · <span className={styles.signed}>signed release</span>
                  </span>
                </a>
              </div>
              <p className={styles.links}>
                <a className='link-arrow' href='./catalogue.html'>
                  Browse all models
                  <ArrowRightIcon size={14} />
                </a>
                <a className='link-arrow' href={doc('catalogue/README.md')}>
                  Self-host the catalogue
                  <ArrowRightIcon size={14} />
                </a>
              </p>
            </div>
            <PullTerminal />
          </div>
          <SeederStrip />
        </div>
      </div>
    </section>
  );
}

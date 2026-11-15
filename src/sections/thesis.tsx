import { SectionHead } from '../components/section-head/section-head';
import section from './section.module.css';
import styles from './thesis.module.css';

export function Thesis() {
  return (
    <section className={section.section} aria-labelledby='thesis-title'>
      <div className={`wrap ${styles.grid}`}>
        <SectionHead source='README.md#the-thesis' id='thesis-title'>
          One company holds the files, the list and the conversation
        </SectionHead>
        <div className={styles.body}>
          <p>
            Hugging Face hosts over 3 million models. In September 2026 Nvidia agreed to buy it for $12.9 billion. Whoever owns it, a single company stores the weights,
            decides what is listed and runs the place where each model is discussed. It can remove a model, and others can make it do so.
          </p>
          <p>
            Torrents already keep files alive without a host. What they lack is a way to know who published a file, and a list of models that does not live on one
            website. ModelSwarm adds both with <a href='https://bitsocial.net'>Bitsocial</a>, a peer-to-peer social protocol.
          </p>
        </div>
      </div>
    </section>
  );
}

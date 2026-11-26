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
            Anyone can join the same swarm from a different catalogue by using the same infohash. ModelSwarm uses <a href='https://bitsocial.net'>Bitsocial</a> so that
            communities can also publish and discuss releases across independently run instances.
          </p>
        </div>
      </div>
    </section>
  );
}

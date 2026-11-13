import { HUGGINGSOCIAL, PARTS } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import { inlineCode } from '../lib/inline-code';
import section from './section.module.css';
import styles from './parts.module.css';

export function Parts() {
  return (
    <section id='how' className={section.section} aria-labelledby='how-title'>
      <div className='wrap'>
        <SectionHead
          source='how-it-could-work.md'
          id='how-title'
          lede={
            <>
              The design builds on <a href={HUGGINGSOCIAL}>HuggingSocial</a>, the original proposal by Bitsocial developer Rinse12.
            </>
          }
        >
          The hub, split into parts no one party holds
        </SectionHead>
        <dl className={styles.grid}>
          {PARTS.map((part) => (
            <div key={part.title} className={styles.part}>
              <dt>
                <span className={styles.term}>{part.term}</span>
                <span className={styles.title}>{part.title}</span>
              </dt>
              <dd className={styles.body}>{inlineCode(part.body)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

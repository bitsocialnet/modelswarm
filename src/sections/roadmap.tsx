import { STEPS, USEFUL_ALONE_AFTER } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import section from './section.module.css';
import styles from './roadmap.module.css';

export function Roadmap() {
  return (
    <section id='roadmap' className={section.section} aria-labelledby='roadmap-title'>
      <div className='wrap'>
        <SectionHead source='roadmap.md' id='roadmap-title' lede='The engine, CLI, SDK endpoint and signed publishing have prototypes. Public hosting and the full hub remain. Estimates are focused work, not dates.'>
          What gets built, in order
        </SectionHead>
        <ol className={styles.steps}>
          {STEPS.map((step, i) => (
            <li key={step.title} className={styles.step} data-milestone={i + 1 === USEFUL_ALONE_AFTER}>
              <span className={styles.box} aria-hidden='true'>
                {step.complete ? '[x]' : '[ ]'}
              </span>
              <span className={styles.number}>{i + 1}</span>
              <h3 className={styles.title}>{step.title}</h3>
              <p className={styles.body}>{step.body}</p>
              <span className={styles.estimate}>{step.estimate}</span>
              {i + 1 === USEFUL_ALONE_AFTER && (
                <p className={styles.milestone}>
                  From here the tool is useful to one person with no network of publishers: verified downloads, resumable from several sources.
                </p>
              )}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

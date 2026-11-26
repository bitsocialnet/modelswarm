import { FAQ, type Question } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import { ArrowRightIcon, PlusIcon } from '../components/icons/icons';
import { inlineCode } from '../lib/inline-code';
import section from './section.module.css';
import styles from './faq.module.css';

const half = Math.ceil(FAQ.length / 2);

export function Faq() {
  return (
    <section id='faq' className={section.section} aria-labelledby='faq-title'>
      <div className='wrap'>
        <SectionHead source='README.md' id='faq-title'>
          Questions people ask first
        </SectionHead>
        <div className={styles.columns}>
          <Column questions={FAQ.slice(0, half)} />
          <Column questions={FAQ.slice(half)} />
        </div>
      </div>
    </section>
  );
}

function Column({ questions }: { questions: Question[] }) {
  return (
    <div className={styles.column}>
      {questions.map((item) => (
        <details key={item.q} className={styles.item}>
          <summary>
            <h3>{item.q}</h3>
            <PlusIcon className={styles.icon} />
          </summary>
          <div className={styles.answer}>
            <p>{inlineCode(item.a)}</p>
            {item.more && (
              <a className='link-arrow' href={item.more.href}>
                {item.more.label}
                <ArrowRightIcon size={13} />
              </a>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

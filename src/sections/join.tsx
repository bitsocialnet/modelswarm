import { NEW_ISSUE, QUESTIONS, REPO, doc } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import { ArrowRightIcon, GitHubMark } from '../components/icons/icons';
import styles from './join.module.css';

export function Join() {
  return (
    <section className={styles.join} aria-labelledby='join-title'>
      <div className='wrap'>
        <div className={styles.panel}>
          <SectionHead source='open-questions.md' id='join-title' lede='The open questions are written down, and an issue is the place to argue with any of them.'>
            The design has open questions. Help answer them.
          </SectionHead>
          <div className={styles.side}>
            <ul className={styles.questions}>
              {QUESTIONS.map((question) => (
                <li key={question.anchor}>
                  <a href={doc(`open-questions.md#${question.anchor}`)}>
                    <span>{question.text}</span>
                    <ArrowRightIcon size={14} className={styles.arrow} />
                  </a>
                </li>
              ))}
            </ul>
            <div className={styles.actions}>
              <a className='button button-primary' href={REPO}>
                <GitHubMark />
                Contribute on GitHub
              </a>
              <a className='button' href={NEW_ISSUE}>
                Open an issue
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

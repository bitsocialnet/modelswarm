import { COMPARE_COLUMNS, COMPARE_ROWS, COMPARE_SOURCE, ONLY_HERE } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import section from './section.module.css';
import styles from './compare.module.css';

const OURS = COMPARE_COLUMNS.length - 1;

export function Compare() {
  return (
    <section id='compare' className={section.section} aria-labelledby='compare-title'>
      <div className='wrap'>
        <SectionHead
          source='README.md#nobody-runs-the-list'
          id='compare-title'
          lede='Other projects already move model files over torrents. Each of them still runs the list of models and hosts the discussion. In ModelSwarm nobody does.'
        >
          Compared with what exists
        </SectionHead>
        <div className={styles.scroll} tabIndex={0} role='region' aria-label='Comparison table, scrolls sideways'>
          <table className={styles.table}>
            <thead>
              <tr>
                <td />
                {COMPARE_COLUMNS.map((column, i) => (
                  <th key={column} scope='col' data-ours={i === OURS}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row) => (
                <tr key={row.label}>
                  <th scope='row'>{row.label}</th>
                  {row.cells.map((cell, i) => (
                    <td key={COMPARE_COLUMNS[i]} data-ours={i === OURS} data-column={COMPARE_COLUMNS[i]}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.source}>{COMPARE_SOURCE}</p>
        <div className={styles.only}>
          <h3 className={styles.onlyTitle}>What a project that only moves files cannot add</h3>
          <dl className={styles.onlyList}>
            {ONLY_HERE.map((item) => (
              <div key={item.title} className={styles.onlyItem}>
                <dt>{item.title}</dt>
                <dd>{item.body}</dd>
              </div>
            ))}
          </dl>
          <p className={styles.onlyNote}>
            Both come from <a href='https://bitsocial.net'>Bitsocial</a>, a peer-to-peer social protocol. Matching them means building a social network first, so
            ModelSwarm grows with Bitsocial, not ahead of it.
          </p>
        </div>
      </div>
    </section>
  );
}

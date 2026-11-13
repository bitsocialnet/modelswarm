import { COMPARE_COLUMNS, COMPARE_ROWS } from '../data/content';
import { SectionHead } from '../components/section-head/section-head';
import section from './section.module.css';
import styles from './compare.module.css';

const OURS = COMPARE_COLUMNS.length - 1;

export function Compare() {
  return (
    <section id='compare' className={section.section} aria-labelledby='compare-title'>
      <div className='wrap'>
        <SectionHead source='README.md#the-thesis' id='compare-title'>
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
                    <td key={i} data-ours={i === OURS} data-column={COMPARE_COLUMNS[i]}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

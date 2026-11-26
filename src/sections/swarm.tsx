import type { CSSProperties } from 'react';
import { HUGGINGSOCIAL } from '../data/content';
import release from '../data/demo-release.json';
import { demoModel } from '../data/demo-model';
import { SectionHead } from '../components/section-head/section-head';
import { CheckIcon, KeyIcon } from '../components/icons/icons';
import section from './section.module.css';
import styles from './swarm.module.css';

const short = (value: string, head = 8, tail = 4) => `${value.slice(0, head)}…${value.slice(-tail)}`;

// How the signed demo reaches a reader: what is signed travels over Bitsocial, the bytes travel over the swarm,
// and the two meet only in the reader's client. Values are the real demo release's.
export function Swarm() {
  return (
    <section id='how' className={section.section} aria-labelledby='how-title'>
      <div className='wrap'>
        <SectionHead
          source='how-it-could-work.md'
          id='how-title'
          lede={
            <>
              What a release says and where its bytes come from travel separately, and only your client puts them together. The design builds on{' '}
              <a href={HUGGINGSOCIAL}>HuggingSocial</a>, the original proposal by Bitsocial developer Rinse12.
            </>
          }
        >
          How a release reaches you
        </SectionHead>

        <div className={styles.diagram}>
          <p className={styles.lane} data-lane='signed'>
            Signed on Bitsocial
          </p>
          <ol className={styles.row} data-lane='signed'>
            <li className={styles.node}>
              <h3>
                <KeyIcon size={14} />
                Publisher
              </h3>
              <p className={styles.value}>{short(release.publisher, 12, 6)}</p>
              <p>Signs every release with one key, so a known publisher can be told from an imitator.</p>
            </li>
            <li className={styles.node}>
              <h3>Signed release</h3>
              <p className={styles.value}>{release.version}</p>
              <p>Its manifest lists each file with its size, SHA-256 and BitTorrent v2 pieces root. The release lives in the publisher's own profile.</p>
            </li>
            <li className={styles.node}>
              <h3>Hubs</h3>
              <p className={styles.value}>crossposts</p>
              <p>Communities that curate a model family or task and host the discussion. A hub can drop a release only from its own board.</p>
            </li>
          </ol>

          <p className={styles.lane} data-lane='bytes'>
            Carried by the swarm
          </p>
          <ol className={styles.row} data-lane='bytes'>
            <li className={styles.node}>
              <h3>Seeders</h3>
              <p className={styles.value}>peer {release.peer}</p>
              <p>BitTorrent v2 peers that hold the weights. The public demo has a persistent seeder.</p>
            </li>
            <li className={styles.node}>
              <h3>Mirrors</h3>
              <p className={styles.value}>huggingface.co</p>
              <p>Any HTTP mirror, Hugging Face included, serves pieces too. No mirror has to be trusted.</p>
            </li>
            <li className={styles.node}>
              <h3>Pieces</h3>
              <p className={styles.value}>{demoModel.pieces} pieces of 1 MiB</p>
              <PieceRun />
            </li>
          </ol>

          <div className={styles.client}>
            <h3>Your client</h3>
            <p>Checks each piece against the signed pieces root as it lands. A bad piece is thrown away and fetched again from another source.</p>
            <p className={styles.verified}>
              <CheckIcon size={14} />
              {release.weights.path}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// A short run of pieces arriving: verified ones light up in turn, one fails and is fetched again.
function PieceRun() {
  return (
    <span className={styles.run} aria-hidden='true'>
      {Array.from({ length: 16 }, (_, i) => (
        <i key={i} style={{ '--i': i } as CSSProperties} data-fault={i === 9 || undefined} />
      ))}
    </span>
  );
}

import { useId } from 'react';
import { GAP_STROKE, PIECES, TRANSFORM } from '../logo/pieces';
import styles from './swarm-field.module.css';

const WIDTH = 1200;
const HEIGHT = 240;

type Mark = { x: number; y: number; size: number; tone: 'far' | 'near' | 'lit'; delay: number };

// A seeded random source so the field is the same on every visit and in every build.
function seeded(seed: number) {
  let state = seed;
  return () => (state = (state * 9301 + 49297) % 233280) / 233280;
}

// Rows of logo marks in loose perspective: small and dim at the back, larger toward the front,
// with about one in nine a shade brighter. The centre of the front row is the full mark.
const MARKS: Mark[] = (() => {
  const random = seeded(17);
  const marks: Mark[] = [];
  const sizes = [14, 20, 28, 40, 56];
  sizes.forEach((size, row) => {
    const step = size * (1.5 - row * 0.08);
    const y = 16 + row * 26 + row * row * 4;
    const offset = (row % 2) * (step / 2) - step;
    for (let x = offset; x < WIDTH + step; x += step) {
      // Leave the front-centre clear for the lead mark.
      if (row >= 3 && Math.abs(x + size / 2 - WIDTH / 2) < 90) continue;
      const lit = random() < 0.09;
      marks.push({
        x: x + (random() - 0.5) * size * 0.4,
        y: y + (random() - 0.5) * 10,
        size,
        tone: lit ? 'lit' : row < 3 ? 'far' : 'near',
        delay: Math.round(random() * 6000),
      });
    }
  });
  return marks;
})();

export function SwarmField() {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const mark = `swarm-mark-${id}`;
  const mask = `swarm-gap-${id}`;
  return (
    <div className={styles.field} aria-hidden='true'>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio='xMidYMax slice' focusable='false'>
        <defs>
          <mask id={mask} maskUnits='userSpaceOnUse' x={-20} y={0} width={430} height={430}>
            <rect x={-20} width={430} height={430} fill='white' />
            <path d={PIECES} transform={TRANSFORM} fill='none' stroke='black' strokeWidth={GAP_STROKE} strokeLinejoin='round' />
          </mask>
          <symbol id={mark} viewBox='-20 0 430 430'>
            <g mask={`url(#${mask})`}>
              <path d={PIECES} transform={TRANSFORM} fill='currentColor' />
            </g>
          </symbol>
        </defs>
        {MARKS.map((m, i) => (
          <use
            key={i}
            href={`#${mark}`}
            x={m.x.toFixed(1)}
            y={m.y.toFixed(1)}
            width={m.size}
            height={m.size}
            className={styles[m.tone]}
            style={{ animationDelay: `${m.delay}ms` }}
          />
        ))}
        <use href={`#${mark}`} x={WIDTH / 2 - 64} y={HEIGHT - 150} width={128} height={128} className={styles.lead} />
      </svg>
    </div>
  );
}

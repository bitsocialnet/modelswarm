import { useEffect, useId, useRef, useState } from 'react';
import { GAP_STROKE, PIECE_PARTS, TRANSFORM } from '../components/logo/pieces';
import styles from './assembly.module.css';

// How far, in logo units, each piece starts from its place, and how much it is turned.
const DISTANCE = 150;
const SPIN = [-28, 22, 24, -20];
// Outline width in path units (2.4 logo units). The outline runs along the inner edge left by the seam mask,
// so the large mark keeps the logo's gaps.
const OUTLINE = 24;
const clamp = (value: number) => Math.min(1, Math.max(0, value));

// The large logo: its four pieces arrive from the swarm and lock into place as the section scrolls through,
// the way a file's pieces arrive and are verified. At this size the pieces are outlines with scanlines rather than
// solid lime, dim while they travel and brighter once they lock in. Reduced motion shows the finished mark.
export function Assembly() {
  const sectionRef = useRef<HTMLElement>(null);
  const pieceRefs = useRef<(SVGGElement | null)[]>([]);
  const [landed, setLanded] = useState<number>(PIECE_PARTS.length);
  const maskBase = `assembly-gap-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = section.getBoundingClientRect();
      const viewport = window.innerHeight;
      // Assembly starts when the section's top is halfway up the viewport and ends 65% of the way through
      // the pinned scroll, so the finished mark stays on screen for the rest of it.
      const start = viewport * 0.5;
      const end = -(rect.height - viewport) * 0.65;
      const progress = clamp((start - rect.top) / (start - end));
      let count = 0;
      PIECE_PARTS.forEach((piece, i) => {
        const t = clamp((progress - i * 0.12) / 0.64);
        const away = (1 - t) ** 3;
        const isLanded = t >= 1;
        const group = pieceRefs.current[i];
        if (group) {
          group.setAttribute(
            'transform',
            `translate(${(piece.dx * DISTANCE * away).toFixed(2)} ${(piece.dy * DISTANCE * away).toFixed(2)}) rotate(${(SPIN[i] * away).toFixed(2)} ${piece.cx} ${piece.cy})`,
          );
          group.setAttribute('data-landed', String(isLanded));
          // A travelling piece fades in as it nears its place; a landed one takes its brightness from the stylesheet.
          group.style.opacity = isLanded ? '' : (0.3 + 0.35 * (1 - away)).toFixed(3);
        }
        if (isLanded) count += 1;
      });
      section.style.setProperty('--assembled', (count === PIECE_PARTS.length ? 1 : progress * 0.5).toFixed(3));
      setLanded(count);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    schedule();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
    };
  }, []);

  const done = landed === PIECE_PARTS.length;

  return (
    <section ref={sectionRef} className={styles.assembly} aria-labelledby='assembly-title'>
      <div className={styles.stage}>
        <div className={styles.markWrap}>
          <svg className={styles.mark} viewBox='-20 0 430 430' aria-hidden='true' focusable='false'>
            <defs>
              {/* Horizontal scanlines in path units: a 1.6-unit line every 6 logo units. */}
              <pattern id={`${maskBase}-scan`} patternUnits='userSpaceOnUse' width={60} height={60}>
                <rect width={60} height={16} fill='var(--accent)' />
              </pattern>
              {PIECE_PARTS.map((piece, i) => (
                <g key={piece.d}>
                  {/* The piece minus the seam band: where the scanlines show. */}
                  <mask id={`${maskBase}-fill-${i}`} maskUnits='userSpaceOnUse' x={-20} y={0} width={430} height={430}>
                    <rect x={-20} width={430} height={430} fill='white' />
                    <path d={piece.d} transform={TRANSFORM} fill='none' stroke='black' strokeWidth={GAP_STROKE} strokeLinejoin='round' />
                  </mask>
                  {/* A thin band along the inner edge of the seam: the outline. */}
                  <mask id={`${maskBase}-line-${i}`} maskUnits='userSpaceOnUse' x={-20} y={0} width={430} height={430}>
                    <path d={piece.d} transform={TRANSFORM} fill='none' stroke='white' strokeWidth={GAP_STROKE + OUTLINE} strokeLinejoin='round' />
                    <path d={piece.d} transform={TRANSFORM} fill='none' stroke='black' strokeWidth={GAP_STROKE - OUTLINE} strokeLinejoin='round' />
                  </mask>
                </g>
              ))}
            </defs>
            {PIECE_PARTS.map((piece, i) => (
              <g
                key={piece.d}
                className={styles.piece}
                data-landed='true'
                ref={(node) => {
                  pieceRefs.current[i] = node;
                }}
              >
                <g mask={`url(#${maskBase}-fill-${i})`}>
                  <path className={styles.scan} d={piece.d} transform={TRANSFORM} fill={`url(#${maskBase}-scan)`} />
                </g>
                <g mask={`url(#${maskBase}-line-${i})`}>
                  <path d={piece.d} transform={TRANSFORM} fill='var(--accent)' />
                </g>
              </g>
            ))}
          </svg>
        </div>
        <div className={styles.caption}>
          <h2 id='assembly-title' className={styles.word}>
            modelswarm
          </h2>
          <p className={styles.definition}>
            <span className={styles.pos}>noun</span> Open-weight AI models, distributed by a swarm of peers as in a BitTorrent swarm.
          </p>
          <p className={styles.detail}>Each file arrives in pieces from whoever has it, and every piece is checked against the publisher's signed release as it lands.</p>
          <p className={styles.counter} data-done={done} aria-hidden='true'>
            pieces {landed}/{PIECE_PARTS.length}
            {done ? ' verified' : ''}
          </p>
        </div>
      </div>
    </section>
  );
}

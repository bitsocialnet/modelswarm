import { useEffect, useLayoutEffect, useReducer, useRef, useState, type CSSProperties } from 'react';
import styles from './pull-terminal.module.css';
import { COMMAND, buildTimeline, finalState, initialState, reducer, region, type Line, type Phase } from './timeline';

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'idle',
  resolving: 'resolving',
  pulling: 'pulling',
  fault: 'bad piece',
  done: 'done',
};

// The sequence is seeded, so it is the same on every visit and can be built once.
const TIMELINE = buildTimeline();

const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Block glyphs are drawn as boxes one cell wide each: the page font has none,
// and a fallback font's glyph widths would break the character grid.
const BLOCKS = /^[█░]+$/;

function Text({ line }: { line: Line }) {
  return line.map((segment, i) =>
    BLOCKS.test(segment.text) ? (
      <span key={i} className={styles.block} data-tone={segment.tone} style={{ width: `${segment.text.length}ch` }} />
    ) : (
      <span key={i} data-tone={segment.tone}>
        {segment.text}
      </span>
    ),
  );
}

export function PullTerminal() {
  const [reduced] = useState(prefersReducedMotion);
  const [run, setRun] = useState(0);
  const [visible, setVisible] = useState(false);
  // A terminal's size decides its map width and where long lines wrap, as in the CLI.
  const [size, setSize] = useState({ columns: 72, rows: 24 });
  const windowRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const probeRef = useRef<HTMLSpanElement>(null);
  const termRef = useRef<HTMLDivElement>(null);
  const [state, dispatch] = useReducer(reducer, TIMELINE, (events) => (reduced ? finalState(events) : initialState()));

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const probe = probeRef.current;
    if (!viewport || !probe) return;
    const measure = () => {
      const cell = probe.getBoundingClientRect().width / 10;
      const style = getComputedStyle(viewport);
      const width = viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      if (!cell) return;
      const columns = Math.max(24, Math.floor(width / cell));
      setSize({ columns, rows: columns >= 60 ? 24 : 30 });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    // The probe resizes when the web font replaces the fallback font.
    observer.observe(probe);
    return () => observer.disconnect();
  }, []);

  // Keep the newest line in view once the output outgrows the terminal, as a terminal scrolls.
  useLayoutEffect(() => {
    const term = termRef.current;
    if (term) term.scrollTop = term.scrollHeight;
  });

  // Start when the terminal is on screen, so on phones it does not finish before anyone scrolls to it.
  useEffect(() => {
    const node = windowRef.current;
    if (!node || reduced) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [reduced]);

  useEffect(() => {
    if (reduced || !visible) return;
    const timers = TIMELINE.map((event) => window.setTimeout(() => dispatch(event.action), event.at));
    return () => timers.forEach(window.clearTimeout);
  }, [reduced, visible, run]);

  const replay = () => {
    dispatch({ type: 'reset' });
    setRun((n) => n + 1);
  };

  const typing = state.typed < COMMAND.length;
  const live = region(state, size.columns, size.rows);

  return (
    <figure className={styles.figure}>
      <div ref={windowRef} className={styles.window} aria-hidden='true'>
        <div className={styles.bar}>
          <span className={styles.path}>~/models</span>
          <span className={styles.phase} data-phase={state.phase}>
            {PHASE_LABEL[state.phase]}
          </span>
        </div>

        <div ref={viewportRef} className={styles.screen}>
          <span ref={probeRef} className={styles.probe}>
            0000000000
          </span>
          <div
            ref={termRef}
            className={styles.term}
            style={{ '--columns': size.columns, '--rows': size.rows } as CSSProperties}
          >
            <p className={styles.wrap}>
              <span className={styles.prompt}>$</span> {COMMAND.slice(0, state.typed)}
              {typing && <span className={styles.cursor} />}
            </p>
            {state.transient && (
              <p className={styles.clip} data-tone='dim'>
                {state.transient}
              </p>
            )}
            {state.lasting.map((line, i) => (
              <p key={i} className={styles.wrap}>
                <Text line={line} />
              </p>
            ))}
            {live && (
              <>
                <p className={styles.clip}>
                  <Text line={live.title} />
                </p>
                {live.map.map((row, i) => (
                  <p key={i} className={styles.clip}>
                    {row.map((cell, j) => (
                      <span key={j} className={styles.cell} data-cell={cell} />
                    ))}
                  </p>
                ))}
                {live.log.map((line, i) => (
                  <p key={i} className={styles.clip}>
                    <Text line={line} />
                  </p>
                ))}
                {live.sources.map((line, i) => (
                  <p key={i} className={styles.clip}>
                    <Text line={line} />
                  </p>
                ))}
                <p className={styles.clip}>
                  <Text line={live.status} />
                </p>
              </>
            )}
            {state.prompt && (
              <p className={styles.wrap}>
                <span className={styles.prompt}>$</span> <span className={styles.cursor} />
              </p>
            )}
          </div>
        </div>
      </div>

      <figcaption className={styles.caption}>
        The terminal view of <code>modelswarm pull</code>, replayed with an example release and example sources. Pieces arrive from a peer and two HTTP sources
        together; a piece that fails its hash check is discarded, the source that sent it is dropped, and the piece is fetched again.{' '}
        {state.phase === 'done' && !reduced && (
          <button type='button' className={styles.replay} onClick={replay}>
            Play again
          </button>
        )}
      </figcaption>
    </figure>
  );
}

import { useEffect, useReducer, useRef, useState } from 'react';
import styles from './pull-terminal.module.css';
import { COMMAND, SOURCES, TOTAL, buildTimeline, finalState, initialState, reducer, type Phase } from './timeline';

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'idle',
  resolving: 'resolving',
  pulling: 'pulling',
  fault: 'bad piece',
  done: 'seeding',
};

// The sequence is seeded, so it is the same on every visit and can be built once.
const TIMELINE = buildTimeline();

const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function PullTerminal() {
  const [reduced] = useState(prefersReducedMotion);
  const [run, setRun] = useState(0);
  const [visible, setVisible] = useState(false);
  const windowRef = useRef<HTMLDivElement>(null);
  const [state, dispatch] = useReducer(reducer, TIMELINE, (events) => (reduced ? finalState(events) : initialState()));

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

  const done = state.phase === 'done';
  const typing = state.typed < COMMAND.length;

  return (
    <figure className={styles.figure}>
      <div ref={windowRef} className={styles.window} aria-hidden='true'>
        <div className={styles.bar}>
          <span className={styles.path}>~/models</span>
          <span className={styles.phase} data-phase={state.phase}>
            {PHASE_LABEL[state.phase]}
          </span>
        </div>

        <div className={styles.screen}>
          <p className={styles.line}>
            <span className={styles.prompt}>$</span> {COMMAND.slice(0, state.typed)}
            {typing && <span className={styles.cursor} />}
          </p>

          <dl className={styles.intro}>
            <div data-shown={state.intro >= 1}>
              <dt>release</dt>
              <dd>
                example-7b-instruct.Q4_K_M.gguf <span className={styles.dim}>4.07 GiB</span>
              </dd>
            </div>
            <div data-shown={state.intro >= 2}>
              <dt>publisher</dt>
              <dd>
                12D3KooWQx…r7Fm <span className={styles.good}>signature valid</span>
              </dd>
            </div>
            <div data-shown={state.intro >= 3}>
              <dt>pieces</dt>
              <dd>{TOTAL}, each checked against the signed pieces root</dd>
            </div>
          </dl>

          <div className={styles.map}>
            {state.pieces.map((piece, i) => (
              <span key={i} className={styles.piece} data-state={piece} />
            ))}
          </div>

          <ol className={styles.log}>
            {state.log.map((line) => (
              <li key={line.id} data-kind={line.kind}>
                {line.text}
              </li>
            ))}
          </ol>

          <ul className={styles.sources}>
            {SOURCES.map((name, i) => {
              const dropped = state.dropped && i === SOURCES.length - 1;
              return (
                <li key={name} data-dropped={dropped}>
                  <span className={styles.sourceName}>{name}</span>
                  <span className={styles.meter}>
                    <span style={{ width: `${Math.min(100, (state.counts[i] / TOTAL) * 250)}%` }} />
                  </span>
                  <span className={styles.count}>{dropped ? 'dropped' : state.counts[i]}</span>
                </li>
              );
            })}
          </ul>

          <p className={styles.status} data-done={done}>
            {done ? `${TOTAL}/${TOTAL} verified. Seeding to the swarm.` : `${state.verified}/${TOTAL} verified`}
          </p>
          <p className={styles.line} data-shown={done}>
            <span className={styles.prompt}>$</span> <span className={styles.cursor} />
          </p>
        </div>
      </div>

      <figcaption className={styles.caption}>
        An illustration of how a download would work: pieces arrive from torrent peers and HTTP mirrors together, and a piece that fails its check is thrown away and
        fetched from another source.{' '}
        {done && !reduced && (
          <button type='button' className={styles.replay} onClick={replay}>
            Play again
          </button>
        )}
      </figcaption>
    </figure>
  );
}

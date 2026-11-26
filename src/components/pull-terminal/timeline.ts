// The hero replays the live view that `modelswarm pull` draws on a terminal
// (cli/src/modelswarm/view.py). The release and its sources are examples; the
// layout, wording and sequence follow the CLI. Pieces from a peer and two HTTP
// sources are verified as they arrive, a piece that fails its hash is discarded,
// libtorrent drops the source that sent it, and the piece is fetched again.

const PUBLISHER = '12D3KooWQxe4Ab9vNcY3TsPr2mKfLd8HhGjW6uZqRy5EoVtXr7Fm';
const RELEASE = 'example/example-0.5b-instruct';
const VERSION = 'v1';
const FILE = 'example-0.5b-instruct.Q4_K_M.gguf';
const SIZE = 267_911_168; // 255.5 MiB, so 256 pieces of 1 MiB
const PIECE_SIZE = 1_048_576;
const DIGEST = '9c41e0a5d2f7c3b1e8a4d6f2b0c9e7a5d3f1b8c6e4a2d0f9b7c5e3a1d8f6b4c2';
const SNAPSHOT = `/home/you/.cache/modelswarm/hub/models--example--example-0.5b-instruct/snapshots/${DIGEST.slice(0, 40)}`;
const SECONDS = 7.4;

export const COMMAND = `modelswarm pull 'pkc://${PUBLISHER}/${RELEASE}@${VERSION}'`;
const TOTAL = 256;
const SOURCES = ['peer 159.195.210.230:51413', 'huggingface.co', 'mirror.example.org'] as const;

const BAD_PIECE = 98;
const BAD_AT = 84; // position in the arrival order where the bad piece shows up
const REFETCH_AT = 112;
const BAD_SOURCE = 2;
const REFETCH_SOURCE = 0;

// view.py constants.
const LABEL = 11;
const LOG_LINES = 4;
const SOURCE_ROWS = 5;
const MAP_COLUMNS = 32;
const MAP_ROWS = 8;
const BOX_WIDTH = 2 * MAP_COLUMNS - 1 + 6;
const FRESH_MS = 600;

type Tone = 'dim' | 'ok' | 'fail' | 'warn' | 'bold' | 'strike';
// `spin` stands for the braille spinner, which the CLI advances on every redraw.
type Segment = { text: string; tone?: Tone; spin?: boolean };
export type Line = Segment[];
export type Phase = 'idle' | 'resolving' | 'pulling' | 'fault' | 'done';
export type Cell = 'none' | 'part' | 'full' | 'fresh' | 'bad';
export type Bar = { width: number; filled: number; half: boolean; dropped: boolean };
export type SourceRow = { name: string; tone?: Tone; bar: Bar | null; count: Segment };

type FileProgress = {
  verified: boolean[];
  done: number;
  bad: number[];
  failed: number[];
  fresh: [number, number][];
  sources: [string, number][];
  dropped: string[];
  log: [number, string][];
  ready: boolean;
  rate: number | null;
};

type State = {
  typed: number;
  phase: Phase;
  transient: string | null;
  lasting: Line[];
  file: FileProgress | null;
  prompt: boolean;
};

type Action =
  | { type: 'reset' }
  | { type: 'type'; chars: number }
  | { type: 'enter' }
  | { type: 'header' }
  | { type: 'start' }
  | { type: 'ready' }
  | { type: 'verify'; piece: number; source: number; at: number }
  | { type: 'fail'; piece: number; source: number }
  | { type: 'drop'; source: number }
  | { type: 'rate'; bytes: number }
  | { type: 'complete' }
  | { type: 'finish' };

export const initialState = (): State => ({ typed: 0, phase: 'idle', transient: null, lasting: [], file: null, prompt: false });

// Python's round() and format() round halves to even; the meters and times must match it.
const roundHalfEven = (value: number) => {
  const floor = Math.floor(value);
  if (value - floor !== 0.5) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
};

const sizeText = (size: number) => {
  for (const [unit, scale] of [
    ['GB', 1e9],
    ['MB', 1e6],
    ['kB', 1e3],
  ] as const) {
    if (size >= scale) return `${(size / scale).toFixed(1)} ${unit}`;
  }
  return `${size} B`;
};

const durationText = (seconds: number) => {
  if (seconds < 1) return '<1 s';
  if (seconds < 60) return `${roundHalfEven(seconds)} s`;
  if (seconds < 3600) return `${roundHalfEven(seconds / 60)} min`;
  return `${Math.floor(seconds / 3600)} h ${roundHalfEven((seconds % 3600) / 60)} min`;
};

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;
const pieceLabel = (piece: number) => `#${String(piece).padStart(Math.max(3, String(TOTAL - 1).length), '0')}`;
const shortKey = (value: string) => (value.length <= 20 ? value : `${value.slice(0, 12)}…${value.slice(-4)}`);
const labelled = (label: string, ...segments: Line): Line => [{ text: label.padEnd(LABEL), tone: 'dim' }, ...segments];
const cellOf = (piece: number, cells: number) => Math.floor(((piece + 1) * cells - 1) / TOTAL);

const HEADER: Line[] = [
  labelled('release', { text: `${RELEASE} ${VERSION}`, tone: 'bold' }, { text: ' · apache-2.0', tone: 'dim' }),
  labelled('publisher', { text: shortKey(PUBLISHER) }, { text: ' ✓ signature valid', tone: 'ok' }),
  labelled('manifest', { text: DIGEST.slice(0, 12) }, { text: ' ✓ matches the signed release', tone: 'ok' }),
  labelled('files', { text: `1 selected · ${sizeText(SIZE)}` }),
  [],
];

const newFile = (): FileProgress => ({
  verified: Array<boolean>(TOTAL).fill(false),
  done: 0,
  bad: [],
  failed: [],
  fresh: [],
  sources: [],
  dropped: [],
  log: [],
  ready: false,
  rate: null,
});

export function reducer(state: State, action: Action): State {
  const file = state.file;
  switch (action.type) {
    case 'reset':
      return initialState();
    case 'type':
      return { ...state, typed: action.chars };
    case 'enter':
      return { ...state, phase: 'resolving', transient: `resolving pkc://${PUBLISHER}/${RELEASE}@${VERSION}` };
    case 'header':
      return { ...state, transient: null, lasting: [...state.lasting, ...HEADER] };
    case 'start':
      return { ...state, phase: 'pulling', file: newFile() };
    case 'ready':
      return file ? { ...state, file: { ...file, ready: true } } : state;
    case 'verify': {
      if (!file) return state;
      const name = SOURCES[action.source];
      const verified = file.verified.slice();
      let { done, sources } = file;
      if (!verified[action.piece]) {
        verified[action.piece] = true;
        done += 1;
        const known = sources.some(([source]) => source === name);
        sources = known ? sources.map(([source, count]) => [source, source === name ? count + 1 : count]) : [...sources, [name, 1]];
      }
      const bad = file.bad.filter((piece) => piece !== action.piece);
      const fresh: [number, number][] = [...file.fresh.filter(([, at]) => action.at - at < FRESH_MS), [action.piece, action.at]];
      const next = { ...file, verified, done, sources, bad, fresh };
      const phase = bad.length ? 'fault' : 'pulling';
      if (file.failed.includes(action.piece)) {
        return {
          ...state,
          phase,
          lasting: [...state.lasting, [{ text: '✓ ', tone: 'ok' }, { text: `piece ${pieceLabel(action.piece)} fetched again from ` }, { text: name, tone: 'bold' }]],
          file: { ...next, failed: file.failed.filter((piece) => piece !== action.piece) },
        };
      }
      return { ...state, phase, file: { ...next, log: [...file.log, [action.piece, name] as [number, string]].slice(-LOG_LINES) } };
    }
    case 'fail':
      if (!file) return state;
      return {
        ...state,
        phase: 'fault',
        lasting: [
          ...state.lasting,
          [
            { text: '✗ ', tone: 'fail' },
            { text: `piece ${pieceLabel(action.piece)} from ` },
            { text: SOURCES[action.source], tone: 'bold' },
            { text: ' failed its hash check and was discarded', tone: 'fail' },
          ],
        ],
        file: { ...file, bad: [...file.bad, action.piece], failed: [...file.failed, action.piece] },
      };
    case 'drop': {
      if (!file) return state;
      const name = SOURCES[action.source];
      const sources: [string, number][] = file.sources.some(([source]) => source === name) ? file.sources : [...file.sources, [name, 0]];
      return {
        ...state,
        lasting: [...state.lasting, [{ text: '! ', tone: 'warn' }, { text: 'dropped ' }, { text: name, tone: 'bold' }, { text: ' for sending a bad piece', tone: 'dim' }]],
        file: { ...file, sources, dropped: [...file.dropped, name] },
      };
    }
    case 'rate':
      return file ? { ...state, file: { ...file, rate: action.bytes } } : state;
    case 'complete': {
      if (!file) return state;
      const lines: Line[] = [
        [
          { text: '✓ ', tone: 'ok' },
          { text: FILE, tone: 'bold' },
          { text: `  ${sizeText(SIZE)} · ${plural(TOTAL, 'piece')} · ${SECONDS.toFixed(1)} s`, tone: 'dim' },
        ],
      ];
      const counted = file.sources.filter(([, count]) => count > 0);
      if (counted.length) {
        const named = counted.map(([name, count]) => (counted.length === 1 ? name : `${name} (${count})`)).join(', ');
        lines.push([{ text: '  from ', tone: 'dim' }, { text: named, tone: 'dim' }]);
      }
      return { ...state, file: null, lasting: [...state.lasting, ...lines] };
    }
    case 'finish':
      return {
        ...state,
        phase: 'done',
        prompt: true,
        lasting: [
          ...state.lasting,
          [],
          labelled('verified', { text: '✓ ', tone: 'ok' }, { text: plural(1, 'file'), tone: 'bold' }),
          labelled('snapshot', { text: SNAPSHOT }),
        ],
      };
  }
}

export type Box = {
  width: number;
  inner: number;
  title: Line;
  fill: number;
  phase: Line;
  map: Cell[][];
  log: Line[];
  sources: SourceRow[];
  status: Line;
};

const fit = (segments: Line, width: number): Line => {
  const out: Line = [];
  let used = 0;
  for (const segment of segments) {
    if (used + segment.text.length > width) {
      out.push({ ...segment, text: `${segment.text.slice(0, Math.max(0, width - used - 1))}…` });
      return out;
    }
    out.push(segment);
    used += segment.text.length;
  }
  return out;
};

const length = (line: Line) => line.reduce((sum, segment) => sum + segment.text.length, 0);

/** The live box view.py redraws in place, for a terminal of the given size. */
export function region(state: State, columns: number, rows: number): Box | null {
  const file = state.file;
  if (!file) return null;
  const width = Math.min(BOX_WIDTH, Math.max(24, columns - 1));
  const inner = width - 4;
  const now = file.fresh.length ? file.fresh[file.fresh.length - 1][1] : 0;

  const phase: Line = !file.ready
    ? [{ text: '· checking', tone: 'dim' }]
    : file.bad.length
      ? [{ text: '✗ bad piece', tone: 'fail' }]
      : [
          { text: '⠋', tone: 'ok', spin: true },
          { text: ' pulling', tone: 'ok' },
        ];
  const title = fit(
    [
      { text: FILE, tone: 'bold' },
      { text: ` · ${sizeText(SIZE)}`, tone: 'dim' },
    ],
    Math.max(1, width - 9 - length(phase)),
  );
  const fill = width - 8 - length(title) - length(phase);

  // Keep the busiest sources, in arrival order, and fold the rest into one row.
  let shown = file.sources;
  let rest: [string, number][] = [];
  const room = Math.max(1, Math.min(SOURCE_ROWS, rows - 13));
  if (shown.length > room) {
    const keep = new Set(
      [...shown]
        .sort((a, b) => b[1] - a[1])
        .slice(0, room - 1)
        .map(([name]) => name),
    );
    rest = shown.filter(([name]) => !keep.has(name));
    shown = shown.filter(([name]) => keep.has(name));
  }
  const folded = rest.length ? `+${rest.length} more` : null;
  const listed: [string, number][] = folded ? [...shown, [folded, rest.reduce((sum, [, count]) => sum + count, 0)]] : shown;

  const mapColumns = Math.max(1, Math.min(MAP_COLUMNS, Math.floor((inner + 1) / 2)));
  const mapRows = Math.max(1, Math.min(MAP_ROWS, rows - 12 - listed.length));
  const cells = Math.min(TOTAL, mapColumns * mapRows);
  const bad = new Set(file.bad.map((piece) => cellOf(piece, cells)));
  const fresh = new Set(file.fresh.filter(([, at]) => now - at < FRESH_MS).map(([piece]) => cellOf(piece, cells)));
  const map: Cell[][] = [];
  for (let cell = 0; cell < cells; cell++) {
    const start = Math.floor((cell * TOTAL) / cells);
    const end = Math.floor(((cell + 1) * TOTAL) / cells);
    let done = 0;
    for (let piece = start; piece < end; piece++) if (file.verified[piece]) done++;
    const value: Cell = bad.has(cell) ? 'bad' : fresh.has(cell) ? 'fresh' : done === end - start ? 'full' : done ? 'part' : 'none';
    if (cell % mapColumns === 0) map.push([]);
    map[map.length - 1].push(value);
  }

  const log: Line[] = file.log.map(([piece, source]) => [{ text: '✓ ', tone: 'ok' }, { text: `${pieceLabel(piece)}  ` }, { text: source, tone: 'dim' }]);
  while (log.length < LOG_LINES) log.push([]);

  const nameWidth = Math.min(28, Math.max(0, ...listed.map(([name]) => name.length)));
  const barWidth = inner - nameWidth - 11;
  const sources = listed.map(([name, count]): SourceRow => {
    const dropped = file.dropped.includes(name);
    const cellsFilled = (count / TOTAL) * barWidth;
    return {
      name: name.slice(0, nameWidth).padEnd(nameWidth),
      tone: dropped ? 'strike' : name === folded ? 'dim' : undefined,
      bar: barWidth >= 6 ? { width: barWidth, filled: Math.floor(cellsFilled), half: cellsFilled - Math.floor(cellsFilled) >= 0.5, dropped } : null,
      count: dropped ? { text: 'dropped'.padStart(9), tone: 'fail' } : { text: String(count).padStart(9) },
    };
  });

  const status: Line = !file.ready
    ? [{ text: 'checking data already on disk', tone: 'dim' }]
    : [
        { text: `${file.done}/${TOTAL}`, tone: 'bold' },
        { text: ' verified' },
        ...(file.rate === null
          ? []
          : [
              { text: ` · ${sizeText(file.rate)}/s`, tone: 'dim' as const },
              ...(file.done < TOTAL ? [{ text: ` · ${durationText(((TOTAL - file.done) * PIECE_SIZE) / file.rate)} left`, tone: 'dim' as const }] : []),
            ]),
      ];

  return { width, inner, title, fill, phase, map, log, sources, status };
}

// Small seeded generator so every visit shows the same sequence.
const seeded = (seed: number) => () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};

type Event = { at: number; action: Action };

export function buildTimeline(): Event[] {
  const random = seeded(11);
  const events: Event[] = [];
  let clock = 400;

  for (let i = 1; i <= COMMAND.length; i++) {
    events.push({ at: clock, action: { type: 'type', chars: i } });
    clock += 12 + Math.floor(random() * 16);
  }
  clock += 350;
  events.push({ at: clock, action: { type: 'enter' } });
  clock += 1100;
  events.push({ at: clock, action: { type: 'header' } });
  clock += 350;
  events.push({ at: clock, action: { type: 'start' } });
  clock += 300;
  events.push({ at: clock, action: { type: 'ready' } });
  clock += 250;

  const order: number[] = [];
  for (let i = 0; i < TOTAL; i++) if (i !== BAD_PIECE) order.push(i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }

  const pick = (dropped: boolean) => {
    const roll = random();
    if (dropped) return roll < 0.56 ? 0 : 1;
    return roll < 0.44 ? 0 : roll < 0.76 ? 1 : 2;
  };

  order.forEach((piece, step) => {
    if (step === BAD_AT) {
      // libtorrent reports the failure and the ban together; the view prints both at once.
      events.push({ at: clock, action: { type: 'fail', piece: BAD_PIECE, source: BAD_SOURCE } });
      events.push({ at: clock, action: { type: 'drop', source: BAD_SOURCE } });
      clock += 1700;
    }
    if (step === REFETCH_AT) {
      events.push({ at: clock, action: { type: 'verify', piece: BAD_PIECE, source: REFETCH_SOURCE, at: clock } });
      clock += 1000;
    }
    if (step % 30 === 29) {
      events.push({ at: clock, action: { type: 'rate', bytes: 31e6 + Math.floor(random() * 11e6) } });
    }
    events.push({ at: clock, action: { type: 'verify', piece, source: pick(step > BAD_AT), at: clock } });
    clock += 18 + Math.floor(random() * 10);
  });

  clock += 300;
  events.push({ at: clock, action: { type: 'complete' } });
  clock += 250;
  events.push({ at: clock, action: { type: 'finish' } });
  return events;
}

export const finalState = (timeline: Event[]) => timeline.reduce((state, event) => reducer(state, event.action), initialState());

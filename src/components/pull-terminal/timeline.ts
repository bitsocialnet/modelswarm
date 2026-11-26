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
const LABEL = 10;
const LOG_LINES = 4;
const MAP_COLUMNS = 64;
const MAP_ROWS = 8;
const METER = 12;

type Tone = 'dim' | 'ok' | 'fail' | 'warn' | 'bold';
type Segment = { text: string; tone?: Tone };
export type Line = Segment[];
export type Phase = 'idle' | 'resolving' | 'pulling' | 'fault' | 'done';
type Cell = 'none' | 'part' | 'full' | 'bad';

type FileProgress = {
  verified: boolean[];
  done: number;
  bad: number[];
  failed: number[];
  sources: [string, number][];
  dropped: string[];
  log: Line[];
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
  | { type: 'verify'; piece: number; source: number }
  | { type: 'fail'; piece: number; source: number }
  | { type: 'drop'; source: number }
  | { type: 'rate'; bytes: number }
  | { type: 'complete' }
  | { type: 'finish' };

export const initialState = (): State => ({ typed: 0, phase: 'idle', transient: null, lasting: [], file: null, prompt: false });

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

// Python's round() rounds halves to even; the meters must match it.
const roundHalfEven = (value: number) => {
  const floor = Math.floor(value);
  const rest = value - floor;
  if (rest !== 0.5) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
};

const pieceLabel = (piece: number) => `#${String(piece).padStart(Math.max(3, String(TOTAL - 1).length), '0')}`;
const shortKey = (value: string) => (value.length <= 20 ? value : `${value.slice(0, 12)}…${value.slice(-4)}`);
const labelled = (label: string, ...segments: Line): Line => [{ text: label.padEnd(LABEL), tone: 'dim' }, ...segments];

const HEADER: Line[] = [
  labelled('release', { text: `${RELEASE} ${VERSION}`, tone: 'bold' }, { text: '  apache-2.0', tone: 'dim' }),
  labelled('publisher', { text: shortKey(PUBLISHER) }, { text: '  signature valid', tone: 'ok' }),
  labelled('manifest', { text: DIGEST.slice(0, 12) }, { text: '  matches the signed release', tone: 'ok' }),
  labelled('files', { text: `1 selected, ${sizeText(SIZE)}` }),
  [],
];

const newFile = (): FileProgress => ({
  verified: Array<boolean>(TOTAL).fill(false),
  done: 0,
  bad: [],
  failed: [],
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
      const line: Line = [{ text: 'ok    ', tone: 'ok' }, { text: `${pieceLabel(action.piece)}  ` }, { text: name, tone: 'dim' }];
      const next = { ...file, verified, done, sources, bad: file.bad.filter((piece) => piece !== action.piece) };
      if (file.failed.includes(action.piece)) {
        return {
          ...state,
          phase: 'pulling',
          lasting: [...state.lasting, [...line, { text: '  fetched again', tone: 'ok' }]],
          file: { ...next, failed: file.failed.filter((piece) => piece !== action.piece) },
        };
      }
      return { ...state, phase: 'pulling', file: { ...next, log: [...file.log, line].slice(-LOG_LINES) } };
    }
    case 'fail':
      if (!file) return state;
      return {
        ...state,
        phase: 'fault',
        lasting: [
          ...state.lasting,
          [
            { text: 'fail  ', tone: 'fail' },
            { text: `${pieceLabel(action.piece)}  ` },
            { text: SOURCES[action.source] },
            { text: '  hash mismatch, piece discarded', tone: 'fail' },
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
        lasting: [...state.lasting, [{ text: 'drop  ', tone: 'warn' }, { text: name }, { text: '  sent a bad piece; no more requests', tone: 'dim' }]],
        file: { ...file, sources, dropped: [...file.dropped, name] },
      };
    }
    case 'rate':
      return file ? { ...state, file: { ...file, rate: action.bytes } } : state;
    case 'complete': {
      if (!file) return state;
      const counted = file.sources.filter(([, count]) => count > 0);
      const named = counted.length ? `  ${counted.map(([name, count]) => (counted.length === 1 ? name : `${name} ${count}`)).join(', ')}` : '';
      const summary: Line = [
        { text: 'ok    ', tone: 'ok' },
        { text: FILE, tone: 'bold' },
        { text: `  ${sizeText(SIZE)}  ${TOTAL} pieces in ${SECONDS.toFixed(1)} s`, tone: 'dim' },
        { text: named, tone: 'dim' },
      ];
      return { ...state, file: null, lasting: [...state.lasting, summary] };
    }
    case 'finish':
      return {
        ...state,
        phase: 'done',
        prompt: true,
        lasting: [...state.lasting, [], labelled('verified', { text: '1 file' }), labelled('snapshot', { text: SNAPSHOT })],
      };
  }
}

/** The live region view.py redraws in place, for a terminal of the given size. */
export function region(state: State, columns: number, rows: number): { title: Line; map: Cell[][]; log: Line[]; sources: Line[]; status: Line } | null {
  const file = state.file;
  if (!file) return null;
  const width = Math.max(20, columns - 1);
  const mapColumns = Math.min(MAP_COLUMNS, width);
  const cells = Math.min(TOTAL, mapColumns * Math.max(1, Math.min(MAP_ROWS, rows - 12)));
  const map: Cell[][] = [];
  for (let cell = 0; cell < cells; cell++) {
    const start = Math.floor((cell * TOTAL) / cells);
    const end = Math.floor(((cell + 1) * TOTAL) / cells);
    let done = 0;
    for (let piece = start; piece < end; piece++) if (file.verified[piece]) done++;
    const state: Cell = file.bad.some((piece) => start <= piece && piece < end) ? 'bad' : done === end - start ? 'full' : done ? 'part' : 'none';
    if (cell % mapColumns === 0) map.push([]);
    map[map.length - 1].push(state);
  }
  const nameWidth = Math.min(32, Math.max(0, ...file.sources.map(([name]) => name.length)));
  const sources = file.sources.map(([name, count]): Line => {
    const filled = Math.min(METER, roundHalfEven((METER * count) / TOTAL));
    return [
      { text: `${name.slice(0, nameWidth).padEnd(nameWidth)}  ` },
      { text: '█'.repeat(filled), tone: 'ok' },
      { text: '░'.repeat(METER - filled), tone: 'dim' },
      file.dropped.includes(name) ? { text: '  dropped', tone: 'fail' } : { text: `  ${count}` },
    ];
  });
  const status: Line = !file.ready
    ? [{ text: 'checking staged data', tone: 'dim' }]
    : [{ text: `${file.done}/${TOTAL} verified` }, ...(file.rate === null ? [] : [{ text: `  ${sizeText(file.rate)}/s`, tone: 'dim' as const }])];
  return { title: [{ text: FILE, tone: 'bold' }, { text: `  ${sizeText(SIZE)}  ${TOTAL} pieces`, tone: 'dim' }], map, log: file.log, sources, status };
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
      events.push({ at: clock, action: { type: 'verify', piece: BAD_PIECE, source: REFETCH_SOURCE } });
      clock += 1000;
    }
    if (step % 30 === 29) {
      events.push({ at: clock, action: { type: 'rate', bytes: 31e6 + Math.floor(random() * 11e6) } });
    }
    events.push({ at: clock, action: { type: 'verify', piece, source: pick(step > BAD_AT) } });
    clock += 18 + Math.floor(random() * 10);
  });

  clock += 300;
  events.push({ at: clock, action: { type: 'complete' } });
  clock += 250;
  events.push({ at: clock, action: { type: 'finish' } });
  return events;
}

export const finalState = (timeline: Event[]) => timeline.reduce((state, event) => reducer(state, event.action), initialState());

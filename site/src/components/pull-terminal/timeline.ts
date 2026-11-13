// The hero illustration: `modelswarm pull` fetching one file piece by piece from several sources.
// One piece fails its check, its source is dropped, and the piece is fetched again from a peer.

export const COMMAND = 'modelswarm pull example/example-7b-instruct';
export const TOTAL = 128;
export const SOURCES = ['peer lisbon', 'peer osaka', 'huggingface.co', 'mirror.example.org'] as const;

const BAD_PIECE = 67;
const BAD_AT = 66; // position in the arrival order where the bad piece shows up
const BAD_SOURCE = 3;
const REFETCH_SOURCE = 0;
const LOG_LINES = 4;

export type PieceState = 'empty' | 'fresh' | 'ok' | 'bad';
export type Phase = 'idle' | 'resolving' | 'pulling' | 'fault' | 'done';
export type LogLine = { id: number; kind: 'ok' | 'fail' | 'drop'; text: string };

export type State = {
  typed: number;
  intro: number;
  phase: Phase;
  pieces: PieceState[];
  counts: number[];
  dropped: boolean;
  verified: number;
  log: LogLine[];
  logId: number;
};

export type Action =
  | { type: 'reset' }
  | { type: 'type'; chars: number }
  | { type: 'intro'; lines: number }
  | { type: 'arrive'; piece: number }
  | { type: 'verify'; piece: number; source: number; note?: string }
  | { type: 'fail'; piece: number; source: number }
  | { type: 'drop'; source: number }
  | { type: 'done' };

export const initialState = (): State => ({
  typed: 0,
  intro: 0,
  phase: 'idle',
  pieces: Array<PieceState>(TOTAL).fill('empty'),
  counts: SOURCES.map(() => 0),
  dropped: false,
  verified: 0,
  log: [],
  logId: 0,
});

const pad = (n: number) => `#${String(n).padStart(3, '0')}`;

const withLog = (state: State, kind: LogLine['kind'], text: string): Pick<State, 'log' | 'logId'> => ({
  log: [...state.log, { id: state.logId, kind, text }].slice(-LOG_LINES),
  logId: state.logId + 1,
});

const setPiece = (pieces: PieceState[], piece: number, value: PieceState) => {
  const next = pieces.slice();
  next[piece] = value;
  return next;
};

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'reset':
      return initialState();
    case 'type':
      return { ...state, typed: action.chars };
    case 'intro':
      return { ...state, intro: action.lines, phase: 'resolving' };
    case 'arrive':
      return { ...state, phase: state.phase === 'fault' ? 'fault' : 'pulling', pieces: setPiece(state.pieces, action.piece, 'fresh') };
    case 'verify': {
      const counts = state.counts.slice();
      counts[action.source]++;
      return {
        ...state,
        phase: 'pulling',
        pieces: setPiece(state.pieces, action.piece, 'ok'),
        counts,
        verified: state.verified + 1,
        ...withLog(state, 'ok', `ok    ${pad(action.piece)}  ${SOURCES[action.source]}${action.note ? `  ${action.note}` : ''}`),
      };
    }
    case 'fail':
      return {
        ...state,
        phase: 'fault',
        pieces: setPiece(state.pieces, action.piece, 'bad'),
        ...withLog(state, 'fail', `fail  ${pad(action.piece)}  ${SOURCES[action.source]}  hash mismatch`),
      };
    case 'drop':
      return { ...state, dropped: true, ...withLog(state, 'drop', `drop  ${SOURCES[action.source]}  no more requests`) };
    case 'done':
      return { ...state, phase: 'done' };
  }
}

// Small seeded generator so every visit shows the same sequence.
const seeded = (seed: number) => () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296;
  return seed / 4294967296;
};

export type Event = { at: number; action: Action };

export function buildTimeline(): Event[] {
  const random = seeded(7);
  const events: Event[] = [];
  let clock = 400;

  for (let i = 1; i <= COMMAND.length; i++) {
    events.push({ at: clock, action: { type: 'type', chars: i } });
    clock += 24 + Math.floor(random() * 22);
  }
  clock += 450;
  for (let line = 1; line <= 3; line++) {
    events.push({ at: clock, action: { type: 'intro', lines: line } });
    clock += 380;
  }
  clock += 200;

  const order: number[] = [];
  for (let i = 0; i < TOTAL; i++) if (i !== BAD_PIECE) order.push(i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  order.splice(BAD_AT, 0, BAD_PIECE);

  order.forEach((piece, step) => {
    if (piece === BAD_PIECE) {
      events.push({ at: clock, action: { type: 'arrive', piece } });
      events.push({ at: clock + 160, action: { type: 'fail', piece, source: BAD_SOURCE } });
      clock += 1500;
      events.push({ at: clock, action: { type: 'drop', source: BAD_SOURCE } });
      clock += 900;
      events.push({ at: clock, action: { type: 'arrive', piece } });
      clock += 500;
      events.push({ at: clock, action: { type: 'verify', piece, source: REFETCH_SOURCE, note: 'fetched again' } });
      clock += 700;
      return;
    }
    const dropped = step > BAD_AT;
    const source = Math.floor(random() * (dropped ? SOURCES.length - 1 : SOURCES.length));
    events.push({ at: clock, action: { type: 'arrive', piece } });
    events.push({ at: clock + 150, action: { type: 'verify', piece, source } });
    clock += 38;
  });

  events.push({ at: clock + 400, action: { type: 'done' } });
  return events;
}

export const finalState = (timeline: Event[]) => timeline.reduce((state, event) => reducer(state, event.action), initialState());

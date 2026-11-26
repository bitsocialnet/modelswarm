export const REPO = 'https://github.com/bitsocialnet/modelswarm';
export const NEW_ISSUE = `${REPO}/issues/new`;
export const doc = (path: string) => `${REPO}/blob/master/${path}`;
// The original design ModelSwarm builds on.
export const HUGGINGSOCIAL = 'https://github.com/Rinse12/huggingsocial';

export type Part = {
  term: string;
  title: string;
  body: string;
};

export const PARTS: Part[] = [
  {
    term: 'publisher key',
    title: 'Publishers sign releases',
    body: "A release lives in its publisher's own profile, signed with a key the publisher holds. The same key covers every release, so a reader can tell a known publisher from an imitator.",
  },
  {
    term: 'bittorrent v2, web seeds',
    title: 'Seeders hold the weights',
    body: 'Files move over BitTorrent, with any HTTP mirror as an extra source. The public demo has a persistent seeder. The experimental CLI can upload pieces for the duration of a pull.',
  },
  {
    term: 'pieces root',
    title: 'Every piece is checked',
    body: 'The signed release carries a hash-tree root for each file. A corrupted or swapped piece is caught when it arrives, not at the end of a 40 GB download, whether it came from a peer or from a mirror.',
  },
  {
    term: 'hubs, crossposts',
    title: 'Hubs curate, and anyone can run one',
    body: "A hub is a community about a model family or a task. It lists releases and hosts the discussion under its own rules. It can drop a release from its board, but not from the publisher's profile or from other hubs.",
  },
  {
    term: 'HF_ENDPOINT',
    title: 'Use the Hugging Face SDK',
    body: 'Point `HF_ENDPOINT` at the local endpoint to download with the Hugging Face SDK. Compatibility with `transformers` and llama.cpp is still untested.',
  },
  {
    term: 'safetensors, gguf',
    title: 'Safe formats by default',
    body: 'A signature does not make a file harmless. Formats that only hold data, such as safetensors and GGUF, download normally. Files that can run code when loaded are flagged and need a confirmation.',
  },
];

export const COMPARE_COLUMNS = ['Hugging Face', 'Pirate Face', 'ModelSwarm'] as const;

// Pirate Face as its own site describes it (pirateface.co, and its CLI README, checked 2026-11-17).
export const COMPARE_SOURCE = 'Pirate Face as described on pirateface.co and in its CLI README on 17 November 2026.';

export const COMPARE_ROWS: { label: string; cells: [string, string, string] }[] = [
  {
    label: 'Where the files are',
    cells: ["Hugging Face's servers", 'Seeders, with Hugging Face as a web seed', 'Seeders, plus any HTTP mirror, including Hugging Face'],
  },
  {
    label: 'Who can delist a model',
    cells: [
      'Hugging Face',
      'Pirate Face, which runs the list. A copy of its index synced earlier still finds the model',
      'Nobody across the network. A hub can only drop it from its own board',
    ],
  },
  {
    label: 'Who published this file',
    cells: [
      'A Hugging Face account',
      'A Pirate Face handle, verified through the matching Hugging Face account',
      'A signing key, the same across every release by that publisher',
    ],
  },
  {
    label: 'When a swapped file is caught',
    cells: [
      'The host is trusted',
      "Each piece against the listed torrent's hashes, then each whole file against Hugging Face's SHA-256",
      'During the download, piece by piece, against the release its publisher signed',
    ],
  },
  { label: 'Where discussion happens', cells: ['Hugging Face', 'On Pirate Face', 'Peer-to-peer communities, each with its own rules'] },
  { label: 'Works with existing tools', cells: ['Yes', 'Yes, through its pip package for Python tools', 'Hugging Face SDK tested; other tools unverified'] },
];

// What no project that only moves files can add (README.md#nobody-runs-the-list).
export const ONLY_HERE: { title: string; body: string }[] = [
  {
    title: 'Nobody runs the list',
    body: "A release is a signed post in its publisher's own profile. No hub, indexer or company can remove it from there, and anyone can run an indexer over the same public data.",
  },
  {
    title: 'Nobody owns the communities',
    body: 'Hubs are Bitsocial communities. Anyone can create one, each sets its own rules, and the discussion about a model does not depend on one website staying online.',
  },
];

export type Step = {
  title: string;
  body: string;
  estimate: string;
  complete?: boolean;
};

export const STEPS: Step[] = [
  { title: 'Measurements', body: 'The engine and a direct public peer transfer are verified. Community scale and broader network tests remain.', estimate: '~1 week' },
  {
    title: 'Manifest and command line',
    body: 'Implemented: make, verify and pull unsigned manifests into a verified local cache.',
    estimate: 'Prototype complete',
    complete: true,
  },
  {
    title: 'The Hugging Face endpoint',
    body: 'Implemented for the SDK: local releases and verified public fallback. Other consumers remain.',
    estimate: 'SDK prototype complete',
  },
  {
    title: 'Publishing and reading releases',
    body: 'The public demo has a signed publisher profile, peer-only downloads and a release page. Hosted onboarding remains.',
    estimate: 'CLI prototype complete',
  },
  {
    title: 'Hubs and search',
    body: 'The self-hosted catalogue searches imported magnets and community releases. Browser posting and live search across several indexers are planned.',
    estimate: '2–3 weeks',
  },
  { title: 'Desktop client', body: 'One app with a node, a torrent engine and the local endpoint.', estimate: '3–4 weeks' },
];

// The step after which the tool is useful to one person with no network of publishers.
export const USEFUL_ALONE_AFTER = 3;

export const QUESTIONS = [
  { text: 'Who publishes first?', anchor: 'who-publishes-first' },
  { text: 'Who seeds a model nobody downloaded this month?', anchor: 'seeding' },
  { text: 'How does a reader tell a real publisher from an imitator?', anchor: 'names-and-impersonation' },
];

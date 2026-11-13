export const REPO = 'https://github.com/bitsocialnet/modelswarm';
export const NEW_ISSUE = `${REPO}/issues/new`;
export const doc = (path: string) => `${REPO}/blob/master/${path}`;
// The original design Modelswarm builds on.
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
    body: 'Files move over BitTorrent, with any HTTP mirror as an extra source. A file with seeders cannot be deleted by a host, and people who download a model seed it by default.',
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
    title: 'Existing tools keep working',
    body: 'A local endpoint speaks the Hugging Face API. Point `HF_ENDPOINT` at it and `transformers` or llama.cpp download through the swarm without changes.',
  },
  {
    term: 'safetensors, gguf',
    title: 'Safe formats by default',
    body: 'A signature does not make a file harmless. Formats that only hold data, such as safetensors and GGUF, download normally. Files that can run code when loaded are flagged and need a confirmation.',
  },
];

export const COMPARE_COLUMNS = ['Hugging Face', 'Pirate Face', 'Modelswarm'] as const;

// Pirate Face as its own site describes it (pirateface.co, checked 2026-11-13).
export const COMPARE_SOURCE = 'Pirate Face as described on pirateface.co in November 2026.';

export const COMPARE_ROWS: { label: string; cells: [string, string, string] }[] = [
  {
    label: 'Where the files are',
    cells: ["Hugging Face's servers", 'Seeders, with Hugging Face as a web seed', 'Seeders, plus any HTTP mirror, including Hugging Face'],
  },
  {
    label: 'Who can delist a model',
    cells: ['Hugging Face', 'Pirate Face, which runs the list', 'Nobody across the network. A hub can only drop it from its own board'],
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
    cells: ['The host is trusted', "After each file downloads, against Hugging Face's SHA-256", 'During the download, piece by piece'],
  },
  { label: 'Where discussion happens', cells: ['Hugging Face', 'On Pirate Face', 'Peer-to-peer communities, each with its own rules'] },
  { label: 'Works with existing tools', cells: ['Yes', 'Yes, through its pip package for Python tools', 'Yes, through a local Hugging Face endpoint'] },
];

export type Step = {
  title: string;
  body: string;
  estimate: string;
  complete?: boolean;
};

export const STEPS: Step[] = [
  { title: 'Measurements', body: 'The engine prototype works; community scale, larger real models and WAN tests remain.', estimate: '~1 week' },
  { title: 'Manifest and command line', body: 'Implemented: make, verify and pull unsigned manifests into a verified local cache.', estimate: 'Prototype complete', complete: true },
  { title: 'The Hugging Face endpoint', body: 'Implemented for the SDK: local releases and verified public fallback. Other consumers remain.', estimate: 'SDK prototype complete' },
  { title: 'Publishing and reading releases', body: 'Signed profile publishing, pulls and endpoint registration work locally. Public hosting, mirrors and web client remain.', estimate: 'CLI prototype complete' },
  { title: 'Hubs and search', body: 'Curated boards with discussion, and search across several indexers.', estimate: '2–3 weeks' },
  { title: 'Desktop client', body: 'One app with a node, a torrent engine and the local endpoint.', estimate: '3–4 weeks' },
];

// The step after which the tool is useful to one person with no network of publishers.
export const USEFUL_ALONE_AFTER = 3;

export const QUESTIONS = [
  { text: 'Who publishes first?', anchor: 'who-publishes-first' },
  { text: 'Who seeds a model nobody downloaded this month?', anchor: 'seeding' },
  { text: 'How does a reader tell a real publisher from an imitator?', anchor: 'names-and-impersonation' },
];

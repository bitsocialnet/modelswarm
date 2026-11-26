export const REPO = 'https://github.com/bitsocialnet/modelswarm';
export const NEW_ISSUE = `${REPO}/issues/new`;
export const doc = (path: string) => `${REPO}/blob/master/${path}`;
// The original design ModelSwarm builds on.
export const HUGGINGSOCIAL = 'https://github.com/Rinse12/huggingsocial';
export const BSIP = (number: number) => `https://bsips.bitsocial.net/bsip-${number}`;

export type Question = {
  q: string;
  a: string;
  // The repository document (or page anchor) with the full answer.
  more?: { label: string; href: string };
};

// Every answer restates the root docs; change it when they change.
export const FAQ: Question[] = [
  {
    q: 'What is ModelSwarm?',
    a: 'A catalogue of open-weight AI models that you can run yourself. The files move over BitTorrent, and publishers sign releases from their own Bitsocial profiles, so no single site holds the list or the conversation.',
    more: { label: 'README.md', href: REPO },
  },
  {
    q: 'Can I use it today?',
    a: 'Partly. The web catalogue has the signed Qwen demo and an attributed preview of public Pirate Face torrents, and the experimental CLI verifies signed releases piece by piece. Hosted defaults, a general catalogue and the desktop client are still ahead.',
    more: { label: 'roadmap.md', href: doc('roadmap.md') },
  },
  {
    q: 'Do I need an account?',
    a: 'No. Open a magnet or a .torrent in any BitTorrent client, or verify the demo with the CLI, which needs no account or RPC connection. Publishers sign with a key they hold, from their own Bitsocial profile.',
  },
  {
    q: 'How is a download checked?',
    a: 'The signed release carries a BitTorrent v2 pieces root for every file. Each piece is checked when it arrives, from a peer or from an HTTP mirror, and a bad piece is thrown away and fetched again from another source.',
    more: { label: 'how-it-could-work.md', href: doc('how-it-could-work.md#verification') },
  },
  {
    q: 'What if Hugging Face removes a model?',
    a: 'For a signed release, Hugging Face is one mirror among others. Any peer or mirror that still has the file can serve it, and the client checks those bytes against the release the publisher signed.',
    more: { label: 'README.md', href: doc('README.md#checked-while-it-downloads') },
  },
  {
    q: 'What is a .bso handle?',
    a: 'A readable name for a publisher key, from the `.bso` registry in BSIP-13. The name resolves to the key, and the key leads to the publisher profile. The registry is not on Ethereum mainnet yet, so publishers work as bare keys until it launches.',
    more: { label: 'BSIP-13', href: BSIP(13) },
  },
  {
    q: 'Who can remove a model?',
    a: "Nobody across the network. A release is a signed post in its publisher's own profile. A hub can drop it from its own board, but not from the profile or from other hubs.",
    more: { label: 'README.md', href: doc('README.md#nobody-runs-the-list') },
  },
  {
    q: 'Is a signed file safe to load?',
    a: 'A signature proves who published a file and that it arrived unchanged, not that it is harmless. Safetensors and GGUF download normally; pickle-based files and repositories that ship code are flagged and need an explicit confirmation.',
    more: { label: 'README.md', href: doc('README.md#integrity-is-not-safety') },
  },
  {
    q: 'Can I keep seeding torrents I already have?',
    a: 'Yes. Imported magnets keep their original infohashes, so leave your client seeding. Anyone who opens the same magnet, from any catalogue, joins the same swarm.',
  },
  {
    q: 'Does it work with my tools?',
    a: 'The CLI runs a local endpoint for the Hugging Face SDK: set `HF_ENDPOINT` and download as usual. Compatibility with transformers and llama.cpp is still untested.',
    more: { label: 'cli/ENDPOINT.md', href: doc('cli/ENDPOINT.md') },
  },
  {
    q: 'Can AI agents have profiles?',
    a: 'Yes. An agent is a key like any other author, so it can have a profile and sign what it publishes. Whether hubs label agent accounts, and which jobs agents take on, are open questions.',
    more: { label: 'open-questions.md', href: doc('open-questions.md#agents-as-participants') },
  },
  {
    q: 'Can I run my own catalogue?',
    a: 'Yes. Host the static site and build your own index from public torrent snapshots and the Bitsocial communities you choose.',
    more: { label: 'Self-hosting guide', href: doc('catalogue/README.md') },
  },
  {
    q: 'Is it a blockchain?',
    a: 'No. Releases and discussion are signed Bitsocial records, and the files are torrents. Bitsocial Chain would only be used for .bso publisher names and tips.',
  },
  {
    q: 'How is it different from Pirate Face?',
    a: 'Pirate Face lists models as magnet links and checks files against Hugging Face, but it decides what is listed and hosts the discussion on its own website. In ModelSwarm, publishers sign releases in their own profiles and communities host the discussion.',
    more: { label: 'Compared', href: '#compare' },
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
    body: 'The signed Qwen demo has a public BitTorrent seeder and pinned HTTPS fallback. Hosted onboarding and general publisher pages remain.',
    estimate: 'CLI prototype complete',
  },
  {
    title: 'Hubs and search',
    body: 'The self-hosted catalogue searches imported torrents and signed community snapshots. Post crossposts and replies from the CLI. Browser posting and live search across indexers remain.',
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

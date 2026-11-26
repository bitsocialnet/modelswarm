import { demoModel } from './demo-model';
import release from './demo-release.json';

export type IndexSnapshot<T> = { version: 1; entries: T[]; observedAt?: string };

export type ImportedModel = {
  name: string;
  format: string;
  bytes: number | null;
  seeders: number | null;
  license: string;
  magnet: string;
  trackedMagnet?: string;
  revision?: string;
  upstream?: string;
};

export type CommunityFile = { path: string; bytes: number; sha256: string; torrent: string | null; https: string | null; flagged: boolean };
export type CommunityModel = Omit<ImportedModel, 'magnet' | 'trackedMagnet' | 'revision' | 'upstream'> & {
  publisher: string;
  releaseCid: string;
  version: string;
  postCid: string;
  files: CommunityFile[];
  replies: { author: string; cid: string; text: string; timestamp: number }[];
};

type CommunitySnapshot = IndexSnapshot<CommunityModel> & { community: string };

export type Model = Omit<ImportedModel, 'magnet' | 'trackedMagnet'> & {
  id: string;
  kind: 'demo' | 'import' | 'community';
  download: string | null;
  peerOnly?: string;
  community?: CommunityModel & { key: string };
};

const imports = import.meta.glob<{ default: IndexSnapshot<ImportedModel> }>('./pirateface-*.json');
const communities = import.meta.glob<{ default: CommunitySnapshot }>('./community-*.json');
const importSnapshot = imports['./pirateface-index.json'] ?? imports['./pirateface-preview.json'];

export const demoEntry: Model = {
  id: 'signed-qwen',
  kind: 'demo',
  name: 'Qwen/Qwen2.5-0.5B-Instruct · Q4_K_M',
  format: demoModel.format,
  bytes: release.weights.size,
  seeders: null,
  license: demoModel.license,
  download: demoModel.torrent,
};

export async function loadCatalogue() {
  const [importResult, communityResult] = await Promise.all([importSnapshot?.(), Promise.all(Object.values(communities).map((load) => load()))]);
  const imported = importResult?.default;
  const communityEntries = new Map<string, CommunityModel & { key: string }>();
  for (const { default: snapshot } of communityResult) {
    for (const entry of snapshot.entries) communityEntries.set(entry.postCid, { ...entry, key: snapshot.community });
  }
  const models: Model[] = [
    demoEntry,
    ...Array.from(communityEntries.values()).map((entry): Model => ({
      ...entry,
      format: ({ gguf: 'GGUF', safetensors: 'Safetensors', other: 'Other' } as Record<string, string>)[entry.format] ?? entry.format,
      id: entry.postCid,
      kind: 'community',
      download: null,
      community: entry,
    })),
    ...(imported?.entries ?? []).map(({ magnet, trackedMagnet, ...entry }): Model => ({
      ...entry,
      id: `import-${entry.name}`,
      kind: 'import',
      download: trackedMagnet?.startsWith('magnet:?') ? trackedMagnet : magnet.startsWith('magnet:?') ? magnet : null,
      peerOnly: trackedMagnet && magnet.startsWith('magnet:?') ? magnet : undefined,
    })),
  ];
  return { models, observedAt: imported?.observedAt };
}

const sizeNumber = new Intl.NumberFormat('en', { maximumFractionDigits: 1 });
const countNumber = new Intl.NumberFormat('en');

export function formatBytes(bytes: number | null) {
  if (bytes === null) return 'Unknown';
  if (bytes >= 1e12) return `${sizeNumber.format(bytes / 1e12)} TB`;
  if (bytes >= 1e9) return `${sizeNumber.format(bytes / 1e9)} GB`;
  if (bytes >= 1e6) return `${sizeNumber.format(bytes / 1e6)} MB`;
  if (bytes >= 1e3) return `${sizeNumber.format(bytes / 1e3)} KB`;
  return `${countNumber.format(bytes)} B`;
}

export function formatCount(n: number) {
  return countNumber.format(n);
}

// One load per page, shared by every component that shows catalogue entries.
let snapshot: Promise<Awaited<ReturnType<typeof loadCatalogue>> | null> | undefined;
export const catalogueSnapshot = () => (snapshot ??= loadCatalogue().catch(() => null));

// Imported torrents with the most seeders at the last observation.
export function mostSeeded(models: Model[], count: number) {
  return models
    .filter((model) => model.kind === 'import' && model.seeders !== null && model.download)
    .sort((a, b) => (b.seeders ?? 0) - (a.seeders ?? 0))
    .slice(0, count);
}

// A catalogue search for one model, used to link a model name to its row.
export const catalogueSearch = (query: string) => `./catalogue.html?q=${encodeURIComponent(query)}`;

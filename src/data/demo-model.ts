import release from './demo-release.json';

const upstream = 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF';
const revision = '9217f5db79a29953eb74d5343926648285ec7e67';
const upstreamFiles = `${upstream}/resolve/${revision}`;

// The GGUF's BitTorrent v2 pieces root and piece length, from public/demo/qwen-signed-manifest.json.
const PIECES_ROOT = '462868d271e23102b4955c6d8b6a051a7aefa4ca89c968d06a1a8028d9dea985';
const PIECE_LENGTH = 1_048_576;

export const demoModel = {
  title: 'Qwen2.5-0.5B-Instruct',
  description: "Qwen's 0.5B-parameter instruction-tuned language model, quantized to Q4_K_M for local inference.",
  format: 'GGUF',
  quantization: 'Q4_K_M',
  size: `${Math.round(release.weights.size / 1_000_000)} MB`,
  license: 'Apache-2.0',
  publisher: 'ModelSwarm demo publisher',
  page: './release.html',
  torrent: `./demo/${release.weights.path}.torrent`,
  https: `${upstreamFiles}/${release.weights.path}`,
  licenseUrl: `${upstreamFiles}/LICENSE`,
  modelCard: `${upstream}/tree/${revision}`,
  piecesRoot: PIECES_ROOT,
  pieces: Math.ceil(release.weights.size / PIECE_LENGTH),
};

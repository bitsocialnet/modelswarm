import release from './demo-release.json';

const upstream = 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF';
const revision = '9217f5db79a29953eb74d5343926648285ec7e67';
const upstreamFiles = `${upstream}/resolve/${revision}`;

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
};

const smolLM360 = 'SmolLM2-360M-Instruct';

// Both conversions name HuggingFaceTB/SmolLM2-360M-Instruct as their upstream base.
const variantGroups = new Map([
  ['import-HuggingFaceTB/SmolLM2-360M-Instruct-GGUF', smolLM360],
  ['import-mfuntowicz/SmolLM2-360M-Instruct-Q4_K_M-GGUF', smolLM360],
]);

export const starterPicks = [
  {
    id: 'signed-qwen',
    name: 'Qwen2.5-0.5B-Instruct',
    description: 'A small, general-purpose chat model.',
    format: 'GGUF · Q4_K_M',
  },
  {
    id: 'import-bartowski/SmolLM2-135M-Instruct-GGUF',
    name: 'SmolLM2-135M-Instruct',
    description: 'A compact chat model for a quick first try.',
    format: 'GGUF',
  },
  {
    id: 'import-mfuntowicz/SmolLM2-360M-Instruct-Q4_K_M-GGUF',
    name: 'SmolLM2-360M-Instruct',
    description: 'A larger SmolLM2 chat model in four-bit GGUF.',
    format: 'GGUF · Q4_K_M',
  },
];

export function modelFamily(id: string) {
  return variantGroups.get(id);
}

export function groupVariants<T extends { id: string }>(models: T[]) {
  const groups = new Map<string, { name?: string; models: T[] }>();
  for (const model of models) {
    const name = modelFamily(model.id);
    const key = name ?? model.id;
    const group = groups.get(key);
    if (group) group.models.push(model);
    else groups.set(key, { name, models: [model] });
  }
  return groups.values();
}

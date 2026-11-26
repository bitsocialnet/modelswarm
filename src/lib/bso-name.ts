// Local checks for a .bso label as BSIP-13 describes it. Nothing here talks to the registry, and
// .bso names are not live yet, so availability cannot be known from the site.
import type { ens_normalize } from '@adraffy/ens-normalize';

export type Normalize = typeof ens_normalize;

export type LabelCheck =
  | { state: 'empty' }
  | { state: 'pending' }
  | { state: 'invalid'; reason: string }
  | { state: 'ok'; label: string; length: number };

// ENSIP-15 tables are large, so the normalizer loads only once someone types a name.
let normalizer: Promise<Normalize> | undefined;
export function loadNormalizer() {
  normalizer ??= import('@adraffy/ens-normalize').then((module) => module.ens_normalize);
  return normalizer;
}

const invalid = (reason: string): LabelCheck => ({ state: 'invalid', reason });

// BSIP-13: a front end must ENS-normalize a label and refuse one normalization rejects; the registry
// itself refuses a leading or trailing hyphen, more than 255 UTF-8 bytes, and fewer than 3 code points.
export function checkLabel(input: string, normalize: Normalize | null): LabelCheck {
  const raw = input.trim().replace(/\.bso$/i, '');
  if (!raw) return { state: 'empty' };
  if (/[\s./\\@:]/.test(raw)) return invalid('A name is one label, without dots, spaces or slashes.');
  if (!normalize) return { state: 'pending' };

  let label: string;
  try {
    label = normalize(raw);
  } catch (error) {
    const message = error instanceof Error ? error.message.replace(/‎/g, '') : String(error);
    if (message.includes('underscore')) {
      // BSIP-13 asks front ends to suggest hyphens, as in relationship-advice for relationship_advice.
      const suggestion = raw.replace(/^(_*)(.*)$/s, (_, lead: string, rest: string) => lead + rest.replaceAll('_', '-'));
      return invalid(`ENS allows an underscore only at the start of a name. Try ${suggestion.toLowerCase()}.bso.`);
    }
    return invalid(`ENS normalization refuses this spelling: ${message}.`);
  }

  if (!label || label.includes('.')) return invalid('A name is one label, without dots, spaces or slashes.');
  if (label.startsWith('-') || label.endsWith('-')) return invalid('A name cannot start or end with a hyphen.');
  if (new TextEncoder().encode(label).length > 255) return invalid('A name can be at most 255 bytes long.');
  const length = [...label].length;
  if (length < 3) return invalid('A top-level name needs at least 3 characters.');
  return { state: 'ok', label, length };
}

// Local checks for a .bso label as BSIP-13 describes it. Nothing here talks to the registry,
// which is not on Ethereum mainnet yet; availability cannot be known from the site.

export type LabelCheck =
  | { state: 'empty' }
  | { state: 'invalid'; reason: string }
  | { state: 'ok'; label: string; length: number; price: string };

// BSIP-13 prices per 365 days, by length in Unicode code points (draft).
function priceFor(length: number) {
  if (length === 3) return '0.05 ETH';
  if (length === 4) return '0.01 ETH';
  return '0.0005 ETH';
}

export function checkLabel(input: string): LabelCheck {
  const label = input.trim().toLowerCase().replace(/\.bso$/, '');
  if (!label) return { state: 'empty' };
  if (/[\s./\\@:]/.test(label)) return { state: 'invalid', reason: 'A name is one label, without dots, spaces or slashes.' };
  const length = [...label].length;
  if (length < 3) return { state: 'invalid', reason: 'A top-level name needs at least 3 characters.' };
  return { state: 'ok', label, length, price: priceFor(length) };
}

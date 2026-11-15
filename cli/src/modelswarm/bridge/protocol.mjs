import { createPublicKey, verify } from 'node:crypto';
import { isIP } from 'node:net';
import { publicKeyFromRaw } from '@libp2p/crypto/keys';
import { peerIdFromPublicKey, peerIdFromString } from '@libp2p/peer-id';
import { encode } from 'cborg';
import { CID } from 'multiformats/cid';
import { of as ipfsHash } from 'typestub-ipfs-only-hash';

export const RELEASE_SCHEMA = 'modelswarm/release/v0';
export const MAX_RECORD_BYTES = 40 * 1024;
export const MAX_CARD_BYTES = 24 * 1024;
const ED25519_SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');
const NAME_PART = /^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,94}[A-Za-z0-9])?$/;
const VERSION = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const REQUIRED_SIGNED = ['content', 'communityPublicKey', 'timestamp', 'protocolVersion'];
const COMMUNITY_FIELDS = new Set([
  'depth', 'thumbnailUrl', 'thumbnailUrlWidth', 'thumbnailUrlHeight', 'previousCid', 'pseudonymityMode',
]);
const PUBLICATION_FIELDS = new Set([
  ...REQUIRED_SIGNED, 'title', 'author', 'communityName', 'flairs', 'spoiler', 'nsfw',
  'link', 'linkWidth', 'linkHeight', 'linkHtmlTagName', 'quotedCids', 'gallery',
]);
const RUNTIME_AUTHOR_FIELDS = new Set(['address', 'publicKey', 'shortAddress', 'community', 'nameResolved']);

function invalid(message) {
  throw new Error(`Invalid ModelSwarm release: ${message}`);
}

function object(value, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) invalid(`${label} must be an object`);
}

function exactKeys(value, keys, label) {
  object(value, label);
  if (Object.keys(value).length !== keys.length || keys.some((key) => !Object.hasOwn(value, key))) {
    invalid(`${label} must contain exactly ${keys.join(', ')}`);
  }
}

function string(value, label) {
  if (typeof value !== 'string' || !value.isWellFormed()) invalid(`${label} must be a well-formed string`);
}

// Bound recursion before CBOR encoding and reject JSON values that have ambiguous encodings.
function validateJson(value) {
  const pending = [[value, 0]];
  while (pending.length) {
    const [entry, depth] = pending.pop();
    if (depth > 32) invalid('JSON nesting exceeds 32 levels');
    if (typeof entry === 'string') string(entry, 'JSON string');
    else if (typeof entry === 'number') {
      if (!Number.isFinite(entry)) invalid('JSON contains a nonfinite number');
    } else if (entry !== null && typeof entry === 'object') {
      if (!Array.isArray(entry) && Object.getPrototypeOf(entry) !== Object.prototype && Object.getPrototypeOf(entry) !== null) {
        invalid('JSON contains a nonplain object');
      }
      for (const [key, child] of Object.entries(entry)) {
        if (key === '__proto__' || key === 'constructor' || key === 'prototype') invalid('JSON contains a reserved property');
        string(key, 'JSON key');
        pending.push([child, depth + 1]);
      }
    } else if (entry !== null && typeof entry !== 'boolean') invalid('JSON contains an unsupported value');
  }
}

function parseJson(text, label) {
  let value;
  try { value = JSON.parse(text); } catch { invalid(`${label} is not valid JSON`); }
  validateJson(value);
  return value;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function cidValue(value, label) {
  if (typeof value !== 'string' || value.length > 128) invalid(`${label} must be an IPFS CID`);
  try { return CID.parse(value); } catch { invalid(`${label} must be an IPFS CID`); }
}

/** Accept only an exact, canonical Ed25519 identity, never a domain or RPC author label. */
export function parsePublisher(value) {
  if (typeof value !== 'string' || value.length > 128) invalid('publisher must be an Ed25519 PeerId');
  try {
    const peer = peerIdFromString(value);
    if (peer.type !== 'Ed25519' || peer.toString() !== value) invalid('publisher must be a canonical Ed25519 PeerId');
  } catch { invalid('publisher must be a canonical Ed25519 PeerId'); }
  return value;
}

function manifestUrl(value) {
  string(value, 'manifest URL');
  if (value.length > 4096 || /[\u0000-\u0020\u007f]/u.test(value)) invalid('manifest URL is malformed or too long');
  if (value.startsWith('ipfs://')) {
    cidValue(value.slice(7), 'manifest URL');
    return;
  }
  if (!/^https?:\/\//.test(value) || value.includes('\\')) invalid('manifest URL must be an absolute HTTP(S) URL');
  let url;
  try { url = new URL(value); } catch { invalid('manifest URL must be HTTPS, loopback HTTP, or ipfs://CID'); }
  if (url.username || url.password || url.hash) invalid('manifest URL cannot include credentials or a fragment');
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  const ip = isIP(host);
  const loopback = host === 'localhost' || host === '::1' || (ip === 4 && host.startsWith('127.'));
  if (url.protocol === 'http:' && loopback) return;
  if (url.protocol !== 'https:' || loopback || !host || (ip !== 6 && !host.includes('.'))) invalid('manifest URL must use public HTTPS or explicit loopback HTTP');
  if (host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) invalid('manifest URL host is not public');
  if (ip === 4) {
    const [a, b] = host.split('.').map(Number);
    if (a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254)
      || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127)) {
      invalid('manifest URL host is not public');
    }
  }
  if (ip === 6 && (host === '::' || host.startsWith('fc') || host.startsWith('fd')
    || /^fe[89ab]/.test(host) || host.startsWith('ff') || host.startsWith('::ffff:'))) {
    invalid('manifest URL host is not public');
  }
  // DNS answers are checked by the fetch transport. The signed
  // reference's syntax is not authorization to access a private address after resolution.
}

function validateRelease(value) {
  validateJson(value);
  exactKeys(value, ['schema', 'name', 'version', 'manifest', 'modelCard'], 'release');
  if (value.schema !== RELEASE_SCHEMA) invalid(`schema must be ${RELEASE_SCHEMA}`);
  string(value.name, 'name');
  const parts = value.name.split('/');
  if (parts.length !== 2 || parts.some((part) => !NAME_PART.test(part) || part.includes('..') || part.includes('--'))) {
    invalid('name must be an owner/model identifier');
  }
  if (typeof value.version !== 'string' || !VERSION.test(value.version)) invalid('version must be a short alphanumeric label');
  exactKeys(value.manifest, ['url', 'sha256'], 'manifest reference');
  manifestUrl(value.manifest.url);
  if (typeof value.manifest.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.manifest.sha256)) {
    invalid('manifest sha256 must be 64 lowercase hexadecimal characters');
  }
  string(value.modelCard, 'modelCard');
  if (Buffer.byteLength(value.modelCard, 'utf8') > MAX_CARD_BYTES) invalid('modelCard exceeds 24 KiB');
  return value;
}

/** Canonicalize the exact v0 release envelope before passing it as PKC comment.content. */
export function encodeRelease(value) {
  const text = JSON.stringify(canonical(validateRelease(value)));
  if (Buffer.byteLength(text, 'utf8') > MAX_RECORD_BYTES) invalid('release content exceeds 40 KiB');
  return text;
}

export function parseRelease(content) {
  string(content, 'content');
  if (Buffer.byteLength(content, 'utf8') > MAX_RECORD_BYTES) invalid('release content exceeds 40 KiB');
  return validateRelease(parseJson(content, 'release content'));
}

function base64(value, length, label) {
  if (typeof value !== 'string') invalid(`${label} must be canonical base64`);
  const bytes = Buffer.from(value, 'base64');
  // uint8arrays, used by PKC, emits RFC 4648 base64 without trailing padding.
  if (bytes.length !== length || bytes.toString('base64').replace(/=+$/, '') !== value) invalid(`${label} must be canonical unpadded base64 for ${length} bytes`);
  return bytes;
}

/**
 * Verify an immutable, native PKC top-level release comment. RPC supplies bytes only:
 * no author labels, page membership, latest claims, edits, or community metadata are trusted.
 * This deliberately accepts a narrower record shape than the general PKC protocol.
 */
export async function verifyRelease({ rawComment, cid, publisher }) {
  parsePublisher(publisher);
  const expectedCid = cidValue(cid, 'release CID');
  if (expectedCid.code !== 0x70 || expectedCid.multihash.code !== 0x12) invalid('release CID must use DAG-PB and SHA-256');
  if (typeof rawComment !== 'string' && !Buffer.isBuffer(rawComment)) invalid('rawComment must contain exact UTF-8 bytes');
  const bytes = Buffer.isBuffer(rawComment) ? rawComment : Buffer.from(rawComment, 'utf8');
  if (bytes.length > MAX_RECORD_BYTES) invalid('comment exceeds 40 KiB');
  let text;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch { invalid('comment is not valid UTF-8'); }
  if (typeof rawComment === 'string' && (!rawComment.isWellFormed() || rawComment !== text)) invalid('comment is not well-formed UTF-8');
  const calculated = CID.parse(await ipfsHash(bytes));
  if (!calculated.toV1().equals(expectedCid.toV1())) invalid('comment bytes do not match release CID');
  const comment = parseJson(text, 'comment');
  object(comment, 'comment');
  for (const key of Object.keys(comment)) {
    if (key !== 'signature' && !PUBLICATION_FIELDS.has(key) && !COMMUNITY_FIELDS.has(key)) invalid(`unsupported comment field ${key}`);
  }
  if (comment.depth !== 0) invalid('release must be a top-level post with depth 0');
  if (comment.communityPublicKey !== publisher) invalid('signed communityPublicKey does not match publisher');
  if (!Number.isSafeInteger(comment.timestamp) || comment.timestamp < 0) invalid('timestamp must be a nonnegative integer');
  if (typeof comment.protocolVersion !== 'string' || !/^\d+\.\d+\.\d+$/.test(comment.protocolVersion)) invalid('invalid PKC protocolVersion');
  for (const field of ['title', 'communityName', 'link', 'linkHtmlTagName']) {
    if (comment[field] !== undefined) string(comment[field], field);
  }
  if (comment.author !== undefined) {
    object(comment.author, 'author');
    if (Object.keys(comment.author).some((key) => RUNTIME_AUTHOR_FIELDS.has(key))) invalid('author contains an untrusted runtime label');
  }
  exactKeys(comment.signature, ['type', 'publicKey', 'signature', 'signedPropertyNames'], 'signature');
  if (comment.signature.type !== 'ed25519') invalid('signature type must be ed25519');
  const publicKey = base64(comment.signature.publicKey, 32, 'signature publicKey');
  const signature = base64(comment.signature.signature, 64, 'signature');
  const signed = comment.signature.signedPropertyNames;
  if (!Array.isArray(signed) || signed.some((name) => typeof name !== 'string') || new Set(signed).size !== signed.length) {
    invalid('signedPropertyNames must contain unique field names');
  }
  if (REQUIRED_SIGNED.some((key) => !signed.includes(key))) invalid('signature does not cover all required release fields');
  for (const key of signed) {
    if (!PUBLICATION_FIELDS.has(key) || !Object.hasOwn(comment, key) || comment[key] === null) invalid(`invalid signed property ${key}`);
  }
  for (const key of Object.keys(comment)) {
    if (PUBLICATION_FIELDS.has(key) && !signed.includes(key)) invalid(`unsigned publication field ${key}`);
  }
  const derivedPublisher = peerIdFromPublicKey(publicKeyFromRaw(publicKey)).toString();
  if (derivedPublisher !== publisher) invalid('signature identity does not match publisher');
  const signedObject = Object.fromEntries(signed.map((key) => [key, comment[key]]));
  const key = createPublicKey({ key: Buffer.concat([ED25519_SPKI_PREFIX, publicKey]), format: 'der', type: 'spki' });
  // PKC signs the CBOR-encoded listed properties. Native Ed25519 verification is
  // intentionally fail-closed for noncanonical signatures accepted by ZIP215.
  if (!verify(null, encode(signedObject), key, signature)) invalid('Ed25519 signature verification failed');
  const release = parseRelease(comment.content);
  return { cid, publisher: derivedPublisher, release, comment };
}

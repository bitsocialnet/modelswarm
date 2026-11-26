import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import PKC from '@pkcprotocol/pkc-js';
import { CID } from 'multiformats/cid';
import { of as ipfsHash } from 'typestub-ipfs-only-hash';
import {
  RELEASE_SCHEMA, MAX_CARD_BYTES, MAX_RECORD_BYTES,
  encodeRelease, parsePublisher, parseRelease, scanDiscussionFeed, verifyDiscussion, verifyRelease,
} from './protocol.mjs';

let pkc;
let signer;
let other;
const release = {
  schema: RELEASE_SCHEMA,
  name: 'alice/tiny-model',
  version: 'v1.0',
  manifest: { url: 'https://models.example/releases/model.json', sha256: 'a'.repeat(64) },
  modelCard: '# Tiny model\n\nA local test fixture.\n',
};

before(async () => {
  // Explicitly empty transports: signing and verification never contact public services.
  pkc = await PKC({
    noData: true, ipfsGatewayUrls: [], kuboRpcClientsOptions: [], pubsubKuboRpcClientsOptions: [],
    httpRoutersOptions: [], nameResolvers: [], resolveAuthorNames: false,
  });
  signer = await pkc.createSigner();
  other = await pkc.createSigner();
});
after(async () => { await pkc?.destroy(); });

async function withCid(comment, publisher = signer.address) {
  const rawComment = JSON.stringify(comment);
  return { rawComment, cid: await ipfsHash(rawComment), publisher };
}

async function fixture(options = {}) {
  const publication = await pkc.createComment({
    signer, communityPublicKey: signer.address, title: 'Tiny model v1.0',
    content: encodeRelease(release), timestamp: 1730000000, ...options,
  });
  assert.ok(publication.raw.pubsubMessageToPublish, 'SDK must sign the supplied community key locally');
  return { ...structuredClone(publication.raw.pubsubMessageToPublish), depth: 0 };
}

async function discussion({ depth, ...options }) {
  const publication = await pkc.createComment({ signer: other, communityPublicKey: other.address, ...options });
  const result = await withCid({ ...structuredClone(publication.raw.pubsubMessageToPublish), depth });
  return { ...result, community: other.address };
}

test('a signed native crosspost cannot substitute its unsigned embedded release', async () => {
  const comment = await fixture();
  const { cid } = await withCid(comment);
  const valid = await discussion({ depth: 0, crosspost: { cid, comment } });
  const verified = await verifyDiscussion(valid);
  assert.equal(verified.publisher, signer.address);
  assert.equal(verified.releaseCid, cid);
  assert.equal(verified.postCid, valid.cid);

  const modified = { ...comment, content: encodeRelease({ ...release, version: 'imposter' }) };
  const modifiedCid = (await withCid(modified)).cid;
  const invalid = await discussion({ depth: 0, crosspost: { cid: modifiedCid, comment: modified } });
  await assert.rejects(verifyDiscussion(invalid), /signature verification failed/);
});

test('signed discussion replies are bound to the original thread and signer', async () => {
  const parent = await ipfsHash('the crosspost');
  const reply = await discussion({ depth: 1, parentCid: parent, postCid: parent, content: 'From the reader' });
  const verified = await verifyDiscussion({ ...reply, parent });
  assert.equal(verified.author, other.address);
  assert.equal(verified.text, 'From the reader');
  await assert.rejects(verifyDiscussion({ ...reply, parent: await ipfsHash('different thread') }), /different thread/);
});

test('native PKC signed release verifies from exact bytes without trusting runtime labels', async () => {
  const args = await withCid(await fixture());
  const result = await verifyRelease(args);
  assert.equal(result.publisher, signer.address);
  assert.equal(result.cid, args.cid);
  assert.deepEqual(result.release, release);
  assert.equal(result.comment.depth, 0);
  assert.equal(parsePublisher(signer.address), signer.address);
});

test('equivalent CIDv1 and Buffer input preserve immutable content verification', async () => {
  const args = await withCid(await fixture());
  const cid = CID.parse(args.cid).toV1().toString();
  const result = await verifyRelease({ ...args, cid, rawComment: Buffer.from(args.rawComment) });
  assert.equal(result.cid, cid);
  assert.deepEqual(result.release, release);
});

test('canonical release encoding is independent of input property order', () => {
  const reversed = Object.fromEntries(Object.entries(release).reverse());
  reversed.manifest = { sha256: release.manifest.sha256, url: release.manifest.url };
  assert.equal(encodeRelease(reversed), encodeRelease(release));
  assert.deepEqual(parseRelease(encodeRelease(reversed)), release);
});

test('tampering with signed content fails even when the attacker supplies its new CID', async () => {
  const comment = await fixture();
  comment.content = encodeRelease({ ...release, version: 'v2' });
  await assert.rejects(verifyRelease(await withCid(comment)), /signature verification failed/);
});

test('exact record CID rejects altered whitespace and mismatching selectors', async () => {
  const args = await withCid(await fixture());
  await assert.rejects(verifyRelease({ ...args, rawComment: `${args.rawComment}\n` }), /do not match release CID/);
  await assert.rejects(verifyRelease({ ...args, cid: 'not-a-cid' }), /must be an IPFS CID/);
  await assert.rejects(verifyRelease({ ...args, cid: await ipfsHash('unrelated') }), /do not match release CID/);
});

test('a different key cannot publish under the expected profile identity', async () => {
  const comment = await fixture({ signer: other });
  await assert.rejects(verifyRelease(await withCid(comment)), /signature identity does not match publisher/);
});

test('the owner cannot reuse a release signed for a different community', async () => {
  const comment = await fixture({ communityPublicKey: other.address });
  await assert.rejects(verifyRelease(await withCid(comment)), /communityPublicKey does not match publisher/);
});

test('signedPropertyNames must cover content, scope, timestamp, and protocolVersion', async () => {
  for (const field of ['content', 'communityPublicKey', 'timestamp', 'protocolVersion']) {
    const comment = await fixture();
    comment.signature.signedPropertyNames = comment.signature.signedPropertyNames.filter((key) => key !== field);
    await assert.rejects(verifyRelease(await withCid(comment)), /does not cover all required release fields/);
  }
});

test('duplicate, nonexistent, and unsigned publication properties are rejected', async () => {
  let comment = await fixture();
  comment.signature.signedPropertyNames.push('content');
  await assert.rejects(verifyRelease(await withCid(comment)), /unique field names/);
  comment = await fixture();
  comment.signature.signedPropertyNames.push('nsfw');
  await assert.rejects(verifyRelease(await withCid(comment)), /invalid signed property nsfw/);
  comment = await fixture();
  comment.nsfw = true;
  await assert.rejects(verifyRelease(await withCid(comment)), /unsigned publication field nsfw/);
});

test('signature bytes, key bytes, encoding, and algorithm fail closed', async () => {
  for (const mutate of [
    (c) => { c.signature.signature = 'A'.repeat(86); },
    (c) => { c.signature.signature += '=='; },
    (c) => { c.signature.publicKey += '='; },
    (c) => { c.signature.publicKey = 'AA'; },
    (c) => { c.signature.type = 'rsa'; },
  ]) {
    const comment = await fixture();
    mutate(comment);
    await assert.rejects(verifyRelease(await withCid(comment)), /Invalid ModelSwarm release/);
  }
});

test('replies, crossposts, and runtime fields are outside the release format', async () => {
  for (const extra of [
    { depth: 1 }, { parentCid: await ipfsHash('parent') }, { postCid: await ipfsHash('post') },
    { crosspost: {} }, { cid: await ipfsHash('runtime') }, { author: { address: signer.address } },
  ]) {
    await assert.rejects(verifyRelease(await withCid({ ...await fixture(), ...extra })), /Invalid ModelSwarm release/);
  }
});

test('signed author display names are allowed but never determine publisher identity', async () => {
  const comment = await fixture({ author: { displayName: 'Somebody else' } });
  const result = await verifyRelease(await withCid(comment));
  assert.equal(result.publisher, signer.address);
});

test('profile selectors require canonical Ed25519 keys rather than names', () => {
  for (const value of ['alice.eth', 'alice', '', 1, 'https://example.com', '12D3KooWinvalid']) {
    assert.throws(() => parsePublisher(value), /publisher must be/);
  }
});

test('release schema, exact fields, model names, version, and manifest digest are strict', () => {
  for (const value of [
    { ...release, schema: 'future' }, { ...release, unknown: true }, { ...release, name: '../model' },
    { ...release, name: 'alice/a--b' }, { ...release, version: '../v1' },
    { ...release, manifest: { ...release.manifest, sha256: 'A'.repeat(64) } },
    { ...release, manifest: { ...release.manifest, size: 10 } },
  ]) assert.throws(() => encodeRelease(value), /Invalid ModelSwarm release/);
  assert.throws(() => parseRelease('{'), /not valid JSON/);
});

const LINE_TERMINATORS = ['\n', '\r', '\r\n', '\u2028', '\u2029'];
for (const [field, withSuffix] of [
  ['owner', (suffix) => ({ ...release, name: `alice${suffix}/tiny-model` })],
  ['model', (suffix) => ({ ...release, name: `${release.name}${suffix}` })],
  ['version', (suffix) => ({ ...release, version: `${release.version}${suffix}` })],
  ['manifest digest', (suffix) => ({ ...release, manifest: { ...release.manifest, sha256: `${release.manifest.sha256}${suffix}` } })],
]) {
  test(`${field} rejects trailing line terminators in encoded and signed releases`, async () => {
    for (const suffix of LINE_TERMINATORS) {
      const value = withSuffix(suffix);
      assert.throws(() => encodeRelease(value), /Invalid ModelSwarm release/);
      assert.throws(() => parseRelease(JSON.stringify(value)), /Invalid ModelSwarm release/);
      const comment = await fixture({ content: JSON.stringify(value) });
      await assert.rejects(verifyRelease(await withCid(comment)), /Invalid ModelSwarm release/);
    }
  });
}

test('native signatures cannot make a PKC protocolVersion with trailing line terminators valid', async () => {
  for (const suffix of LINE_TERMINATORS) {
    const comment = await fixture({ protocolVersion: `1.0.0${suffix}` });
    await assert.rejects(verifyRelease(await withCid(comment)), /invalid PKC protocolVersion/);
  }
});

test('manifest references accept HTTPS, explicit loopback HTTP, and an IPFS CID', async () => {
  for (const url of [
    'https://models.example/model.json', 'http://127.0.0.1:1234/manifest.json',
    'http://localhost:1234/manifest.json', 'http://[::1]:1234/manifest.json', `ipfs://${await ipfsHash('manifest')}`,
  ]) assert.equal(parseRelease(encodeRelease({ ...release, manifest: { ...release.manifest, url } })).manifest.url, url);
});

test('manifest references reject credentials, fragments, private addresses, and unsafe schemes', () => {
  for (const url of [
    'http://example.com/m', 'file:///etc/passwd', 'https://user:pass@example.com/m',
    'https://example.com/m#fragment', 'https://127.0.0.1/m', 'https://10.0.0.1/m',
    'https://[fd00::1]/m', 'https://[::ffff:127.0.0.1]/m', 'https://intranet/m',
    'https://service.local/m', 'ipfs://not-a-cid', 'ipfs://cid/path', 'https://example.com/\nm',
    'https:example.com/m', 'https://example.com\\m',
  ]) assert.throws(() => encodeRelease({ ...release, manifest: { ...release.manifest, url } }), /Invalid ModelSwarm release/);
});

test('card and record limits count UTF-8 bytes, malformed Unicode and nesting fail closed', async () => {
  assert.throws(() => encodeRelease({ ...release, modelCard: '😀'.repeat(MAX_CARD_BYTES / 4 + 1) }), /exceeds 24 KiB/);
  assert.throws(() => encodeRelease({ ...release, modelCard: '\ud800' }), /well-formed string/);
  const args = await withCid(await fixture());
  await assert.rejects(verifyRelease({ ...args, rawComment: ' '.repeat(MAX_RECORD_BYTES + 1) }), /exceeds 40 KiB/);
  await assert.rejects(verifyRelease({ ...args, rawComment: Buffer.from([0xc0, 0x80]) }), /not valid UTF-8/);
  const comment = await fixture();
  let nested = comment.author = {};
  for (let i = 0; i < 34; i++) nested = nested.nested = {};
  await assert.rejects(verifyRelease(await withCid(comment)), /nesting exceeds/);
});

test('discussion scan distinguishes a full final page from an unfetched successor', async () => {
  for (const pageCount of [4, 5]) {
    const fetched = [];
    const posts = {
      pageCids: { new: '1' },
      async getPage({ cid }) {
        fetched.push(cid);
        const nextCid = Number(cid) < pageCount ? String(Number(cid) + 1) : undefined;
        return { comments: [], nextCid };
      },
    };
    assert.deepEqual(await scanDiscussionFeed(posts), { entries: [], truncated: pageCount > 4 });
    assert.deepEqual(fetched, ['1', '2', '3', '4']);
  }
});

test('discussion scan reports an unseen post beyond the candidate limit', async () => {
  const comments = Array.from({ length: 100 }, (_, i) => ({ cid: String(i) }));
  const posts = { pages: { new: { comments } } };
  assert.deepEqual(await scanDiscussionFeed(posts), { entries: [], truncated: false });
  comments.push(comments[0]);
  assert.deepEqual(await scanDiscussionFeed(posts), { entries: [], truncated: false });
  comments.push({ cid: 'later' });
  assert.deepEqual(await scanDiscussionFeed(posts), { entries: [], truncated: true });
});

test('discussion scan caps verified releases and reports an unscanned successor', async () => {
  const comments = Array.from({ length: 32 }, (_, i) => ({ cid: String(i), crosspost: {} }));
  const posts = { pages: { new: { comments } } };
  const read = async (cid) => ({ cid, release });
  let feed = await scanDiscussionFeed(posts, read);
  assert.equal(feed.entries.length, 32);
  assert.equal(feed.truncated, false);
  posts.pages.new.nextCid = 'later';
  feed = await scanDiscussionFeed(posts, read);
  assert.equal(feed.entries.length, 32);
  assert.equal(feed.truncated, true);
});

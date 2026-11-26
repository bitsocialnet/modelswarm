import assert from 'node:assert/strict';
import { test } from 'node:test';
import { communityHttpsLink, communityTorrentLink } from '../../src/lib/community-links.ts';

test('malformed community mirrors are omitted without throwing', () => {
  for (const value of ['https://a%zz.com/model.gguf', 'https://exa mple.com/weights.gguf', 'https://[broken', null, 12]) {
    assert.equal(communityHttpsLink(value), null);
  }
});

test('community mirror links preserve valid HTTPS and reject other source types', () => {
  assert.deepEqual(communityHttpsLink('https://Example.com/model.gguf?revision=1'), {
    href: 'https://example.com/model.gguf?revision=1',
    hostname: 'example.com',
  });
  for (const value of ['http://example.com/model.gguf', 'https://user@example.com/model.gguf', 'https://example.com/model.gguf#part']) {
    assert.equal(communityHttpsLink(value), null);
  }
});

test('browser-only IPv4 aliases cannot bypass the manifest source policy', () => {
  assert.equal(communityHttpsLink('https://127.1/model.gguf'), null);
  assert.equal(communityHttpsLink('https://0x7f000001/model.gguf'), null);
  assert.equal(communityHttpsLink('https://%31%32%37.0.0.1/model.gguf'), null);
  assert.equal(communityHttpsLink('https://1.1.1.1/model.gguf')?.hostname, '1.1.1.1');
});

test('normalization cannot turn a public community mirror into localhost', () => {
  for (const value of ['https://%6cocalhost/weights.gguf', 'https://localhost./model.gguf', 'https://hub.localhost/model.gguf']) {
    assert.equal(communityHttpsLink(value), null);
  }
});

test('community torrents support custom public directories with no external or traversal links', () => {
  const file = `${'a'.repeat(64)}.torrent`;
  for (const prefix of ['./community-torrents/', './hub-torrents/', './hubs/hub-torrents/']) {
    assert.equal(communityTorrentLink(prefix + file), prefix + file);
  }
  for (const prefix of ['//example.com/', 'https://example.com/', './../', './hubs/../', './hubs/%2e%2e/', './hubs\\']) {
    assert.equal(communityTorrentLink(prefix + file), null);
  }
});

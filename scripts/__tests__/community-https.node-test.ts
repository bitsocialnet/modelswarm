import assert from 'node:assert/strict';
import { test } from 'node:test';
import { communityHttpsLink } from '../../src/lib/community-https.ts';

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

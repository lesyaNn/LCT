import assert from 'node:assert/strict';
import test from 'node:test';
import nextConfig from '../../../next.config.ts';

test('API proxy waits beyond both default model stages but has a finite deadline', () => {
  assert.ok(Number.isFinite(nextConfig.experimental.proxyTimeout));
  assert.ok(nextConfig.experimental.proxyTimeout > 2 * 120_000);
  assert.ok(nextConfig.experimental.proxyTimeout <= 600_000);
});

test('assistant keeps the existing same-origin API rewrite', async () => {
  const rewrites = await nextConfig.rewrites();
  assert.ok(rewrites.some(rule => rule.source === '/api/v1/:path*' && rule.destination.endsWith('/api/v1/:path*')));
});

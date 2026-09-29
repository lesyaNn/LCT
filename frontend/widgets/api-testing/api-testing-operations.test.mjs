import assert from 'node:assert/strict';
import { test } from 'node:test';
import { allowedHeaderNames, findOperation, safeResponse } from './api-testing-operations.ts';

test('only registered method and endpoint pairs can execute', () => {
  assert.equal(findOperation('GET', '/api/v1/universities')?.id, 'universities');
  assert.equal(findOperation('POST', '/api/v1/integrations/lms/ingest')?.id, 'lms');
  assert.equal(findOperation('DELETE', '/api/v1/universities/123'), undefined);
  assert.equal(findOperation('DELETE', '/api/v1/reports/templates/123e4567-e89b-12d3-a456-426614174000')?.id, 'delete-report-template');
  assert.equal(findOperation('DELETE', '/api/v1/reports/templates/123e4567-e89b-12d3-a456-426614174000/extra'), undefined);
  assert.equal(findOperation('GET', 'http://127.0.0.1/secret'), undefined);
  assert.equal(findOperation('GET', 'http://169.254.169.254/latest/meta-data'), undefined);
});

test('security headers cannot be supplied by the request form', () => {
  for (const name of ['authorization', 'cookie', 'set-cookie', 'host', 'origin', 'x-forwarded-for', 'proxy-authorization']) {
    assert.equal(allowedHeaderNames.has(name), false);
  }
});

test('response redaction recursively removes credentials', () => {
  assert.deepEqual(safeResponse({ data: [{ token: 'secret', headers: { Authorization: 'Bearer abc' } }], message: 'ok' }),
    { data: [{ token: '[скрыто]', headers: { Authorization: '[скрыто]' } }], message: 'ok' });
});

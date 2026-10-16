import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../notifications-repository.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const repositoryExports = {};
const apiCalls = [];
runInNewContext(compiled, {
  exports: repositoryExports,
  require: (specifier) => {
    assert.equal(specifier, './api-client');
    return { apiFetch: (path, options) => {
      apiCalls.push({ path, options });
      return Promise.resolve({ ok: true, data: undefined });
    } };
  },
});

test('repository uses the authenticated notifications endpoints', async () => {
  const signal = new AbortController().signal;
  await repositoryExports.notificationsRepository.list('unread', 7, 14, signal);
  await repositoryExports.notificationsRepository.unreadCount(signal);
  await repositoryExports.notificationsRepository.markRead('notification-1');
  await repositoryExports.notificationsRepository.markAllRead();
  assert.deepEqual(apiCalls.map(({ path, options }) => ({ path, method: options?.method ?? 'GET', signal: options?.signal })), [
    { path: '/api/v1/notifications?filter=unread&limit=7&offset=14', method: 'GET', signal },
    { path: '/api/v1/notifications/unread-count', method: 'GET', signal },
    { path: '/api/v1/notifications/notification-1/read', method: 'PATCH', signal: undefined },
    { path: '/api/v1/notifications/read-all', method: 'POST', signal: undefined },
  ]);
});

test('contract notifications open documents and license notifications open licenses', () => {
  const item = { entity_id: 'item-1', university_id: 'university-1' };
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'contract' }),
    '/universities/university-1?tab=documents');
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'license' }),
    '/universities/university-1?tab=licenses');
});

test('notification targets depend on entity metadata, never message text', () => {
  const item = { entity_id: 'workflow-1', university_id: null, title: 'Совсем другой заголовок' };
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'workflow' }), '/workflows/workflow-1');
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'import_job' }), '/admin/import');
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'license' }), null);
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'unknown' }), null);
});

test('unknown backend types keep their text with a neutral existing icon', () => {
  const item = {
    id: 'notification-1', type: 'future_type', title: 'Событие', message: 'Описание',
    created_at: '2026-10-17T10:00:00Z', is_read: false, entity_type: 'unknown',
    entity_id: 'entity-1', university_id: null,
  };
  assert.deepEqual({ ...repositoryExports.notificationPresentation(item) }, {
    id: item.id, type: 'comment', title: item.title, description: item.message,
    createdAt: item.created_at, read: false, target: undefined,
  });
});

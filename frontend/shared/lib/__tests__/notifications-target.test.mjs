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
runInNewContext(compiled, {
  exports: repositoryExports,
  require: (specifier) => {
    assert.equal(specifier, './api-client');
    return { apiFetch: () => { throw new Error('Unexpected API call'); } };
  },
});

test('contract notifications open documents and license notifications open licenses', () => {
  const item = { entity_id: 'item-1', university_id: 'university-1' };
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'contract' }),
    '/universities/university-1?tab=documents');
  assert.equal(repositoryExports.notificationTarget({ ...item, entity_type: 'license' }),
    '/universities/university-1?tab=licenses');
});

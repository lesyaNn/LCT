import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import ts from 'typescript';

const source = readFileSync(fileURLToPath(new URL('../service-api.ts', import.meta.url)), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { filterOperations, mediaExample, operationCurl, resolveSchema, schemaType, readableDescription } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);

const doc = { paths: {}, components: { schemas: {
  Person: { type: 'object', properties: { name: { type: 'string' } } },
  Loop: { $ref: '#/components/schemas/Loop' },
  Status: { type: 'string', enum: ['ready', 'failed'] },
} } };
const operations = [
  { method: 'GET', path: '/api/v1/universities', summary: 'Список вузов', tags: ['Universities'], role_allowed: true },
  { method: 'POST', path: '/api/v1/universities', summary: 'Создать вуз', tags: ['Universities'], role_allowed: false },
  { method: 'GET', path: '/api/v1/reports', summary: 'Список отчётов', tags: ['Reports'], role_allowed: true },
];

test('filters combine method, section, query and role without mutating contract', () => {
  assert.equal(filterOperations(operations, 'ВУЗ', 'GET', 'Universities', true).length, 1);
  assert.equal(filterOperations(operations, '  /reports ', '', '', false).length, 1);
  assert.equal(filterOperations(operations, '', 'POST', '', true).length, 0);
  assert.equal(filterOperations(operations, 'Вузы и встречи', '', '', false).length, 2);
  assert.equal(operations.length, 3);
});

test('schemas resolve local references only and tolerate circular or missing references', () => {
  assert.equal(resolveSchema({ $ref: '#/components/schemas/Person' }, doc).properties.name.type, 'string');
  assert.equal(resolveSchema({ $ref: '#/components/schemas/Loop' }, doc).$ref, '#/components/schemas/Loop');
  assert.equal(resolveSchema({ $ref: 'https://example.org/private' }, doc).$ref, 'https://example.org/private');
  assert.equal(schemaType({ anyOf: [{ $ref: '#/components/schemas/Status' }, { type: 'null' }] }, doc), '"ready" | "failed" | null');
  assert.equal(schemaType({ type: 'array', items: { type: 'string', format: 'uuid' } }, doc), 'Array<uuid>');
});

test('examples preserve null and prefer operation-level examples', () => {
  assert.equal(mediaExample({ example: null, examples: { other: { value: 1 } } }, doc), null);
  assert.equal(mediaExample({ examples: { demo: { value: 2 } } }, doc), 2);
  assert.equal(mediaExample({ schema: { example: 3 } }, doc), 3);
});

test('curl never includes a real credential and quotes apostrophes in JSON', () => {
  const curl = operationCurl(operations[1], { example: { name: "O'Brien" } }, doc);
  assert.ok(curl.includes('Bearer <ACCESS_TOKEN>'));
  assert.ok(curl.includes("O'\\''Brien"));
  assert.ok(curl.includes(" \\\n  --header"));
  assert.ok(!operationCurl(operations[0]).includes('--data-raw'));
  assert.ok(!operationCurl({ ...operations[0], authentication_required: false }).includes('Authorization'));
});

test('prose formatting does not alter paths or technical hyphens', () => {
  assert.equal(readableDescription('Ответ — поле «status». API-v1'), 'Ответ: поле status. API-v1');
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../university-local-time.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { localTimeAt, contactText } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);

test('clock uses university timezone and local date across midnight, independent of browser timezone', () => {
  const instant = Date.parse('2026-10-17T16:30:00Z');
  assert.equal(localTimeAt('Europe/Moscow', instant).time, '19:30:00');
  const east = localTimeAt('Asia/Vladivostok', instant);
  assert.equal(east.time, '02:30:00');
  assert.equal(east.date, '18.10.2026');
  assert.equal(east.offset, 'UTC+10');
});

test('daytime boundaries are calculated in the university timezone', () => {
  const at = hour => localTimeAt('Europe/Moscow', Date.parse(`2026-10-17T${hour}:00:00Z`));
  assert.equal(at('05').outsideDaytime, true);
  assert.equal(at('06').outsideDaytime, false);
  assert.equal(at('14').outsideDaytime, false);
  assert.equal(at('15').outsideDaytime, true);
});

test('unknown and unsupported zones never silently show browser or Moscow time', () => {
  for (const zone of [null, undefined, '', 'Invalid/Zone']) assert.equal(localTimeAt(zone, Date.now()), null);
});

test('copy contact preserves phone formatting and excludes absent placeholders', () => {
  assert.equal(contactText({ name: 'Анна Иванова', role: 'Куратор', phone: '+7 (900) 123-45-67', email: 'anna@example.org' }), 'Анна Иванова\nКуратор\nanna@example.org\n+7 (900) 123-45-67');
  assert.equal(contactText({ name: 'Анна Иванова', role: '', phone: '—' }), 'Анна Иванова');
});

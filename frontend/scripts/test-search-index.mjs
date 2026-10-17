import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';

const root = resolve(import.meta.dirname, '..');
const cache = new Map();
function load(file) {
  const path = resolve(file);
  if (cache.has(path)) return cache.get(path);
  const source = readFileSync(path, 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const loaded = { exports: {} };
  cache.set(path, loaded.exports);
  const requireLocal = (specifier) => load(specifier.startsWith('@/')
    ? resolve(root, specifier.slice(2) + '.ts')
    : resolve(dirname(path), specifier + '.ts'));
  vm.runInNewContext('(function(require,module,exports){' + code + '\n})', { console })(requireLocal, loaded, loaded.exports);
  return loaded.exports;
}

const { searchStaticIndex } = load(resolve(root, 'shared/config/search-index.ts'));
const { navigationItems, getVisibleNavigationItems, canAccessRoute } = load(resolve(root, 'shared/config/navigation.ts'));
const user = (role, permissions) => ({ rawRoles: [role], permissions });
const regular = user('user', ['university.read', 'workflow.read', 'workflow.change_status', 'workflow.task.update', 'workflow.comment.create', 'workflow.attachment.create', 'reports.read']);
const admin = user('admin', ['*']);
const manager = user('manager', [...regular.permissions, 'university_responsible.manage', 'audit.read', 'university.edit', 'user_university.manage']);
const titles = (query, account) => searchStaticIndex(query, account).results.map((item) => item.title);

assert.equal(titles('дедлайн', regular)[0], 'Установить дедлайн');
assert.equal(searchStaticIndex('дедлайн', regular).entityTerm, null);
assert.equal(searchStaticIndex('дедлайн ИТМО', regular).entityTerm, 'итмо');
assert.equal(searchStaticIndex('workflow МФТИ', regular).entityTerm, 'мфти');
assert.equal(searchStaticIndex('запустить workflow', admin).entityTerm, null);
assert.equal(searchStaticIndex('договор ИТМО', regular).entityTerm, 'итмо');
assert.equal(searchStaticIndex('WORKFLOW', regular).entityTerm, null);
assert.ok(titles('запуска', admin).includes('Запустить Workflow'));
assert.equal(searchStaticIndex('ИТМО', regular).entityTerm, 'итмо');
assert.equal(searchStaticIndex('история', regular).results[0].href, '/docs?article=user-guide%2Fhistory');
assert.ok(titles('истор', regular).includes('История изменений'));
assert.equal(titles('запустить', admin)[0], 'Запустить Workflow');
assert.ok(!titles('запустить', regular).includes('Запустить Workflow'));
for (const term of ['задача', 'комментарий', 'файл', 'договор', 'лицензия', 'история', 'срок', 'отчёт', 'отчет', 'отчетт', 'запустт']) {
  assert.ok(titles(term, regular).length, `No result for ${term}`);
}
assert.ok(!titles('импорт', manager).includes('Импорт каталогов'));
assert.ok(titles('импорт', admin).includes('Импорт каталогов'));
assert.ok(titles('аудит', manager).includes('Аудит'));
assert.ok(getVisibleNavigationItems(manager).some((item) => item.href === '/admin/university-assignments'));
assert.ok(!getVisibleNavigationItems(admin).some((item) => item.href === '/admin/university-assignments'));
assert.ok(canAccessRoute('/admin', manager));
assert.ok(canAccessRoute('/admin/university-assignments', manager));
assert.ok(!canAccessRoute('/admin/users', manager));
for (const path of ['/admin/catalogs', '/admin/import']) {
  assert.ok(!getVisibleNavigationItems(manager).some((item) => item.href === path));
  assert.ok(!canAccessRoute(path, manager));
  assert.ok(canAccessRoute(path, admin));
}
assert.ok(titles('приглашение', admin).includes('Пригласить пользователя'));
if (navigationItems.some((item) => item.href === '/api-testing')) {
  assert.ok(titles('api', admin).includes('Тестирование API'));
}
assert.equal(titles('api', regular).length, 0);
assert.ok(!titles('приглашение', regular).includes('Пользователи и права'));
assert.ok(!titles('аудит', regular).includes('Аудит'));
console.log('Search aliases, ranking, residual terms and permissions: passed');

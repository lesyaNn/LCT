import { getVisibleNavigationItems } from './navigation';
import { hasPermission, hasRole } from '@/shared/lib/access-control';
import type { AuthUser } from '@/shared/types/user';
import type { IconName } from '@/shared/types/navigation';

type Metadata = { description: string; keywords: readonly string[] };
type Action = Metadata & { title: string; href: string; icon: IconName; requiredPermission?: string; adminOnly?: boolean };
export type StaticSearchResult = { kind: 'action' | 'navigation'; key: string; title: string; subtitle: string; href: string; icon: IconName; score: number };

// Routes and permissions remain defined in navigation.ts. These terms only
// describe existing pages and actions that can be reached from those pages.
const pageKeywords: Record<string, Metadata> = {
  '/dashboard': { description: 'Обзор показателей и задач', keywords: ['главная', 'сводка', 'показатели'] },
  '/universities': { description: 'Список и паспорта ВУЗов', keywords: ['вуз', 'вузы', 'университет', 'учебное заведение', 'документ', 'договор', 'лицензия', 'ответственный'] },
  '/workflows': { description: 'Процессы, этапы и задачи ВУЗов', keywords: ['воркфлоу', 'процесс', 'маршрут', 'этап', 'дедлайн', 'срок', 'задача', 'комментарий', 'вложение', 'запуск'] },
  '/reports': { description: 'Формирование и скачивание отчётов', keywords: ['отчет', 'статистика', 'график', 'скачать отчет', 'сформировать отчет'] },
  '/audit': { description: 'Журнал действий пользователей', keywords: ['журнал', 'история действий', 'события', 'действия пользователей', 'кто изменил'] },
  '/admin': { description: 'Настройки системы', keywords: ['настройки системы', 'администратор'] },
  '/admin/users': { description: 'Учётные записи, приглашения и роли', keywords: ['пользователь', 'приглашение', 'права', 'роль', 'роли'] },
  '/admin/university-assignments': { description: 'Назначение вузов пользователям и граф связей', keywords: ['пользователь', 'вуз', 'вузы', 'назначение', 'граф связей'] },
  '/admin/catalogs': { description: 'Справочники и каталоги', keywords: ['каталог', 'справочник', 'продукт', 'вендор', 'договор', 'лицензия'] },
  '/admin/import': { description: 'Загрузка каталогов из файла', keywords: ['импорт', 'загрузить excel', 'импорт каталога', 'загрузить файл'] },
  '/admin/workflow/templates': { description: 'Настройка шаблонов Workflow', keywords: ['шаблон процесса', 'шаблон workflow'] },
  '/api-testing': { description: 'Проверка API', keywords: ['api', 'апи', 'тестирование api'] },
  '/api': { description: 'Методы API и подключение сервисов', keywords: ['api', 'апи', 'интеграция', 'openapi', 'rest'] },
  '/docs': { description: 'Справочный центр CRM', keywords: ['справка', 'помощь', 'инструкция', 'документация'] },
};

const actions: readonly Action[] = [
  { title: 'Запустить Workflow', description: 'Открыть паспорт ВУЗа и создать Workflow для программы', href: '/universities', icon: 'workflow', requiredPermission: 'workflow.change_status', adminOnly: true, keywords: ['запустить', 'запуск', 'запускается', 'создать workflow', 'создать воркфлоу', 'начать процесс', 'новый workflow'] },
  { title: 'Установить дедлайн', description: 'Открыть текущий этап Workflow и изменить срок', href: '/workflows', icon: 'workflow', requiredPermission: 'workflow.change_status', keywords: ['дедлайн', 'срок', 'дата этапа', 'установить срок', 'изменить дедлайн'] },
  { title: 'Назначить ответственного', description: 'Открыть ответственных в Workflow', href: '/workflows', icon: 'workflow', requiredPermission: 'university_responsible.manage', keywords: ['назначить ответственного', 'сменить ответственного', 'ответственный', 'менеджер'] },
  { title: 'Добавить задачу', description: 'Открыть задачи текущего этапа Workflow', href: '/workflows', icon: 'workflow', requiredPermission: 'workflow.task.update', keywords: ['задача', 'задачи', 'задачу', 'добавить задачу', 'выполнить задачу'] },
  { title: 'Написать комментарий', description: 'Открыть комментарии этапа Workflow', href: '/workflows', icon: 'workflow', requiredPermission: 'workflow.comment.create', keywords: ['комментарий', 'комментарии', 'написать комментарий', 'редактировать комментарий'] },
  { title: 'Прикрепить файл', description: 'Открыть вложения этапа Workflow', href: '/workflows', icon: 'workflow', requiredPermission: 'workflow.attachment.create', keywords: ['файл', 'вложение', 'прикрепить', 'скачать файл'] },
  { title: 'Договоры ВУЗа', description: 'Открыть документы и договоры в паспорте ВУЗа', href: '/universities', icon: 'university', keywords: ['договор', 'договора', 'договоры', 'контракт'] },
  { title: 'Лицензии ВУЗа', description: 'Открыть лицензии в паспорте ВУЗа', href: '/universities', icon: 'university', keywords: ['лицензия', 'лицензии', 'лицензию'] },
  { title: 'История изменений', description: 'Как открыть историю ВУЗа, Workflow и журнал аудита', href: '/docs?article=user-guide%2Fhistory', icon: 'docs', keywords: ['история', 'изменения', 'кто изменил'] },
  { title: 'Скачать отчёт', description: 'Открыть раздел формирования и скачивания отчётов', href: '/reports', icon: 'report', keywords: ['скачать отчет', 'сформировать отчет', 'отчет за месяц'] },
  { title: 'Импортировать каталоги', description: 'Открыть загрузку каталогов из файла', href: '/admin/import', icon: 'admin', keywords: ['импорт', 'загрузить excel', 'импорт каталога'] },
  { title: 'Пригласить пользователя', description: 'Открыть пользователей и права', href: '/admin/users', icon: 'admin', keywords: ['пригласить пользователя', 'приглашение', 'создать приглашение', 'назначить роль'] },
];

export function normalizeSearchText(value: string): string {
  return value.toLocaleLowerCase('ru').replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ');
}

function similarToken(query: string, keyword: string): boolean {
  if (query === keyword) return true;
  if (Math.min(query.length, keyword.length) >= 5 && query.slice(0, 5) === keyword.slice(0, 5)) return true;
  if (query.length < 5 || Math.abs(query.length - keyword.length) > 1) return false;
  let edits = 0;
  for (let left = 0, right = 0; left < query.length && right < keyword.length;) {
    if (query[left] === keyword[right]) { left++; right++; continue; }
    if (++edits > 1) return false;
    if (query.length >= keyword.length) left++;
    if (query.length <= keyword.length) right++;
  }
  return true;
}

function match(query: string, phrase: string): number {
  const alias = normalizeSearchText(phrase);
  if (!alias) return 0;
  if (query === alias) return 100 + alias.length;
  if (` ${query} `.includes(` ${alias} `)) return 70 + alias.length;
  if (query.length >= 3 && alias.includes(query)) return 45 + query.length;
  if (!query.includes(' ') && !alias.includes(' ') && similarToken(query, alias)) return 35;
  return 0;
}

export function searchStaticIndex(query: string, user: AuthUser): { results: StaticSearchResult[]; entityTerm: string | null } {
  const term = normalizeSearchText(query);
  if (term.length < 2) return { results: [], entityTerm: null };
  const visible = getVisibleNavigationItems(user);
  const visibleHrefs = new Set(visible.map((item) => item.href));
  const candidates: StaticSearchResult[] = [];
  const matchedAliases: string[] = [];
  for (const item of visible) {
    const meta = pageKeywords[item.href];
    const phrases = [item.label, ...(meta ? [meta.description, ...meta.keywords] : [])];
    const score = Math.max(...phrases.map((phrase) => match(term, phrase)));
    if (score) {
      candidates.push({ kind: 'navigation', key: `n-${item.href}`, title: item.label, subtitle: meta?.description ?? 'Раздел системы', href: item.href, icon: item.icon, score });
      matchedAliases.push(...phrases.filter((phrase) => match(term, phrase) >= 70));
    }
  }
  for (const action of actions) {
    if (!visibleHrefs.has(action.href.split('?')[0]) || (action.requiredPermission && !hasPermission(user, action.requiredPermission)) || (action.adminOnly && !hasRole(user, 'admin'))) continue;
    const score = Math.max(...action.keywords.map((phrase) => match(term, phrase)));
    if (score) {
      candidates.push({ kind: 'action', key: `a-${action.title}`, title: action.title, subtitle: action.description, href: action.href, icon: action.icon, score: score + 15 });
      matchedAliases.push(...action.keywords.filter((phrase) => match(term, phrase) >= 70));
    }
  }
  candidates.sort((left, right) => right.score - left.score || (left.kind === 'action' ? -1 : 1));
  // Remove all recognized words/phrases before searching real data. This
  // keeps "запустить workflow" local, while "дедлайн ИТМО" queries ITMO.
  let residual = term;
  for (const alias of [...new Set(matchedAliases.map(normalizeSearchText))].sort((left, right) => right.length - left.length)) {
    residual = normalizeSearchText(` ${residual} `.replace(` ${alias} `, ' '));
  }
  if (!matchedAliases.length && candidates.length) residual = '';
  return { results: candidates.slice(0, 3), entityTerm: residual.length >= 2 ? residual : null };
}

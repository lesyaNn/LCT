export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type Operation = { id: string; label: string; method: Method; endpoint: string; query?: readonly string[]; description: string; mutates?: boolean };

// Fixed browser-side registry. All routes are existing FastAPI routes, with their own RBAC.
export const operations: readonly Operation[] = [
  { id: 'universities', label: 'Список ВУЗов', method: 'GET', endpoint: '/api/v1/universities', query: ['page', 'page_size', 'search', 'city'], description: 'Данные CRM' },
  { id: 'me', label: 'Текущий пользователь', method: 'GET', endpoint: '/api/v1/auth/me', description: 'Данные текущей сессии' },
  { id: 'capabilities', label: 'Состояние интеграций', method: 'GET', endpoint: '/api/v1/integrations/capabilities', description: 'Внешние адаптеры' },
  { id: 'lms', label: 'Входящий JSON LMS', method: 'POST', endpoint: '/api/v1/integrations/lms/ingest', description: 'Статистика программ', mutates: true },
  { id: 'website', label: 'Входящий JSON веб-сайта', method: 'POST', endpoint: '/api/v1/integrations/website/ingest', description: 'Заявки сайта', mutates: true },
  { id: 'report-templates', label: 'Шаблоны отчётов', method: 'GET', endpoint: '/api/v1/reports/templates', description: 'Список сохранённых шаблонов' },
  { id: 'delete-report-template', label: 'Удалить шаблон отчёта', method: 'DELETE', endpoint: '/api/v1/reports/templates/{template_id}', description: 'Удаляет один шаблон по UUID', mutates: true },
];

export function findOperation(method: Method, endpoint: string): Operation | undefined {
  const path = endpoint.trim();
  const exact = operations.find((item) => item.method === method && item.endpoint === path);
  if (exact) return exact;
  if (method === 'DELETE' && /^\/api\/v1\/reports\/templates\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(path)) {
    return { ...operations.find((item) => item.id === 'delete-report-template')!, endpoint: path };
  }
  return undefined;
}

export const allowedHeaderNames = new Set(['accept', 'accept-language', 'x-request-id']);
export const unavailableMessage = 'Этот endpoint недоступен в инструменте тестирования API.';

export function safeResponse(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeResponse);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    /authorization|cookie|secret|password|token|credential|api.?key|private.?key/i.test(key) ? '[скрыто]' : safeResponse(item)]));
  if (typeof value === 'string') {
    if (/bearer\s+\S+|(?:access|refresh)[_-]?token|client_secret|traceback|stack trace|select\s+.*\s+from\s+/i.test(value)) return '[скрыто]';
    return value.length > 10000 ? `${value.slice(0, 10000)}…` : value;
  }
  return value;
}

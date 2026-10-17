export type ApiOperation = {
  operation_id: string;
  method: string;
  path: string;
  summary: string;
  tags: string[];
  required_permissions: string[];
  allowed_roles: string[];
  role_allowed: boolean;
  deprecated: boolean;
};

export type ServiceApiCatalog = {
  version: string;
  base_path: string;
  openapi_path: string;
  operation_count: number;
  role: string;
  operations: ApiOperation[];
  limits: {
    heavy_requests_per_minute: number;
    heavy_paths: string[];
    assistant_requests_per_minute: number;
    assistant_timeout_seconds: number;
    max_upload_mb: number;
  };
  errors: Array<{ code: string; status: number; message: string }>;
};

export type JsonSchema = {
  $ref?: string;
  type?: string;
  title?: string;
  format?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  enum?: unknown[];
  default?: unknown;
  example?: unknown;
  examples?: unknown[];
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
};

export type Media = { schema?: JsonSchema; example?: unknown; examples?: Record<string, { value?: unknown }> };
export type Parameter = { name: string; in: string; required?: boolean; description?: string; schema?: JsonSchema };
export type OpenApiOperation = {
  description?: string;
  parameters?: Parameter[];
  requestBody?: { required?: boolean; content?: Record<string, Media> };
  responses?: Record<string, { description?: string; content?: Record<string, Media> }>;
};
export type OpenApiDocument = {
  openapi: string;
  info: { version: string; title: string };
  paths: Record<string, Record<string, OpenApiOperation>>;
  components?: { schemas?: Record<string, JsonSchema> };
};

export const apiGroupNames: Record<string, string> = {
  Universities: 'Вузы и встречи', Workflow: 'Workflow', Programs: 'Программы',
  Directions: 'Направления', Products: 'Продукты', Vendors: 'Вендоры',
  Contracts: 'Договоры', Licenses: 'Лицензии', Responsibles: 'Ответственные',
  Reports: 'Отчёты', Analytics: 'Аналитика', Import: 'Импорт', Audit: 'Аудит',
  Assistant: 'ИИ-помощник', Auth: 'Авторизация', Notifications: 'Уведомления',
  'Admin Users': 'Пользователи', 'External integrations': 'Внешние интеграции',
  'Meeting agenda': 'Повестка встречи', 'Education statistics': 'Статистика обучения',
  'Teacher training': 'Преподаватели', Catalog: 'Обзор каталога', search: 'Поиск',
  'Service API': 'Контракт API',
};

export function readableDescription(text = ''): string {
  return text.replace(/[«»]/g, '').replace(/\s*[—–]\s*/g, ': ');
}

export function resolveSchema(schema: JsonSchema | undefined, document: OpenApiDocument): JsonSchema {
  let current = schema ?? {};
  const seen = new Set<string>();
  while (current.$ref?.startsWith('#/components/schemas/') && !seen.has(current.$ref)) {
    seen.add(current.$ref);
    const key = current.$ref.slice('#/components/schemas/'.length).replaceAll('~1', '/').replaceAll('~0', '~');
    const target = document.components?.schemas?.[key];
    if (!target) break;
    current = target;
  }
  return current;
}

export function schemaType(schema: JsonSchema | undefined, document: OpenApiDocument, depth = 0): string {
  if (!schema || depth > 8) return 'object';
  const value = resolveSchema(schema, document);
  const union = value.anyOf ?? value.oneOf;
  if (union) return union.map(item => schemaType(item, document, depth + 1)).join(' | ');
  if (value.enum) return value.enum.map(item => JSON.stringify(item)).join(' | ');
  if (value.type === 'array') return `Array<${schemaType(value.items, document, depth + 1)}>`;
  return value.format ?? value.type ?? (value.properties ? 'object' : value.title ?? 'object');
}

export function mediaExample(media: Media, document: OpenApiDocument): unknown {
  if (media.example !== undefined) return media.example;
  const named = Object.values(media.examples ?? {}).find(item => item.value !== undefined);
  if (named) return named.value;
  const schema = resolveSchema(media.schema, document);
  return schema.example ?? schema.examples?.[0];
}

export function operationCurl(operation: ApiOperation, media?: Media, document?: OpenApiDocument): string {
  const lines = [
    `curl --request ${operation.method} 'https://crm.example${operation.path}'`,
    "  --header 'Authorization: Bearer <ACCESS_TOKEN>'",
  ];
  const example = media && document ? mediaExample(media, document) : undefined;
  if (example !== undefined) {
    lines.push("  --header 'Content-Type: application/json'");
    const json = JSON.stringify(example).replaceAll("'", "'\\''");
    lines.push(`  --data-raw '${json}'`);
  }
  return lines.join(' \\\n');
}

export function filterOperations(operations: ApiOperation[], query: string, method: string, group: string, allowedOnly: boolean): ApiOperation[] {
  const normalized = query.trim().toLocaleLowerCase('ru-RU');
  return operations.filter(item => (!method || item.method === method)
    && (!group || item.tags.includes(group))
    && (!allowedOnly || item.role_allowed)
    && `${item.path} ${item.summary} ${item.tags.map(tag => apiGroupNames[tag] ?? tag).join(' ')}`.toLocaleLowerCase('ru-RU').includes(normalized));
}

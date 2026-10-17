'use client';

import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiFetch } from '@/shared/lib/api-client';
import {
  apiGroupNames, filterOperations, mediaExample, operationCurl, readableDescription,
  resolveSchema, schemaType, type ApiOperation, type JsonSchema, type Media,
  type OpenApiDocument, type ServiceApiCatalog,
} from '@/shared/lib/service-api';
import { useAuth } from '@/shared/auth/AuthProvider';
import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import styles from './api-documentation-page.module.css';

function Code({ value }: { value: unknown }) {
  return <pre className={styles.code}><code>{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</code></pre>;
}

function SchemaView({ schema, document, depth = 0 }: { schema?: JsonSchema; document: OpenApiDocument; depth?: number }) {
  if (!schema) return <p>Тело не описано.</p>;
  const resolved = resolveSchema(schema, document);
  const properties = resolved.properties;
  if (!properties) return <><p><code>{schemaType(schema, document)}</code></p><Code value={resolved} />
    {resolved.items && depth < 2 ? <details><summary>Поля элемента массива</summary><SchemaView schema={resolved.items} document={document} depth={depth + 1} /></details> : null}</>;
  return <div className={styles.tableWrap}><table><thead><tr><th>Поле</th><th>Тип</th><th>Обязательно</th><th>Правила</th></tr></thead><tbody>
    {Object.entries(properties).map(([name, field]) => {
      const value = resolveSchema(field, document);
      const constraints = [
        value.minLength !== undefined ? `Длина от ${value.minLength}` : '',
        value.maxLength !== undefined ? `Длина до ${value.maxLength}` : '',
        value.minimum !== undefined ? `Минимум ${value.minimum}` : '',
        value.maximum !== undefined ? `Максимум ${value.maximum}` : '',
        value.pattern ? `Шаблон ${value.pattern}` : '',
        value.default !== undefined ? `По умолчанию ${JSON.stringify(value.default)}` : '',
      ].filter(Boolean).join('. ');
      const nested = value.properties || value.items || value.anyOf || value.oneOf;
      return <tr key={name}><td><code>{name}</code></td><td><code>{schemaType(field, document)}</code></td><td>{resolved.required?.includes(name) ? 'Да' : 'Нет'}</td><td>{readableDescription(value.description)}{constraints ? <p>{constraints}</p> : null}
        {nested && depth < 2 ? <details><summary>Структура поля</summary><SchemaView schema={field} document={document} depth={depth + 1} /></details> : null}</td></tr>;
    })}
  </tbody></table></div>;
}

function MediaView({ content, document }: { content?: Record<string, Media>; document: OpenApiDocument }) {
  if (!content || !Object.keys(content).length) return <p>Без тела ответа.</p>;
  return Object.entries(content).map(([contentType, media]) => <div key={contentType}>
    <p><code>{contentType}</code></p>
    {mediaExample(media, document) !== undefined ? <><h4>Пример JSON</h4><Code value={mediaExample(media, document)} /></> : null}
    <SchemaView schema={media.schema} document={document} />
    <details><summary>JSON Schema</summary><Code value={resolveSchema(media.schema, document)} /></details>
  </div>);
}

function OperationDetails({ operation, document }: { operation: ApiOperation; document: OpenApiDocument }) {
  const spec = document.paths[operation.path]?.[operation.method.toLowerCase()];
  if (!spec) return <p role="alert">Метод отсутствует в загруженной схеме. Обновите контракт.</p>;
  const json = spec.requestBody?.content?.['application/json'];
  return <div className={styles.operationBody}>
    <p>{readableDescription(spec.description)}</p>
    <p>Роли: <strong>{operation.allowed_roles.join(', ') || 'Нет разрешённых ролей'}</strong></p>
    {operation.required_permissions.length ? <p>Права: <code>{operation.required_permissions.join(', ')}</code></p> : null}
    <p className={styles.hint}>Это проверка роли. Доступ к вузу, авторство, статус объекта и другие условия проверяются при вызове.</p>
    {spec.parameters?.length ? <><h3>Параметры</h3><div className={styles.tableWrap}><table><thead><tr><th>Имя</th><th>Где передать</th><th>Тип</th><th>Обязательно</th><th>Описание</th></tr></thead><tbody>{spec.parameters.map(parameter => <tr key={`${parameter.in}-${parameter.name}`}><td><code>{parameter.name}</code></td><td>{parameter.in}</td><td><code>{schemaType(parameter.schema, document)}</code></td><td>{parameter.required ? 'Да' : 'Нет'}</td><td>{readableDescription(parameter.description)}{parameter.schema?.default !== undefined ? <p>По умолчанию {JSON.stringify(parameter.schema.default)}</p> : null}</td></tr>)}</tbody></table></div></> : null}
    {spec.requestBody ? <><h3>Тело запроса{spec.requestBody.required ? ' (обязательно)' : ''}</h3><MediaView content={spec.requestBody.content} document={document} /></> : <p>Тело запроса не требуется.</p>}
    <h3>Пример curl</h3><p className={styles.hint}>Замените адрес, ACCESS_TOKEN и параметры в фигурных скобках. Пример не выполняется на этой странице. Для multipart передавайте файл через --form.</p><Code value={operationCurl(operation, json, document)} />
    <h3>Ответы</h3>{Object.entries(spec.responses ?? {}).map(([status, response]) => <details className={styles.response} key={status}><summary>HTTP {status}: {readableDescription(response.description)}</summary><MediaView content={response.content} document={document} /></details>)}
  </div>;
}

export function ApiDocumentationPage({ guide }: { guide: string }) {
  const { user } = useAuth();
  const [tab, setTab] = useState('guide');
  const [catalog, setCatalog] = useState<ServiceApiCatalog | null>(null);
  const [document, setDocument] = useState<OpenApiDocument | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState('');
  const [method, setMethod] = useState('');
  const [group, setGroup] = useState('');
  const [allowedOnly, setAllowedOnly] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const accountKey = `${user?.id ?? ''}:${user?.role ?? ''}`;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setCatalog(null);
      setDocument(null);
      setError('');
      const [catalogResult, schemaResult] = await Promise.all([
        apiFetch<ServiceApiCatalog>('/api/v1/service-api', { signal: controller.signal }),
        apiFetch<OpenApiDocument>('/api/v1/openapi.json', { signal: controller.signal }),
      ]);
      if (!active) return;
      if (!catalogResult.ok || !schemaResult.ok) {
        setError('Не удалось загрузить контракт API. Проверьте подключение и сессию, затем повторите загрузку.');
        return;
      }
      setCatalog(catalogResult.data);
      setDocument(schemaResult.data);
    });
    return () => { active = false; controller.abort(); };
  }, [accountKey, attempt]);

  const groups = useMemo(() => [...new Set(catalog?.operations.flatMap(item => item.tags) ?? [])]
    .sort((left, right) => (apiGroupNames[left] ?? left).localeCompare(apiGroupNames[right] ?? right, 'ru')), [catalog]);
  const operations = useMemo(() => filterOperations(catalog?.operations ?? [], query, method, group, allowedOnly), [catalog, query, method, group, allowedOnly]);
  const tabs = [{ id: 'guide', label: 'Подключение и примеры' }, { id: 'methods', label: 'Все методы' }, { id: 'errors', label: 'Ошибки и ограничения' }];

  function downloadSchema() {
    if (!document) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' }));
    const link = window.document.createElement('a');
    link.href = url;
    link.download = 'crm-openapi.json';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className={styles.page}>
    <div className={styles.toolbar}><p>Базовый путь <code>/api/v1</code>{catalog ? ` · Версия ${catalog.version} · Методов ${catalog.operation_count}` : ''}</p><div className={styles.actions}><Button disabled={!document} onClick={downloadSchema}>Скачать OpenAPI</Button><ButtonLink href="/docs?article=api%2Fintegration">Открыть инструкцию</ButtonLink></div></div>
    <p className={styles.hint}>Справочник загружается с текущего бэкенда. Просмотр документации не создаёт и не удаляет данные CRM.</p>
    {error ? <div className={styles.notice} role="alert"><p>{error}</p><Button onClick={() => setAttempt(value => value + 1)}>Повторить загрузку</Button></div> : !catalog ? <p role="status">Загрузка контракта API…</p> : null}
    <div className={styles.tabs} role="tablist" aria-label="Разделы API">{tabs.map((item, index) => <button type="button" id={`api-tab-${item.id}`} role="tab" aria-selected={tab === item.id} aria-controls={`api-panel-${item.id}`} tabIndex={tab === item.id ? 0 : -1} key={item.id} onClick={() => setTab(item.id)} onKeyDown={event => {
      if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
      setTab(tabs[next].id);
      window.document.getElementById(`api-tab-${tabs[next].id}`)?.focus();
    }}>{item.label}</button>)}</div>
    <div id={`api-panel-${tab}`} role="tabpanel" aria-labelledby={`api-tab-${tab}`}>
      {tab === 'guide' ? <article className={styles.markdown}><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        table: ({ children, ...props }) => <div className={styles.tableWrap}><table {...props}>{children}</table></div>,
        pre: ({ children }) => <pre className={styles.code}>{children}</pre>,
        a: ({ href, children }) => <a href={href} rel={href?.startsWith('https://') ? 'noopener noreferrer' : undefined}>{children}</a>,
      }}>{guide}</ReactMarkdown></article> : null}
      {tab === 'methods' && catalog && document ? <>
        <div className={styles.filters}>
          <label>Поиск<Input type="search" aria-label="Поиск методов" placeholder="Путь или название метода" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <label>Метод<Select aria-label="Метод" value={method} onChange={event => setMethod(event.target.value)}><option value="">Все методы</option>{['GET', 'POST', 'PATCH', 'PUT', 'DELETE'].map(item => <option key={item}>{item}</option>)}</Select></label>
          <label>Раздел<Select aria-label="Раздел" value={group} onChange={event => setGroup(event.target.value)}><option value="">Все разделы</option>{groups.map(item => <option key={item} value={item}>{apiGroupNames[item] ?? item}</option>)}</Select></label>
        </div>
        <label className={styles.checkbox}><input type="checkbox" checked={allowedOnly} onChange={event => setAllowedOnly(event.target.checked)} />Только разрешённые моей роли</label><p role="status">Найдено методов: {operations.length}</p>
        <div className={styles.operationList}>{operations.map(operation => <div className={styles.operation} key={operation.operation_id}>
          <button className={styles.operationHeader} type="button" aria-expanded={expanded === operation.operation_id} aria-controls={`operation-${operation.operation_id}`} onClick={() => setExpanded(value => value === operation.operation_id ? null : operation.operation_id)}><span className={styles.method} data-method={operation.method}>{operation.method}</span><code>{operation.path}</code><span>{readableDescription(operation.summary)}</span><small>{operation.deprecated ? 'Устаревает' : operation.role_allowed ? 'Роль разрешена' : 'Нет прав роли'}</small></button>
          {expanded === operation.operation_id ? <div id={`operation-${operation.operation_id}`}><OperationDetails operation={operation} document={document} /></div> : null}
        </div>)}</div>{!operations.length ? <p>По этим условиям ничего не найдено. Измените фильтр.</p> : null}
      </> : null}
      {tab === 'errors' && catalog ? <>
        <h2>Ограничения текущего стенда</h2><p>Для тяжёлых запросов: {catalog.limits.heavy_requests_per_minute > 0 ? `${catalog.limits.heavy_requests_per_minute} в минуту на токен или IP` : 'общий лимит отключён'}. Ограничение применяется только к путям ниже.</p><Code value={catalog.limits.heavy_paths} />
        <p>ИИ: {catalog.limits.assistant_requests_per_minute} запросов в минуту на пользователя. Таймаут обращения к модели: {catalog.limits.assistant_timeout_seconds} секунд. Максимальный размер загрузки в настройках: {catalog.limits.max_upload_mb} МБ. У отдельных методов могут быть дополнительные ограничения.</p>
        <h2>Коды ошибок</h2><p>Проверяйте error.code. Для обращения к поддержке сохраните error.request_id. Не сохраняйте токен или тело запроса в журнал ошибок.</p><Code value={{ error: { code: 'NOT_FOUND', message: 'Запрашиваемый ресурс не найден.', request_id: '11111111-1111-4111-8111-111111111111', details: {} } }} />
        <div className={styles.tableWrap}><table><thead><tr><th>HTTP</th><th>Код</th><th>Сообщение</th></tr></thead><tbody>{catalog.errors.map(item => <tr key={item.code}><td>{item.status}</td><td><code>{item.code}</code></td><td>{readableDescription(item.message)}</td></tr>)}</tbody></table></div>
      </> : null}
    </div>
  </section>;
}

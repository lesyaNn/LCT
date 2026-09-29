'use client';

import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/shared/lib/api-client';
import { Button } from '@/shared/ui/rtk/button';
import { Input, Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { allowedHeaderNames, findOperation, operations, safeResponse, unavailableMessage, type Method, type Operation } from './api-testing-operations';
import styles from './api-testing-page.module.css';

type Pair = { key: string; value: string };
type Result = { status: number; duration: number; size: number; body: unknown; ok: boolean };
type HistoryEntry = { at: string; method: Method; endpoint: string; status: number; duration: number };
const historyKey = 'crm-api-testing-history-v1';
const methods: Method[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const statusLabels: Record<number, string> = { 400: 'Некорректные данные запроса', 401: 'Не выполнена авторизация', 403: 'Недостаточно прав', 404: 'Метод или объект не найден', 422: 'Ошибка проверки данных', 500: 'Внутренняя ошибка сервера', 503: 'Сервис недоступен' };
const clock = () => performance.now();
const currentDate = () => new Date();

function printable(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '';
}

function formatJson(value: string): string {
  return JSON.stringify(JSON.parse(value), null, 2);
}

function toCurl(method: Method, endpoint: string, params: Pair[], headers: Pair[], body: string): string {
  const query = new URLSearchParams(params.filter((item) => item.key && item.value).map((item) => [item.key, item.value]));
  const url = `${typeof window === 'undefined' ? 'https://crm.example' : window.location.origin}${endpoint}${query.size ? `?${query}` : ''}`;
  const quote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
  const parts = [`curl -X ${method} ${quote(url)}`, "-H 'Authorization: Bearer <token>'"];
  for (const header of headers.filter((item) => allowedHeaderNames.has(item.key.toLowerCase()) && item.value)) parts.push(`-H ${quote(`${header.key}: ${header.value}`)}`);
  if (['POST', 'PUT', 'PATCH'].includes(method) && body.trim()) parts.push("-H 'Content-Type: application/json'", `-d ${quote(body)}`);
  return parts.join(' \\\n  ');
}

export function ApiTestingPage() {
  const [access, setAccess] = useState<'loading' | 'allowed' | 'denied'>('loading');
  const [method, setMethod] = useState<Method>('GET');
  const [endpoint, setEndpoint] = useState('/api/v1/universities');
  const [activePreset, setActivePreset] = useState('universities');
  const [params, setParams] = useState<Pair[]>([]);
  const [headers, setHeaders] = useState<Pair[]>([]);
  const [body, setBody] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    let active = true;
    void apiFetch('/api/v1/auth/test/admin').then((response) => { if (active) setAccess(response.ok ? 'allowed' : 'denied'); });
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(historyKey) ?? '[]');
      if (Array.isArray(stored)) void Promise.resolve().then(() => { if (active) setHistory(stored.filter((item) => item && typeof item.endpoint === 'string' && typeof item.method === 'string').slice(0, 10)); });
    } catch { /* Corrupt local history is ignored. */ }
    return () => { active = false; };
  }, []);

  const operation = findOperation(method, endpoint);
  const curl = useMemo(() => findOperation(method, endpoint) ? toCurl(method, endpoint, params, headers, body) : unavailableMessage, [method, endpoint, params, headers, body]);

  async function selectPreset(item: Operation) {
    setMethod(item.method);
    setEndpoint(item.endpoint);
    setActivePreset(item.id);
    setParams([]);
    setHeaders([]);
    setResult(null);
    setError(null);
    if (item.id !== 'lms' && item.id !== 'website') { setBody(''); return; }

    // Load real CRM IDs for a usable incoming JSON example. No data is submitted here.
    const universities = await apiFetch<{ items: { id: string }[] }>('/api/v1/universities?page_size=20');
    if (!universities.ok || !universities.data.items.length) {
      setBody(JSON.stringify({ university_id: '<UUID ВУЗа>', [item.id === 'lms' ? 'programs' : 'applications']: [] }, null, 2));
      return;
    }
    const universityId = universities.data.items[0].id;
    const programs = await apiFetch<{ items: { id: string }[] }>(`/api/v1/universities/${encodeURIComponent(universityId)}/passport/programs?page_size=1`);
    const programId = programs.ok ? programs.data.items[0]?.id : undefined;
    const sample = item.id === 'lms'
      ? { university_id: universityId, programs: programId ? [{ program_id: programId, learners_count: 24, flows_count: 2 }] : [] }
      : { university_id: universityId, applications: programId ? [{ external_id: `api-demo-${currentDate().getTime()}`, program_id: programId, status: 'new', external_created_at: currentDate().toISOString() }] : [] };
    setBody(JSON.stringify(sample, null, 2));
  }

  function updatePair(items: Pair[], setter: (next: Pair[]) => void, index: number, field: keyof Pair, value: string) {
    setter(items.map((item, position) => position === index ? { ...item, [field]: value } : item));
  }

  async function execute() {
    setError(null);
    if (access !== 'allowed') { setError('Недостаточно прав для тестирования API.'); return; }
    if (!operation) { setError(unavailableMessage); return; }
    if (params.some((item) => !item.key || !operation.query?.includes(item.key))) { setError('Недоступный параметр запроса.'); return; }
    if (headers.some((item) => !allowedHeaderNames.has(item.key.toLowerCase()) || /[\r\n]/.test(item.value))) { setError('Этот заголовок недоступен в инструменте тестирования API.'); return; }
    let payload: unknown;
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      try { payload = JSON.parse(body); }
      catch (cause) { setError(`Некорректный формат JSON: ${cause instanceof Error ? cause.message : 'ошибка синтаксиса'}`); return; }
    }
    const query = new URLSearchParams(params.filter((item) => item.value).map((item) => [item.key, item.value]));
    setPending(true);
    const started = clock();
    try {
      const response = await apiFetch<unknown>(`${operation.endpoint}${query.size ? `?${query}` : ''}`, {
        method, body: payload, headers: Object.fromEntries(headers.filter((item) => item.key).map((item) => [item.key, item.value])),
      });
      const duration = Math.round(clock() - started);
      const responseBody = safeResponse(response.ok ? response.data : response.body ?? statusLabels[response.status] ?? response.error);
      const size = new TextEncoder().encode(printable(responseBody)).length;
      setResult({ status: response.status, duration, size, body: responseBody, ok: response.ok });
      const next = [{ at: currentDate().toISOString(), method, endpoint: operation.endpoint, status: response.status, duration }, ...history].slice(0, 10);
      setHistory(next);
      sessionStorage.setItem(historyKey, JSON.stringify(next));
    } catch {
      setError('Не удалось выполнить запрос. Попробуйте ещё раз.');
    } finally { setPending(false); setConfirmDelete(false); }
  }

  function clear() { setResult(null); setError(null); setParams([]); setHeaders([]); setBody(''); }
  function restore(item: HistoryEntry) { setMethod(item.method); setEndpoint(item.endpoint); setActivePreset(findOperation(item.method, item.endpoint)?.id ?? ''); clear(); }

  if (access === 'loading') return <div className={styles.surface}>Проверяем доступ…</div>;
  if (access === 'denied') return <div className={styles.surface} role="alert">Недостаточно прав для раздела «Тестирование API».</div>;

  return <div className={styles.page}>
    <section className={styles.surface} aria-labelledby="presets-title">
      <h2 id="presets-title">Готовые сценарии</h2>
      <div className={styles.presets}>{operations.filter((item) => ['lms', 'website', 'universities', 'me', 'capabilities'].includes(item.id)).map((item) =>
        <button type="button" key={item.id} className={`${styles.preset} ${activePreset === item.id ? styles.selected : ''}`} onClick={() => void selectPreset(item)} aria-pressed={activePreset === item.id}>
          <strong>{item.label}</strong><span>{item.description}</span>
        </button>)}</div>
      <p className={styles.note}>Внешние LMS и веб-сайт не настроены. Сценарии отправляют JSON в реальные входящие API CRM.</p>
    </section>

    <div className={styles.columns}>
      <section className={styles.surface} aria-labelledby="request-title">
        <h2 id="request-title">Настройка запроса</h2>
        <div className={styles.methodRow}><label>HTTP Method<Select value={method} onChange={(event) => { setMethod(event.target.value as Method); setActivePreset(''); }}>{methods.map((value) => <option key={value}>{value}</option>)}</Select></label><label>Endpoint<Input value={endpoint} onChange={(event) => { setEndpoint(event.target.value); setActivePreset(''); }} spellCheck={false} /></label></div>
        {operation?.query?.length ? <p className={styles.hint}>Доступные параметры: {operation.query.join(', ')}</p> : null}
        {method === 'DELETE' ? <p className={styles.hint}>Разрешён только DELETE /api/v1/reports/templates/{'{UUID}'} для шаблона отчёта.</p> : null}
        <h3>Параметры запроса</h3>
        <PairRows items={params} onChange={setParams} update={(index, field, value) => updatePair(params, setParams, index, field, value)} addLabel="Добавить параметр" />
        <details className={styles.details}><summary>Заголовки</summary><p className={styles.hint}>Разрешены Accept, Accept-Language и X-Request-ID. Авторизация добавляется автоматически.</p><PairRows items={headers} onChange={setHeaders} update={(index, field, value) => updatePair(headers, setHeaders, index, field, value)} addLabel="Добавить заголовок" /></details>
        {['POST', 'PUT', 'PATCH'].includes(method) ? <div className={styles.body}><div className={styles.row}><h3>Тело запроса</h3><Button type="button" size="s" variant="ghost" onClick={() => { try { setBody(formatJson(body)); setError(null); } catch { setError('Некорректный формат JSON'); } }}>Форматировать JSON</Button></div><TextArea aria-label="Тело запроса JSON" rows={12} value={body} onChange={(event) => setBody(event.target.value)} spellCheck={false} className={styles.editor} /></div> : null}
        {operation?.mutates ? <p className={styles.warning}>Этот запрос изменяет данные CRM.</p> : null}
        {error ? <p role="alert" className={styles.error}>{error}</p> : null}
        <div className={styles.actions}><Button type="button" variant="primary" loading={pending} disabled={pending} onClick={() => method === 'DELETE' ? setConfirmDelete(true) : void execute()}>{pending ? 'Выполняется...' : 'Отправить запрос'}</Button><Button type="button" onClick={clear}>Очистить</Button></div>
        <div className={styles.curl}><div className={styles.row}><h3>Пример запроса</h3><Button type="button" size="s" variant="ghost" onClick={() => void navigator.clipboard.writeText(curl)}>Копировать</Button></div><pre>{curl}</pre></div>
      </section>
      <section className={styles.surface} aria-labelledby="response-title">
        <h2 id="response-title">Ответ API</h2>
        {result ? <><div className={styles.metrics}><span className={result.ok ? styles.success : styles.failure}>{result.ok ? '✓' : 'Ошибка —'} {result.status} {statusLabels[result.status] ?? (result.ok ? 'OK' : 'Ошибка')}</span><span>Время: {result.duration} ms</span><span>Размер: {result.size < 1024 ? `${result.size} B` : `${(result.size / 1024).toFixed(1)} KB`}</span></div><h3>Response Body</h3><pre className={styles.response}>{printable(result.body)}</pre></> : <p className={styles.empty}>Выберите сценарий и отправьте запрос, чтобы увидеть ответ.</p>}
      </section>
    </div>

    <section className={styles.surface} aria-labelledby="history-title"><div className={styles.row}><h2 id="history-title">История запросов</h2><Button type="button" size="s" variant="ghost" onClick={() => { setHistory([]); sessionStorage.removeItem(historyKey); }}>Очистить историю</Button></div><p className={styles.hint}>Сохраняются только маршрут и метаданные. Тело, значения параметров и заголовки не сохраняются.</p>{history.length ? <div className={styles.history}>{history.map((item, index) => <button type="button" key={`${item.at}-${index}`} onClick={() => restore(item)}><time>{new Date(item.at).toLocaleTimeString('ru-RU')}</time><strong>{item.method}</strong><span>{item.endpoint}</span><span>{item.status}</span><span>{item.duration} ms</span></button>)}</div> : <p className={styles.empty}>История пуста.</p>}</section>
    {confirmDelete ? <Modal title="Выполнить DELETE-запрос?" onClose={() => setConfirmDelete(false)}><p>Это действие может изменить данные.</p><div className={styles.actions}><Button type="button" onClick={() => setConfirmDelete(false)}>Отмена</Button><Button type="button" variant="danger" onClick={() => void execute()}>Выполнить DELETE</Button></div></Modal> : null}
  </div>;
}

function PairRows({ items, onChange, update, addLabel }: { items: Pair[]; onChange: (items: Pair[]) => void; update: (index: number, field: keyof Pair, value: string) => void; addLabel: string }) {
  return <div className={styles.pairs}>{items.map((item, index) => <div className={styles.pair} key={index}><Input aria-label={`Ключ ${index + 1}`} placeholder="Ключ" value={item.key} onChange={(event) => update(index, 'key', event.target.value)} /><Input aria-label={`Значение ${index + 1}`} placeholder="Значение" value={item.value} onChange={(event) => update(index, 'value', event.target.value)} /><Button type="button" size="s" variant="ghost" aria-label={`Удалить строку ${index + 1}`} onClick={() => onChange(items.filter((_, position) => position !== index))}>Удалить</Button></div>)}<Button type="button" size="s" variant="ghost" onClick={() => onChange([...items, { key: '', value: '' }])}>+ {addLabel}</Button></div>;
}

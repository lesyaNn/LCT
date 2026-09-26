'use client';

import Calendar from '@atomaro/icons/24/communication/Calendar';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import HistoryAction from '@atomaro/icons/24/communication/HistoryAction';
import SecurityCheck from '@atomaro/icons/24/action/SecurityCheck';
import User from '@atomaro/icons/24/communication/User';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { formatDateTimeRu, formatRelativeDateRu } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  AUDIT_PAGE_SIZES,
  EMPTY_AUDIT_FILTERS,
  auditEntityLabels,
  auditQueryKey,
  getAuditFilterOptions,
  getAuditActionMeta,
  getAuditEntityLabel,
  getAuditRoleLabel,
  formatAuditValue,
  getAuditEvents,
  type AuditEvent,
  type AuditFilters,
  type AuditListQuery,
  type AuditListResult,
  type AuditFilterOptions,
} from '@/shared/lib/audit-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { EmptyState } from '@/shared/ui/empty-state';
import { BackgroundRefreshNotice } from '@/shared/ui/background-refresh-notice';
import { ErrorState } from '@/shared/ui/error-state';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { AuditDiff } from './audit-diff';
import styles from './audit-page.module.css';


function parseQuery(searchParams: URLSearchParams): AuditListQuery {
  const list = (key: string) => (searchParams.get(key) ?? '').split(',').map((value) => value.trim()).filter(Boolean);
  const rawFrom = searchParams.get('date_from') ?? '';
  const rawTo = searchParams.get('date_to') ?? '';
  const pageSizeCandidate = Number(searchParams.get('page_size'));
  const pageSize = AUDIT_PAGE_SIZES.includes(pageSizeCandidate as (typeof AUDIT_PAGE_SIZES)[number]) ? pageSizeCandidate : AUDIT_PAGE_SIZES[0];
  return {
    filters: normalizeFilters({ dateFrom: rawFrom, dateTo: rawTo, userIds: list('user'), universityIds: list('university'), actions: list('action'), entityTypes: list('entity_type') }),
    page: Math.max(1, Number(searchParams.get('page')) || 1),
    pageSize,
  };
}

function queryString(query: AuditListQuery): string {
  const params = new URLSearchParams();
  const set = (key: string, value: string | string[]) => { if (Array.isArray(value) ? value.length : value) params.set(key, Array.isArray(value) ? value.join(',') : value); };
  set('date_from', query.filters.dateFrom);
  set('date_to', query.filters.dateTo);
  set('user', query.filters.userIds);
  set('university', query.filters.universityIds);
  set('action', query.filters.actions);
  set('entity_type', query.filters.entityTypes);
  if (query.page > 1) set('page', String(query.page));
  if (query.pageSize !== AUDIT_PAGE_SIZES[0]) set('page_size', String(query.pageSize));
  const value = params.toString();
  return value ? `?${value}` : '';
}

function EntityIcon({ type }: { type: string }) {
  const normalized = type.toLowerCase();
  if (normalized.includes('user')) return <User size={16} fill="currentColor" />;
  if (normalized.includes('document')) return <DocumentText size={16} fill="currentColor" />;
  if (normalized.includes('workflow')) return <HistoryAction size={16} fill="currentColor" />;
  if (normalized.includes('meeting')) return <Calendar size={16} fill="currentColor" />;
  return <SecurityCheck size={16} fill="currentColor" />;
}

function normalizeFilters(filters: AuditFilters): AuditFilters {
  return {
    ...filters,
    dateFrom: filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo ? filters.dateTo : filters.dateFrom,
    dateTo: filters.dateFrom && filters.dateTo && filters.dateFrom > filters.dateTo ? filters.dateFrom : filters.dateTo,
    userIds: [...new Set(filters.userIds)].sort(),
    universityIds: [...new Set(filters.universityIds)].sort(),
    actions: [...new Set(filters.actions)].sort(),
    entityTypes: [...new Set(filters.entityTypes)].sort(),
  };
}

function selectedFilterCount(filters: AuditFilters): number {
  return [filters.dateFrom, filters.dateTo, ...filters.userIds, ...filters.universityIds, ...filters.actions, ...filters.entityTypes].filter(Boolean).length;
}

function AuditFilters({ query, result, options, onPatch, onReset }: { query: AuditListQuery; result?: AuditListResult; options?: AuditFilterOptions; onPatch: (patch: Partial<AuditFilters>) => void; onReset: () => void }) {
  const capabilities = result?.capabilities;
  const entityOptions = (options?.entityTypes ?? Object.keys(auditEntityLabels)).map((id) => ({ id, name: getAuditEntityLabel(id) }));
  const actionOptions = (options?.actions ?? []).map((id) => ({ id, name: getAuditActionMeta(id).label }));
  const users = options?.users ?? [];
  const universities = options?.universities ?? [];
  const controls = () => <>
      <DateRangeField presets from={query.filters.dateFrom} to={query.filters.dateTo} disabled={!capabilities?.dateRange} onFromChange={(dateFrom) => onPatch({ dateFrom })} onToChange={(dateTo) => onPatch({ dateTo })} onRangeChange={(dateFrom, dateTo) => onPatch({ dateFrom, dateTo })} />
      <MultiSelect label="Пользователь" values={query.filters.userIds} options={users} disabled={!capabilities?.users || !options} onChange={(values) => onPatch({ userIds: values })} />
      <MultiSelect label="ВУЗ" values={query.filters.universityIds} options={universities} disabled={!capabilities?.universities || !options} onChange={(values) => onPatch({ universityIds: values })} />
      <MultiSelect label="Тип действия" values={query.filters.actions} options={actionOptions} disabled={!capabilities?.actions || !options} onChange={(values) => onPatch({ actions: values })} />
      <MultiSelect label="Тип сущности" values={query.filters.entityTypes} options={entityOptions} disabled={!capabilities?.entityTypes || !options} onChange={(values) => onPatch({ entityTypes: values })} />
    </>;

  const chips = [
    ...(query.filters.dateFrom || query.filters.dateTo ? [{ id: 'period', label: `Период: ${query.filters.dateFrom || '…'} — ${query.filters.dateTo || '…'}`, onRemove: () => onPatch({ dateFrom: '', dateTo: '' }) }] : []),
    ...([['userIds', 'Пользователь', users], ['universityIds', 'ВУЗ', universities], ['actions', 'Тип действия', actionOptions], ['entityTypes', 'Тип сущности', entityOptions]] as const).filter(([key]) => query.filters[key].length).map(([key, label, entries]) => ({ id: key, label: `${label}: ${query.filters[key].map((id) => entries.find((item) => item.id === id)?.name ?? id).join(', ')}`, onRemove: () => onPatch({ [key]: [] }) })),
  ];
  return <FilterToolbar activeFilters={chips} label="Фильтры журнала аудита" controls={controls} onReset={onReset} resetDisabled={!selectedFilterCount(query.filters)} mobileCount={selectedFilterCount(query.filters)} />;
}

function TimeCell({ value }: { value: string }) {
  if (!value) return <span>—</span>;
  return <Tooltip content={<span>{formatDateTimeRu(value)}</span>}><time dateTime={value}>{formatRelativeDateRu(value)}</time></Tooltip>;
}

function ActionBadge({ action }: { action: string }) {
  const meta = getAuditActionMeta(action);
  return <StatusBadge intent={meta.intent}>{meta.label}</StatusBadge>;
}

function EntityCell({ event }: { event: AuditEvent }) {
  return <span className={styles.entity}><span className={styles.entityIcon} aria-hidden="true"><EntityIcon type={event.entity.type} /></span><span><strong>{getAuditEntityLabel(event.entity.type)}</strong><small>{event.entity.id}</small></span></span>;
}

function DetailsModal({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  return <Modal title={`${getAuditActionMeta(event.action).label}: ${event.entity.label}`} onClose={onClose} size="l"><div className={styles.modalMeta}><span>Время</span><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time><span>Пользователь</span><strong>{event.user.name}</strong><span>Роль</span><span>{getAuditRoleLabel(event.role)}</span><span>ВУЗ</span><span>{event.university.name}</span></div><AuditDiff event={event} /></Modal>;
}

function AuditTable({ events, onOpen }: { events: AuditEvent[]; onOpen: (event: AuditEvent) => void }) {
  return <TableShell ariaLabel="Журнал действий"><div className={styles.desktopTable}><table><caption className={styles.visuallyHidden}>Полный журнал аудита</caption><thead><tr><th scope="col">Время</th><th scope="col">Пользователь</th><th scope="col">Роль</th><th scope="col">Действие</th><th scope="col">Сущность</th><th scope="col">ВУЗ</th><th scope="col">Старое значение</th><th scope="col">Новое значение</th></tr></thead><tbody>{events.map((event) => <tr key={event.id} data-testid="audit-event"><td><TimeCell value={event.occurredAt} /></td><td><span className={styles.userCell}>{event.user.name}</span></td><td>{getAuditRoleLabel(event.role)}</td><td><ActionBadge action={event.action} /></td><td><EntityCell event={event} /></td><td>{event.university.name}</td><td><span className={styles.valuePreview}>{formatAuditValue(event.oldValues)}</span></td><td><button className={styles.valueButton} type="button" onClick={() => onOpen(event)}><span className={styles.valuePreview}>{formatAuditValue(event.newValues)}</span><span className={styles.detailsLink}>Подробнее</span></button></td></tr>)}</tbody></table></div><div className={styles.mobileList}>{events.map((event) => <article className={styles.mobileCard} key={event.id}><div className={styles.mobileTop}><TimeCell value={event.occurredAt} /><ActionBadge action={event.action} /></div><dl><div><dt>Пользователь</dt><dd>{event.user.name}</dd></div><div><dt>Роль</dt><dd>{getAuditRoleLabel(event.role)}</dd></div><div><dt>Сущность</dt><dd><EntityCell event={event} /></dd></div><div><dt>ВУЗ</dt><dd>{event.university.name}</dd></div><div><dt>Было</dt><dd>{formatAuditValue(event.oldValues)}</dd></div><div><dt>Стало</dt><dd>{formatAuditValue(event.newValues)}</dd></div></dl><Button variant="secondary" size="s" type="button" onClick={() => onOpen(event)}>Открыть детали</Button></article>)}</div></TableShell>;
}

function Pagination({ result, pageSize, onPage, onPageSize }: { result: AuditListResult; pageSize: number; onPage: (page: number) => void; onPageSize: (pageSize: number) => void }) {
  if (!result.capabilities.pagination) return null;
  const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
  return <div className={styles.pagination}><span>Страница {result.page} из {totalPages}</span><label>Показывать <select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>{AUDIT_PAGE_SIZES.map((size) => <option value={size} key={size}>{size}</option>)}</select></label><Button variant="secondary" size="s" type="button" disabled={result.page <= 1} onClick={() => onPage(result.page - 1)}>Назад</Button><Button variant="secondary" size="s" type="button" disabled={result.page >= totalPages} onClick={() => onPage(result.page + 1)}>Вперёд</Button></div>;
}

export function AuditPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState<AuditListQuery>(() => parseQuery(new URLSearchParams(searchParams.toString())));
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const auditQuery = useQuery({ queryKey: auditQueryKey(query), queryFn: () => getAuditEvents(query), placeholderData: keepPreviousData, staleTime: 30_000 });
  const optionsQuery = useQuery({ queryKey: queryKeys.audit.filterOptions, queryFn: getAuditFilterOptions, staleTime: 5 * 60_000 });
  const filtered = selectedFilterCount(query.filters) > 0;
  const normalizedError = auditQuery.error ? normalizeApiError(auditQuery.error, { fallbackMessage: 'Не удалось загрузить журнал аудита.' }) : null;
  const filterHint = optionsQuery.isPending ? 'Загрузка доступных фильтров…' : null;

  useEffect(() => {
    router.replace(`${pathname}${queryString(query)}`, { scroll: false });
  }, [pathname, query, router]);

  const patchFilters = (patch: Partial<AuditFilters>) => setQuery((current) => ({ ...current, filters: normalizeFilters({ ...current.filters, ...patch }), page: 1 }));
  const resetFilters = () => setQuery((current) => ({ ...current, filters: EMPTY_AUDIT_FILTERS, page: 1 }));
  const retry = () => void auditQuery.refetch();

  return <div className={styles.page}>
    <AuditFilters query={query} result={auditQuery.data} options={optionsQuery.data} onPatch={patchFilters} onReset={resetFilters} />
    {filterHint ? <p className={styles.loadingHint}>{filterHint}</p> : null}
    {optionsQuery.isError ? <ErrorState title="Не удалось загрузить фильтры журнала" description="Журнал доступен; повторите загрузку фильтров." onRetry={() => void optionsQuery.refetch()} /> : null}
    <div className={styles.refreshStatus} aria-live="polite">{auditQuery.isFetching && auditQuery.data ? <span className={styles.loadingHint} role="status">Обновляем журнал…</span> : null}{auditQuery.isError && auditQuery.data ? <BackgroundRefreshNotice onRetry={retry} /> : null}</div>
    {auditQuery.isPending ? <TableSkeleton rows={6} columns={8} label="Загрузка журнала аудита" /> : !auditQuery.data ? <ErrorState title={normalizedError?.message ?? 'Не удалось загрузить журнал аудита'} description="Повторите попытку или обратитесь к администратору." onRetry={retry} /> : auditQuery.data.items.length ? <AuditTable events={auditQuery.data.items} onOpen={setSelectedEvent} /> : <EmptyState icon={<SecurityCheck size={24} fill="currentColor" />} title={filtered ? 'По заданным фильтрам события не найдены' : 'Событий пока нет'} description={filtered ? 'Измените условия поиска или сбросьте фильтры.' : 'Когда появятся записи, они будут отображены в этом журнале.'} primaryAction={filtered ? { label: 'Сбросить фильтры', onClick: resetFilters, variant: 'secondary' } : undefined} />}
    {auditQuery.data ? <Pagination result={auditQuery.data} pageSize={query.pageSize} onPage={(page) => setQuery((current) => ({ ...current, page }))} onPageSize={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))} /> : null}
    {selectedEvent ? <DetailsModal event={selectedEvent} onClose={() => setSelectedEvent(null)} /> : null}
  </div>;
}

'use client';

import HistoryAction from '@atomaro/icons/24/communication/HistoryAction';
import SecurityCheck from '@atomaro/icons/24/action/SecurityCheck';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { formatDateTimeRu, formatRelativeDateRu } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  AUDIT_PAGE_SIZES,
  EMPTY_AUDIT_FILTERS,
  auditQueryKey,
  getAuditFilterOptions,
  getAuditEvents,
  type AuditEvent,
  type AuditFilters,
  type AuditListQuery,
  type AuditListResult,
  type AuditFilterOptions,
} from '@/shared/lib/audit-repository';
import {
  AUDIT_ACTION_GROUP_OPTIONS,
  AUDIT_SECTION_OPTIONS,
  getAuditRoleLabel,
  summarizeAuditEvent,
  universityDisplayName,
} from '@/shared/lib/audit-human';
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

const ACTION_GROUP_TO_ACTIONS = new Map(AUDIT_ACTION_GROUP_OPTIONS.map((group) => [group.id, group.actions]));
const SECTION_TO_TYPES = new Map(AUDIT_SECTION_OPTIONS.map((section) => [section.id, section.entityTypes]));

function expandActionGroups(groupIds: string[]): string[] {
  return [...new Set(groupIds.flatMap((id) => ACTION_GROUP_TO_ACTIONS.get(id) ?? []))].sort();
}

function expandSections(sectionIds: string[]): string[] {
  return [...new Set(sectionIds.flatMap((id) => SECTION_TO_TYPES.get(id) ?? []))].sort();
}

function parseQuery(searchParams: URLSearchParams): AuditListQuery {
  const list = (key: string) => (searchParams.get(key) ?? '').split(',').map((value) => value.trim()).filter(Boolean);
  const rawFrom = searchParams.get('date_from') ?? '';
  const rawTo = searchParams.get('date_to') ?? '';
  const pageSizeCandidate = Number(searchParams.get('page_size'));
  const pageSize = AUDIT_PAGE_SIZES.includes(pageSizeCandidate as (typeof AUDIT_PAGE_SIZES)[number]) ? pageSizeCandidate : AUDIT_PAGE_SIZES[0];
  return {
    filters: normalizeFilters({
      dateFrom: rawFrom,
      dateTo: rawTo,
      userIds: list('user'),
      universityIds: list('university'),
      actions: list('action'),
      entityTypes: list('entity_type'),
      sections: list('section'),
      search: searchParams.get('search') ?? '',
    }),
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
  set('section', query.filters.sections);
  if (query.filters.search.trim()) params.set('search', query.filters.search.trim());
  if (query.page > 1) set('page', String(query.page));
  if (query.pageSize !== AUDIT_PAGE_SIZES[0]) set('page_size', String(query.pageSize));
  const value = params.toString();
  return value ? `?${value}` : '';
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
    sections: [...new Set(filters.sections)].sort(),
    search: filters.search.trim().slice(0, 200),
  };
}

function selectedFilterCount(filters: AuditFilters): number {
  return [
    filters.dateFrom, filters.dateTo,
    ...filters.userIds, ...filters.universityIds,
    ...filters.actions, ...filters.entityTypes, ...filters.sections,
    filters.search.trim(),
  ].filter(Boolean).length;
}

/** Effective API query: friendly groups expanded to backend values. */
function toApiQuery(query: AuditListQuery): AuditListQuery {
  return {
    ...query,
    filters: {
      ...query.filters,
      actions: expandActionGroups(query.filters.actions),
      entityTypes: [...new Set([...query.filters.entityTypes, ...expandSections(query.filters.sections)])].sort(),
    },
  };
}

function AuditFilters({ query, result, options, onPatch, onReset }: { query: AuditListQuery; result?: AuditListResult; options?: AuditFilterOptions; onPatch: (patch: Partial<AuditFilters>) => void; onReset: () => void }) {
  const capabilities = result?.capabilities;
  const actionOptions = AUDIT_ACTION_GROUP_OPTIONS.map(({ id, label }) => ({ id, name: label }));
  const sectionOptions = AUDIT_SECTION_OPTIONS.map(({ id, label }) => ({ id, name: label }));
  const users = options?.users ?? [];
  const universities = options?.universities ?? [];
  const controls = () => <>
      <label className={styles.searchField}><span>Поиск</span><input
        type="search"
        value={query.filters.search}
        maxLength={200}
        placeholder="Имя, ВУЗ, объект…"
        aria-label="Поиск по журналу"
        onChange={(event) => onPatch({ search: event.target.value })}
      /></label>
      <MultiSelect labelPlacement="outside" label="Сотрудник" values={query.filters.userIds} options={users} disabled={!capabilities?.users || !options} onChange={(values) => onPatch({ userIds: values })} />
      <MultiSelect labelPlacement="outside" label="ВУЗ" values={query.filters.universityIds} options={universities} disabled={!capabilities?.universities || !options} onChange={(values) => onPatch({ universityIds: values })} />
      <MultiSelect labelPlacement="outside" label="Что произошло" values={query.filters.actions} options={actionOptions} disabled={!capabilities?.actions} onChange={(values) => onPatch({ actions: values })} />
      <MultiSelect labelPlacement="outside" label="Раздел" values={query.filters.sections} options={sectionOptions} disabled={!capabilities?.entityTypes} onChange={(values) => onPatch({ sections: values })} />
    </>;

  const chips = [
    ...(query.filters.search.trim() ? [{ id: 'search', label: `Поиск: ${query.filters.search.trim()}`, onRemove: () => onPatch({ search: '' }) }] : []),
    ...(query.filters.dateFrom || query.filters.dateTo ? [{ id: 'period', label: `Период: ${query.filters.dateFrom || '…'} — ${query.filters.dateTo || '…'}`, onRemove: () => onPatch({ dateFrom: '', dateTo: '' }) }] : []),
    ...([['userIds', 'Сотрудник', users], ['universityIds', 'ВУЗ', universities], ['actions', 'Что произошло', actionOptions], ['sections', 'Раздел', sectionOptions]] as const).filter(([key]) => query.filters[key].length).map(([key, label, entries]) => ({ id: key, label: `${label}: ${query.filters[key].map((id) => entries.find((item) => item.id === id)?.name ?? id).join(', ')}`, onRemove: () => onPatch({ [key]: [] }) })),
  ];
  return <FilterToolbar activeFilters={chips} label="Фильтры истории изменений" controls={controls} periodControls={<DateRangeField presets from={query.filters.dateFrom} to={query.filters.dateTo} disabled={!capabilities?.dateRange} onFromChange={(dateFrom) => onPatch({ dateFrom })} onToChange={(dateTo) => onPatch({ dateTo })} onRangeChange={(dateFrom, dateTo) => onPatch({ dateFrom, dateTo })} />} collapsible onReset={onReset} resetDisabled={!selectedFilterCount(query.filters)} mobileCount={selectedFilterCount(query.filters)} />;
}

function TimeCell({ value }: { value: string }) {
  if (!value) return <span>—</span>;
  return <Tooltip content={<span>{formatDateTimeRu(value)}</span>}><time dateTime={value}>{formatRelativeDateRu(value)}</time></Tooltip>;
}

function ActorCell({ event }: { event: AuditEvent }) {
  const summary = summarizeAuditEvent(event);
  return <span className={styles.actor}><strong>{summary.actorName}</strong><small>{getAuditRoleLabel(summary.actorRole ?? event.role)}</small></span>;
}

function EventCell({ event }: { event: AuditEvent }) {
  const summary = summarizeAuditEvent(event);
  return <span className={styles.event}><strong>{summary.title}</strong><small>{summary.section}</small></span>;
}

function UniversityCell({ event }: { event: AuditEvent }) {
  const summary = summarizeAuditEvent(event);
  const display = universityDisplayName(event);
  if (display) return <span>{display}</span>;
  return <span className={styles.muted}>{summary.section}</span>;
}

function ChangePreview({ event, onOpen }: { event: AuditEvent; onOpen: (event: AuditEvent) => void }) {
  const summary = summarizeAuditEvent(event);
  if (!summary.changes.length) return <span className={styles.muted}>—</span>;
  const visible = summary.changes.slice(0, 2);
  const rest = summary.changes.length - visible.length;
  return <button className={styles.valueButton} type="button" onClick={() => onOpen(event)}>
    <span className={styles.changeList}>{visible.map((change) => <span key={change.field} className={styles.changeLine}><span className={styles.changeLabel}>{change.label}:</span> <span>{change.old} → {change.next}</span></span>)}</span>
    {rest > 0 ? <span className={styles.detailsLink}>Изменено полей: {summary.changes.length} · Подробнее</span> : <span className={styles.detailsLink}>Подробнее</span>}
  </button>;
}

function DetailsModal({ event, onClose }: { event: AuditEvent; onClose: () => void }) {
  const summary = summarizeAuditEvent(event);
  const university = universityDisplayName(event) || summary.section;
  return <Modal title={summary.title} onClose={onClose} size="l">
    <div className={styles.modalMeta}>
      <span>Кто</span><strong>{summary.actorName}</strong>
      <span>Роль</span><span>{getAuditRoleLabel(summary.actorRole ?? event.role)}</span>
      <span>Когда</span><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time>
      <span>ВУЗ</span><span>{university}</span>
      <span>Раздел</span><span>{summary.section}</span>
    </div>
    <AuditDiff event={event} />
  </Modal>;
}

function SectionBadge({ section }: { section: string }) {
  return <StatusBadge intent="neutral">{section}</StatusBadge>;
}

function AuditTable({ events, onOpen }: { events: AuditEvent[]; onOpen: (event: AuditEvent) => void }) {
  return <TableShell ariaLabel="История изменений"><div className={styles.desktopTable}><table><caption className={styles.visuallyHidden}>История изменений</caption><thead><tr><th scope="col">Время</th><th scope="col">Кто</th><th scope="col">Что произошло</th><th scope="col">ВУЗ / Раздел</th><th scope="col">Изменение</th></tr></thead><tbody>{events.map((event) => {
    return <tr key={event.id} data-testid="audit-event"><td><TimeCell value={event.occurredAt} /></td><td><ActorCell event={event} /></td><td><EventCell event={event} /></td><td><UniversityCell event={event} /></td><td><ChangePreview event={event} onOpen={onOpen} /></td></tr>;
  })}</tbody></table></div><div className={styles.mobileList}>{events.map((event) => {
    const summary = summarizeAuditEvent(event);
    const university = universityDisplayName(event) || summary.section;
    return <article className={styles.mobileCard} key={event.id}><div className={styles.mobileTop}><TimeCell value={event.occurredAt} /><SectionBadge section={summary.section} /></div><strong className={styles.mobileTitle}>{summary.title}</strong><dl><div><dt>Кто</dt><dd>{summary.actorName} · {getAuditRoleLabel(summary.actorRole ?? event.role)}</dd></div><div><dt>ВУЗ</dt><dd>{university}</dd></div>{summary.changes.slice(0, 3).map((change) => <div key={change.field}><dt>{change.label}</dt><dd>{change.old} → {change.next}</dd></div>)}</dl><Button variant="secondary" size="s" type="button" onClick={() => onOpen(event)}>{summary.changes.length > 3 ? `Подробнее (${summary.changes.length} полей)` : 'Открыть детали'}</Button></article>;
  })}</div></TableShell>;
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
  const apiQuery = toApiQuery(query);
  const auditQuery = useQuery({ queryKey: auditQueryKey(apiQuery), queryFn: () => getAuditEvents(apiQuery), placeholderData: keepPreviousData, staleTime: 30_000 });
  const optionsQuery = useQuery({ queryKey: queryKeys.audit.filterOptions, queryFn: getAuditFilterOptions, staleTime: 5 * 60_000 });
  const filtered = selectedFilterCount(query.filters) > 0;
  const normalizedError = auditQuery.error ? normalizeApiError(auditQuery.error, { fallbackMessage: 'Не удалось загрузить историю изменений.' }) : null;
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
    {auditQuery.isPending ? <TableSkeleton rows={6} columns={5} label="Загрузка истории изменений" /> : !auditQuery.data ? <ErrorState title={normalizedError?.message ?? 'Не удалось загрузить историю изменений'} description="Повторите попытку или обратитесь к администратору." onRetry={retry} /> : auditQuery.data.items.length ? <AuditTable events={auditQuery.data.items} onOpen={setSelectedEvent} /> : <EmptyState icon={<SecurityCheck size={24} fill="currentColor" />} title={filtered ? 'По заданным фильтрам события не найдены' : 'Событий пока нет'} description={filtered ? 'Измените условия поиска или сбросьте фильтры.' : 'Когда появятся записи, они будут отображены в этом журнале.'} primaryAction={filtered ? { label: 'Сбросить фильтры', onClick: resetFilters, variant: 'secondary' } : undefined} />}
    {auditQuery.data ? <Pagination result={auditQuery.data} pageSize={query.pageSize} onPage={(page) => setQuery((current) => ({ ...current, page }))} onPageSize={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))} /> : null}
    {selectedEvent ? <DetailsModal event={selectedEvent} onClose={() => setSelectedEvent(null)} /> : null}
  </div>;
}

export function AuditHistoryIcon() {
  return <HistoryAction size={16} fill="currentColor" />;
}

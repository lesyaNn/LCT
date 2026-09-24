'use client';

import Calendar from '@atomaro/icons/24/communication/Calendar';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import HistoryAction from '@atomaro/icons/24/communication/HistoryAction';
import SecurityCheck from '@atomaro/icons/24/action/SecurityCheck';
import User from '@atomaro/icons/24/communication/User';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { formatDateTimeRu, formatRelativeDateRu } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import {
  AUDIT_PAGE_SIZES,
  EMPTY_AUDIT_FILTERS,
  auditEntityLabels,
  auditQueryKey,
  getAuditActionMeta,
  getAuditEntityLabel,
  getAuditRoleLabel,
  formatAuditValue,
  getAuditEvents,
  type AuditEvent,
  type AuditFilters,
  type AuditListQuery,
  type AuditListResult,
} from '@/shared/lib/audit-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { Modal } from '@/shared/ui/rtk/modal';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { TableSkeleton } from '@/shared/ui/skeleton';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { AuditDiff } from './audit-diff';
import styles from './audit-page.module.css';

const ACTION_OPTIONS = ['CREATE', 'UPDATE', 'DELETE', 'WORKFLOW_TRANSITION'];
const ENTITY_OPTIONS = Object.keys(auditEntityLabels);

function parseQuery(searchParams: URLSearchParams): AuditListQuery {
  const list = (key: string) => (searchParams.get(key) ?? '').split(',').map((value) => value.trim()).filter(Boolean);
  const rawFrom = searchParams.get('date_from') ?? '';
  const rawTo = searchParams.get('date_to') ?? '';
  const pageSizeCandidate = Number(searchParams.get('page_size'));
  const pageSize = AUDIT_PAGE_SIZES.includes(pageSizeCandidate as (typeof AUDIT_PAGE_SIZES)[number]) ? pageSizeCandidate : AUDIT_PAGE_SIZES[0];
  return {
    filters: normalizeFilters({ dateFrom: rawFrom, dateTo: rawTo, userIds: list('user'), universityIds: list('university'), actions: list('action'), entityTypes: list('entity_type').slice(-1) }),
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

function AuditFilters({ query, result, onPatch, onReset, open, onClose }: { query: AuditListQuery; result?: AuditListResult; onPatch: (patch: Partial<AuditFilters>) => void; onReset: () => void; open: boolean; onClose: () => void }) {
  const capabilities = result?.capabilities;
  const entityOptions = ENTITY_OPTIONS.map((id) => ({ id, name: getAuditEntityLabel(id) }));
  const actionOptions = ACTION_OPTIONS.map((id) => ({ id, name: getAuditActionMeta(id).label }));
  const users = result?.filterOptions.users ?? [];
  const universities = result?.filterOptions.universities ?? [];
  const content = (
    <div className={styles.filterGrid}>
      <div className={styles.dateRange}>
        <span className={styles.filterLabel}>Период</span>
        <div className={styles.dateInputs}>
          <label><span>От</span><input type="date" value={query.filters.dateFrom} disabled={!capabilities?.dateRange} max={query.filters.dateTo || undefined} onChange={(event) => onPatch({ dateFrom: event.target.value })} /></label>
          <label><span>До</span><input type="date" value={query.filters.dateTo} disabled={!capabilities?.dateRange} min={query.filters.dateFrom || undefined} onChange={(event) => onPatch({ dateTo: event.target.value })} /></label>
        </div>
      </div>
      <MultiSelect label="Пользователь" values={query.filters.userIds} options={users} disabled={!capabilities?.users} hint="Опции появятся в P5-05-03 API." onChange={(values) => onPatch({ userIds: values })} />
      <MultiSelect label="ВУЗ" values={query.filters.universityIds} options={universities} disabled={!capabilities?.universities} hint="Опции появятся в P5-05-03 API." onChange={(values) => onPatch({ universityIds: values })} />
      <MultiSelect label="Тип действия" values={query.filters.actions} options={actionOptions} disabled={!capabilities?.actions} hint="Фильтр не поддержан текущим API." onChange={(values) => onPatch({ actions: values })} />
      <MultiSelect label="Тип сущности" values={query.filters.entityTypes} options={entityOptions} disabled={!capabilities?.entityTypes} hint="Текущий API поддерживает один тип за запрос." onChange={(values) => onPatch({ entityTypes: values.slice(-1) })} />
      <Button variant="ghost" size="s" type="button" disabled={!selectedFilterCount(query.filters)} onClick={onReset}>Сбросить фильтры</Button>
    </div>
  );

  return (
    <>
      <div className={styles.desktopFilters} aria-label="Фильтры журнала аудита">{content}</div>
      {open ? <Drawer title="Фильтры" onClose={onClose}><div className={styles.drawerContent}>{content}</div></Drawer> : null}
    </>
  );
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
  if (!result.capabilities.pagination) return <p className={styles.apiNotice}>Текущий backend-контракт возвращает массив до 200 записей без server pagination. Полная фильтрация и страницы 20/50/100 подключатся после P5-05-03 API.</p>;
  const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
  return <div className={styles.pagination}><span>Страница {result.page} из {totalPages}</span><label>Показывать <select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>{AUDIT_PAGE_SIZES.map((size) => <option value={size} key={size}>{size}</option>)}</select></label><Button variant="secondary" size="s" type="button" disabled={result.page <= 1} onClick={() => onPage(result.page - 1)}>Назад</Button><Button variant="secondary" size="s" type="button" disabled={result.page >= totalPages} onClick={() => onPage(result.page + 1)}>Вперёд</Button></div>;
}

export function AuditPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState<AuditListQuery>(() => parseQuery(new URLSearchParams(searchParams.toString())));
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);
  const auditQuery = useQuery({ queryKey: auditQueryKey(query), queryFn: () => getAuditEvents(query), placeholderData: keepPreviousData, staleTime: 30_000 });
  const filtered = selectedFilterCount(query.filters) > 0;
  const normalizedError = auditQuery.error ? normalizeApiError(auditQuery.error, { fallbackMessage: 'Не удалось загрузить журнал аудита.' }) : null;
  const optionsReady = Boolean(auditQuery.data);
  const filterHint = useMemo(() => optionsReady ? null : 'Загрузка доступных фильтров…', [optionsReady]);

  useEffect(() => {
    router.replace(`${pathname}${queryString(query)}`, { scroll: false });
  }, [pathname, query, router]);

  const patchFilters = (patch: Partial<AuditFilters>) => setQuery((current) => ({ ...current, filters: normalizeFilters({ ...current.filters, ...patch }), page: 1 }));
  const resetFilters = () => setQuery((current) => ({ ...current, filters: EMPTY_AUDIT_FILTERS, page: 1 }));
  const retry = () => void auditQuery.refetch();

  return <div className={styles.page}>
    <div className={styles.toolbar}><p className={styles.eyebrow}>Только просмотр</p><Button className={styles.mobileFilterButton} variant="secondary" size="s" type="button" onClick={() => setMobileFiltersOpen(true)}>Фильтры{filtered ? ` (${selectedFilterCount(query.filters)})` : ''}</Button></div>
    <AuditFilters query={query} result={auditQuery.data} onPatch={patchFilters} onReset={resetFilters} open={mobileFiltersOpen} onClose={() => setMobileFiltersOpen(false)} />
    {filterHint ? <p className={styles.loadingHint}>{filterHint}</p> : null}
    {auditQuery.isPending ? <TableSkeleton rows={6} columns={8} label="Загрузка журнала аудита" /> : auditQuery.isError || !auditQuery.data ? <ErrorState title={normalizedError?.message ?? 'Не удалось загрузить журнал аудита'} description="Повторите попытку или обратитесь к администратору." onRetry={retry} /> : auditQuery.data.items.length ? <AuditTable events={auditQuery.data.items} onOpen={setSelectedEvent} /> : <EmptyState icon={<SecurityCheck size={24} fill="currentColor" />} title={filtered ? 'По заданным фильтрам события не найдены' : 'Событий пока нет'} description={filtered ? 'Измените условия поиска или сбросьте фильтры.' : 'Когда появятся записи, они будут отображены в этом журнале.'} primaryAction={filtered ? { label: 'Сбросить фильтры', onClick: resetFilters, variant: 'secondary' } : undefined} />}
    {auditQuery.data ? <Pagination result={auditQuery.data} pageSize={query.pageSize} onPage={(page) => setQuery((current) => ({ ...current, page }))} onPageSize={(pageSize) => setQuery((current) => ({ ...current, page: 1, pageSize }))} /> : null}
    {selectedEvent ? <DetailsModal event={selectedEvent} onClose={() => setSelectedEvent(null)} /> : null}
  </div>;
}

'use client';

import AuditIcon from '@atomaro/icons/24/action/SecurityCheck';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Edit from '@atomaro/icons/24/editor/Edit';
import HistoryAction from '@atomaro/icons/24/communication/HistoryAction';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { historyEventTypeIntent, historyEventTypeLabels } from '@/shared/lib/status-semantics';
import { getUniversityHistory, getUniversityHistoryFilterOptions, universityHistoryQueryKey, type UniversityHistoryEvent, type UniversityHistoryEventType, type UniversityHistoryFilters } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import styles from './university-history.module.css';

const eventTypes: Array<UniversityHistoryEventType | 'all'> = ['all', 'workflow', 'document', 'meeting', 'note', 'audit'];
const eventTypeOptions: Record<UniversityHistoryEventType | 'all', string> = { all: 'Все события', ...historyEventTypeLabels };

function EventTypeIcon({ type }: { type: UniversityHistoryEventType }) {
  if (type === 'workflow') return <HistoryAction size={16} fill="currentColor" />;
  if (type === 'document') return <DocumentText size={16} fill="currentColor" />;
  if (type === 'meeting') return <Calendar size={16} fill="currentColor" />;
  if (type === 'audit') return <AuditIcon size={16} fill="currentColor" />;
  return <Edit size={16} fill="currentColor" />;
}

function EventType({ type }: { type: UniversityHistoryEventType }) {
  return <span className={styles.eventType}><EventTypeIcon type={type} /><StatusBadge intent={historyEventTypeIntent[type]}>{historyEventTypeLabels[type]}</StatusBadge></span>;
}

function displayValue(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(value);
}

function AuditDiff({ event }: { event: UniversityHistoryEvent }) {
  const keys = [...new Set([...Object.keys(event.oldValues ?? {}), ...Object.keys(event.newValues ?? {})])];
  if (!keys.length) return null;
  return <div className={styles.auditDetails}><table><thead><tr><th>Поле</th><th>Было</th><th>Стало</th></tr></thead><tbody>{keys.map((key) => <tr key={key}><th scope="row">{key}</th><td>{displayValue(event.oldValues?.[key])}</td><td>{displayValue(event.newValues?.[key])}</td></tr>)}</tbody></table>{event.ip || event.userAgent ? <p>{event.ip ? `IP: ${event.ip}` : ''}{event.ip && event.userAgent ? ' · ' : ''}{event.userAgent ? `User-Agent: ${event.userAgent}` : ''}</p> : null}</div>;
}

function EventDetails({ event }: { event: UniversityHistoryEvent }) {
  return <details className={styles.details}><summary>{event.details}</summary>{event.type === 'audit' ? <AuditDiff event={event} /> : <p>{event.details}</p>}</details>;
}

function HistoryFilters({ filters, options, onChange, onReset }: { filters: UniversityHistoryFilters; options: ReturnType<typeof getUniversityHistoryFilterOptions>; onChange: (patch: Partial<UniversityHistoryFilters>) => void; onReset: () => void }) {
  return <div className={styles.filters} aria-label="Фильтры истории"><label><span>Тип события</span><select value={filters.type} onChange={(event) => onChange({ type: event.target.value as UniversityHistoryFilters['type'] })}>{eventTypes.map((type) => <option value={type} key={type}>{eventTypeOptions[type]}</option>)}</select></label><label><span>С даты</span><input type="date" value={filters.dateFrom} onChange={(event) => onChange({ dateFrom: event.target.value })} /></label><label><span>По дату</span><input type="date" value={filters.dateTo} onChange={(event) => onChange({ dateTo: event.target.value })} /></label><label><span>Пользователь</span><select value={filters.userId} onChange={(event) => onChange({ userId: event.target.value })}><option value="">Все пользователи</option>{options.users.map((user) => <option value={user.id} key={user.id}>{user.name}</option>)}</select></label><label><span>Сущность</span><select value={filters.entityId} onChange={(event) => onChange({ entityId: event.target.value })}><option value="">Все сущности</option>{options.entities.map((entity) => <option value={entity.id} key={entity.id}>{entity.label}</option>)}</select></label><Button variant="ghost" size="s" type="button" onClick={onReset}>Сбросить</Button></div>;
}

function HistorySkeleton() {
  return <TableShell><div className={styles.skeleton} aria-live="polite" aria-busy="true">{Array.from({ length: 6 }, (_, index) => <span key={index} />)}</div></TableShell>;
}

function HistoryEmpty({ filtered, onReset }: { filtered: boolean; onReset: () => void }) {
  return <div className={styles.empty} role="status"><HistoryAction size={22} fill="currentColor" /><p>{filtered ? 'По заданным фильтрам события не найдены' : 'Событий пока нет'}</p>{filtered ? <Button variant="secondary" size="s" type="button" onClick={onReset}>Сбросить фильтры</Button> : null}</div>;
}

function HistoryTable({ events }: { events: UniversityHistoryEvent[] }) {
  return <TableShell><div className={styles.desktopTable}><table><caption className={styles.visuallyHidden}>История событий университета</caption><thead><tr><th scope="col">Время</th><th scope="col">Тип</th><th scope="col">Пользователь</th><th scope="col">Действие</th><th scope="col">Детали</th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time></td><td><EventType type={event.type} /></td><td>{event.user.name}</td><td><strong>{event.action}</strong></td><td><EventDetails event={event} /></td></tr>)}</tbody></table></div><div className={styles.mobileList}>{events.map((event) => <article className={styles.mobileEvent} key={event.id}><div className={styles.mobileEventTop}><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time><EventType type={event.type} /></div><strong>{event.action}</strong><span>{event.user.name}</span><EventDetails event={event} /></article>)}</div></TableShell>;
}

export function UniversityHistory({ id }: { id: string }) {
  const [filters, setFilters] = useState<UniversityHistoryFilters>({ type: 'all', dateFrom: '', dateTo: '', userId: '', entityId: '' });
  const options = useMemo(() => getUniversityHistoryFilterOptions(id), [id]);
  const query = useQuery({ queryKey: universityHistoryQueryKey(id, filters), queryFn: () => getUniversityHistory(id, filters), staleTime: 30_000 });
  const filtered = Boolean(filters.type !== 'all' || filters.dateFrom || filters.dateTo || filters.userId || filters.entityId);
  const onChange = (patch: Partial<UniversityHistoryFilters>) => setFilters((current) => {
    const next = { ...current, ...patch };
    if (next.dateFrom && next.dateTo && next.dateFrom > next.dateTo) [next.dateFrom, next.dateTo] = [next.dateTo, next.dateFrom];
    return next;
  });
  const resetFilters = () => setFilters({ type: 'all', dateFrom: '', dateTo: '', userId: '', entityId: '' });

  return <div className={styles.page}><HistoryFilters filters={filters} options={options} onChange={onChange} onReset={resetFilters} />{query.isPending ? <HistorySkeleton /> : query.isError || !query.data ? <RouteErrorState onRetry={() => void query.refetch()} /> : query.data.length ? <HistoryTable events={query.data} /> : <HistoryEmpty filtered={filtered} onReset={resetFilters} />}</div>;
}

'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type Table,
  type Updater,
} from '@tanstack/react-table';
import Attention from '@atomaro/icons/24/action/Attention';
import Search from '@atomaro/icons/24/action/Search';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import ChevronSort from '@atomaro/icons/24/navigation/ChevronSort';
import SortDown from '@atomaro/icons/24/editor/SortDown';
import SortUp from '@atomaro/icons/24/editor/SortUp';
import { Button } from '@/shared/ui/rtk/button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import {
  getHealthStatus,
  healthStatusMeta,
  type HealthStatus,
} from '@/shared/lib/health-score';
import {
  getUniversities,
  programStatusLabels,
  universityFilterOptions,
  universitiesQueryKey,
  type UniversityListItem,
  type UniversityListQuery,
  type UniversitySortColumn,
} from '@/shared/lib/universities-repository';
import styles from './universities-list.module.css';

const DEFAULT_PAGE_SIZE = 8;
const PAGE_SIZE_OPTIONS = [8, 12, 20];
const HEALTH_STATUS_OPTIONS: Array<{ value: HealthStatus; label: string }> = [
  { value: 'green', label: healthStatusMeta.green.label },
  { value: 'yellow', label: healthStatusMeta.yellow.label },
  { value: 'red', label: healthStatusMeta.red.label },
];

type SearchParamsLike = {
  get: (name: string) => string | null;
  toString: () => string;
};

type UniversityUrlState = UniversityListQuery;

const SORT_COLUMNS = new Set<UniversitySortColumn>(['name', 'responsible', 'programs', 'stage', 'health_score', 'last_interaction']);
const HEALTH_STATUSES = new Set<HealthStatus>(['green', 'yellow', 'red']);

function parsePositiveInteger(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseUrlState(searchParams: SearchParamsLike): UniversityUrlState {
  const sortValue = searchParams.get('sort');
  const healthStatuses = (searchParams.get('health_status') ?? '')
    .split(',')
    .filter((value): value is HealthStatus => HEALTH_STATUSES.has(value as HealthStatus));
  const pageSizeValue = parsePositiveInteger(searchParams.get('page_size'), DEFAULT_PAGE_SIZE);

  return {
    search: searchParams.get('search') ?? '',
    city: searchParams.get('city') ?? '',
    responsible: searchParams.get('responsible') ?? '',
    healthStatuses,
    stage: searchParams.get('stage') ?? '',
    sort: SORT_COLUMNS.has(sortValue as UniversitySortColumn) ? sortValue as UniversitySortColumn : null,
    order: searchParams.get('order') === 'desc' ? 'desc' : 'asc',
    page: parsePositiveInteger(searchParams.get('page'), 1),
    pageSize: PAGE_SIZE_OPTIONS.includes(pageSizeValue) ? pageSizeValue : DEFAULT_PAGE_SIZE,
  };
}

function updateSearchParams(
  current: SearchParamsLike,
  patch: Record<string, string | number | string[] | null>,
): string {
  const next = new URLSearchParams(current.toString());

  Object.entries(patch).forEach(([key, value]) => {
    if (value === null || value === '' || (Array.isArray(value) && value.length === 0)) {
      next.delete(key);
      return;
    }
    next.set(key, Array.isArray(value) ? value.join(',') : String(value));
  });

  const query = next.toString();
  return query ? `?${query}` : '';
}

function formatRelativeTime(isoDate: string): string {
  const differenceSeconds = Math.round((new Date(isoDate).getTime() - Date.now()) / 1000);
  const absoluteSeconds = Math.abs(differenceSeconds);
  const unit = absoluteSeconds >= 86_400 ? 'day' : absoluteSeconds >= 3_600 ? 'hour' : 'minute';
  const divisor = unit === 'day' ? 86_400 : unit === 'hour' ? 3_600 : 60;
  const value = Math.round(differenceSeconds / divisor);
  return new Intl.RelativeTimeFormat('ru-RU', { numeric: 'always' }).format(value, unit);
}

function formatFullDate(isoDate: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(isoDate));
}

function StatusBadge({ status }: { status: HealthStatus }) {
  const meta = healthStatusMeta[status];
  return <span className={`${styles.statusBadge} ${styles[`status-${status}`]}`}><span aria-hidden="true" />{meta.label}</span>;
}

function StageBadge({ item }: { item: UniversityListItem }) {
  return <span className={`${styles.stageBadge} ${styles[`stage-${item.currentStage.tone}`]}`}>{item.currentStage.name}</span>;
}

function ProgramsCell({ item }: { item: UniversityListItem }) {
  const statuses = Object.entries(item.programStatusCounts).filter(([, count]) => count);

  return (
    <div className={styles.programsCell}>
      <strong>{item.programsCount}</strong>
      {statuses.length ? (
        <div className={styles.programStatuses}>
          {statuses.slice(0, 3).map(([status, count]) => (
            <span className={styles.programStatus} key={status} title={programStatusLabels[status as keyof typeof programStatusLabels]}>
              {programStatusLabels[status as keyof typeof programStatusLabels].slice(0, 3)} {count}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AttentionIndicator({ active }: { active: boolean }) {
  if (!active) return <span className={styles.noAttention} aria-label="Нет элементов, требующих внимания">—</span>;

  return (
    <span className={styles.attention} title="Есть элементы, требующие внимания" aria-label="Есть элементы, требующие внимания">
      <Attention size={20} fill="currentColor" />
    </span>
  );
}

function SortIndicator({ sorted }: { sorted: false | 'asc' | 'desc' }) {
  if (sorted === 'asc') return <SortUp size={16} fill="currentColor" />;
  if (sorted === 'desc') return <SortDown size={16} fill="currentColor" />;
  return <ChevronSort size={16} fill="currentColor" />;
}

function Filters({ state, searchInput, setSearchInput, onPatch, onReset, hasFilters }: {
  state: UniversityUrlState;
  searchInput: string;
  setSearchInput: (value: string) => void;
  onPatch: (patch: Record<string, string | number | string[] | null>) => void;
  onReset: () => void;
  hasFilters: boolean;
}) {
  return (
    <section className={styles.filters} aria-label="Фильтры списка вузов">
      <div className={`${styles.field} ${styles.searchField}`}>
        <label htmlFor="universities-search">Поиск по названию вуза</label>
        <div className={styles.inputWrap}>
          <Search size={18} fill="currentColor" />
          <input id="universities-search" type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Поиск по названию вуза" />
        </div>
      </div>
      <label className={styles.field}>
        <span>Город</span>
        <select value={state.city} onChange={(event) => onPatch({ city: event.target.value, page: 1 })}>
          <option value="">Все города</option>
          {universityFilterOptions.cities.map((city) => <option key={city} value={city}>{city}</option>)}
        </select>
      </label>
      <label className={styles.field}>
        <span>Ответственный</span>
        <select value={state.responsible} onChange={(event) => onPatch({ responsible: event.target.value, page: 1 })}>
          <option value="">Все ответственные</option>
          {universityFilterOptions.responsibles.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
        </select>
      </label>
      <details className={styles.multiselect}>
        <summary>
          <span>Health Score{state.healthStatuses.length ? ` (${state.healthStatuses.length})` : ''}</span>
          <ChevronDown size={16} fill="currentColor" />
        </summary>
        <div className={styles.multiselectMenu}>
          {HEALTH_STATUS_OPTIONS.map((option) => (
            <label key={option.value}>
              <input
                type="checkbox"
                checked={state.healthStatuses.includes(option.value)}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...state.healthStatuses, option.value]
                    : state.healthStatuses.filter((value) => value !== option.value);
                  onPatch({ health_status: next, page: 1 });
                }}
              />
              <StatusBadge status={option.value} />
            </label>
          ))}
        </div>
      </details>
      <label className={styles.field}>
        <span>Текущий этап</span>
        <select value={state.stage} onChange={(event) => onPatch({ stage: event.target.value, page: 1 })}>
          <option value="">Все этапы</option>
          {universityFilterOptions.stages.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <Button variant="ghost" size="s" type="button" disabled={!hasFilters} onClick={onReset}>Сбросить фильтры</Button>
    </section>
  );
}

function UniversityListSkeleton() {
  return (
    <div aria-live="polite" aria-busy="true">
      <div className={styles.desktopOnly}>
        <div className={styles.tableScroll}>
          <table className={styles.table} aria-label="Загрузка списка вузов">
            <tbody>
              {Array.from({ length: 6 }, (_, index) => (
                <tr key={index}>{Array.from({ length: 7 }, (_, cellIndex) => <td key={cellIndex}><span className={styles.skeletonLine} /></td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className={styles.mobileOnly}>
        <div className={styles.mobileSkeletons} aria-label="Загрузка списка вузов">
          {Array.from({ length: 4 }, (_, index) => <div className={styles.mobileSkeletonCard} key={index}><span className={styles.skeletonLine} /><span className={styles.skeletonLine} /><span className={styles.skeletonLine} /></div>)}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ filtered, onReset }: { filtered: boolean; onReset: () => void }) {
  return (
    <div className={styles.emptyState} role="status">
      <div className={styles.emptyIcon} aria-hidden="true"><Search size={20} fill="currentColor" /></div>
      <h2>{filtered ? 'По заданным фильтрам ничего не найдено' : 'Вузы пока не добавлены'}</h2>
      <p>{filtered ? 'Измените условия поиска или сбросьте фильтры.' : 'Когда появятся записи, они будут отображены в этом списке.'}</p>
      {filtered ? <Button variant="secondary" size="s" type="button" onClick={onReset}>Сбросить фильтры</Button> : null}
    </div>
  );
}

function MobileUniversityCards({ items }: { items: UniversityListItem[] }) {
  return (
    <div className={styles.mobileCards} aria-label="Список вузов в формате карточек">
      {items.map((item) => (
        <Link className={styles.mobileCard} href={`/universities/${item.id}`} key={item.id}>
          <div className={styles.mobileCardHeader}>
            <strong>{item.name}</strong>
            <AttentionIndicator active={item.attention} />
          </div>
          <div className={styles.mobileCardScore}><span>Health Score</span><strong>{item.healthScore}</strong><StatusBadge status={getHealthStatus(item.healthScore)} /></div>
          <dl className={styles.mobileDetails}>
            <div><dt>Этап</dt><dd><StageBadge item={item} /></dd></div>
            <div><dt>Ответственный</dt><dd>{item.responsible?.name ?? '—'}</dd></div>
            <div><dt>Программы</dt><dd>{item.programsCount}</dd></div>
            <div><dt>Последнее взаимодействие</dt><dd title={formatFullDate(item.lastInteractionAt)}>{formatRelativeTime(item.lastInteractionAt)}</dd></div>
          </dl>
        </Link>
      ))}
    </div>
  );
}

function Pagination({ page, pageSize, total, onPatch }: { page: number; pageSize: number; total: number; onPatch: (patch: Record<string, string | number | string[] | null>) => void }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const pages = Array.from({ length: Math.min(totalPages, 5) }, (_, index) => {
    if (totalPages <= 5) return index + 1;
    if (safePage <= 3) return index + 1;
    if (safePage >= totalPages - 2) return totalPages - 4 + index;
    return safePage - 2 + index;
  });
  const firstItem = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const lastItem = Math.min(safePage * pageSize, total);

  return (
    <nav className={styles.pagination} aria-label="Пагинация списка вузов">
      <span className={styles.paginationSummary}>{firstItem}–{lastItem} из {total}</span>
      <div className={styles.pageButtons}>
        <Button variant="secondary" size="s" type="button" disabled={safePage === 1} onClick={() => onPatch({ page: safePage - 1 })}>Назад</Button>
        {pages.map((pageNumber) => <button className={pageNumber === safePage ? styles.pageButtonActive : styles.pageButton} type="button" aria-current={pageNumber === safePage ? 'page' : undefined} key={pageNumber} onClick={() => onPatch({ page: pageNumber })}>{pageNumber}</button>)}
        <Button variant="secondary" size="s" type="button" disabled={safePage === totalPages} onClick={() => onPatch({ page: safePage + 1 })}>Далее</Button>
      </div>
      <label className={styles.pageSize}><span>На странице</span><select value={pageSize} onChange={(event) => onPatch({ page_size: Number(event.target.value), page: 1 })}>{PAGE_SIZE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
    </nav>
  );
}

function DesktopTable({ table }: { table: Table<UniversityListItem> }) {
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <caption className={styles.visuallyHidden}>Список вузов</caption>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined} key={header.id} scope="col">
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button type="button" className={styles.sortButton} onClick={header.column.getToggleSortingHandler()} aria-label={`Сортировать по ${String(header.column.columnDef.header)}`}>
                        {flexRender(header.column.columnDef.header, header.getContext())}<SortIndicator sorted={sorted} />
                      </button>
                    ) : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

export function UniversitiesList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(() => parseUrlState(searchParams), [searchParams]);
  const [searchInput, setSearchInput] = useState(state.search);

  const goToState = useCallback((patch: Record<string, string | number | string[] | null>) => {
    router.replace(`${pathname}${updateSearchParams(searchParams, patch)}`, { scroll: false });
  }, [pathname, router, searchParams]);

  useEffect(() => setSearchInput(state.search), [state.search]);
  useEffect(() => {
    if (searchInput === state.search) return undefined;
    const timeout = window.setTimeout(() => goToState({ search: searchInput, page: 1 }), 300);
    return () => window.clearTimeout(timeout);
  }, [goToState, searchInput, state.search]);

  const query = useQuery({
    queryKey: [...universitiesQueryKey, state],
    queryFn: () => getUniversities(state),
    placeholderData: keepPreviousData,
  });

  const sorting: SortingState = state.sort ? [{ id: state.sort, desc: state.order === 'desc' }] : [];
  const columns = useMemo<ColumnDef<UniversityListItem>[]>(() => [
    { accessorKey: 'name', header: 'ВУЗ', cell: ({ row }) => <Link className={styles.universityLink} href={`/universities/${row.original.id}`}>{row.original.name}</Link> },
    { id: 'responsible', accessorFn: (row) => row.responsible?.name ?? '', header: 'Ответственный', cell: ({ row }) => row.original.responsible?.name ?? '—' },
    { id: 'programs', accessorFn: (row) => row.programsCount, header: 'Программы', cell: ({ row }) => <ProgramsCell item={row.original} /> },
    { id: 'stage', accessorFn: (row) => row.currentStage.name, header: 'Текущий этап', cell: ({ row }) => <StageBadge item={row.original} /> },
    { id: 'health_score', accessorFn: (row) => row.healthScore, header: 'Health Score', cell: ({ row }) => <div className={styles.healthCell}><strong>{row.original.healthScore}</strong><StatusBadge status={getHealthStatus(row.original.healthScore)} /></div> },
    { id: 'last_interaction', accessorFn: (row) => row.lastInteractionAt, header: 'Последнее взаимодействие', cell: ({ row }) => <time dateTime={row.original.lastInteractionAt} title={formatFullDate(row.original.lastInteractionAt)}>{formatRelativeTime(row.original.lastInteractionAt)}</time> },
    { id: 'attention', enableSorting: false, header: 'Attention', cell: ({ row }) => <AttentionIndicator active={row.original.attention} /> },
  ], []);

  // TanStack Table intentionally returns an imperative table instance; React Compiler cannot memoize it safely.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: query.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    state: { sorting },
    onSortingChange: (updater: Updater<SortingState>) => {
      const nextSorting = typeof updater === 'function' ? updater(sorting) : updater;
      const next = nextSorting[0];
      goToState(next ? { sort: next.id, order: next.desc ? 'desc' : 'asc', page: 1 } : { sort: null, order: null, page: 1 });
    },
  });

  const hasFilters = Boolean(state.search || state.city || state.responsible || state.stage || state.healthStatuses.length);
  const resetFilters = () => {
    setSearchInput('');
    goToState({ search: null, city: null, responsible: null, health_status: null, stage: null, page: 1 });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>РЕЕСТР</p>
          <h1>ВУЗы</h1>
          <p className={styles.description}>Учебные заведения, программы и задачи, требующие внимания команды.</p>
        </div>
      </header>
      <Filters state={state} searchInput={searchInput} setSearchInput={setSearchInput} onPatch={goToState} onReset={resetFilters} hasFilters={hasFilters} />
      {query.isPending ? <UniversityListSkeleton /> : query.isError || !query.data ? <RouteErrorState onRetry={() => void query.refetch()} /> : query.data.total === 0 ? <EmptyState filtered={hasFilters} onReset={resetFilters} /> : (
        <>
          {query.isFetching ? <p className={styles.fetching} role="status">Обновляем список…</p> : null}
          <div className={styles.desktopOnly}><DesktopTable table={table} /></div>
          <div className={styles.mobileOnly}><MobileUniversityCards items={query.data.items} /></div>
          <Pagination page={query.data.page} pageSize={query.data.pageSize} total={query.data.total} onPatch={goToState} />
        </>
      )}
    </div>
  );
}

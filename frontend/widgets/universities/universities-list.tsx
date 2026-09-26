'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import ChevronSort from '@atomaro/icons/24/navigation/ChevronSort';
import SortDown from '@atomaro/icons/24/editor/SortDown';
import SortUp from '@atomaro/icons/24/editor/SortUp';
import { Button } from '@/shared/ui/rtk/button';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { Select } from '@/shared/ui/rtk/form-controls';
import { EmptyState } from '@/shared/ui/empty-state';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { StatusBadge as SemanticStatusBadge } from '@/shared/ui/rtk/status-badge';
import { TableShell } from '@/shared/ui/rtk/table-shell';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { TableSkeleton } from '@/shared/ui/skeleton';
import {
  getHealthStatus,
  healthStatusMeta,
  type HealthStatus,
} from '@/shared/lib/health-score';
import {
  getUniversities,
  programStatusLabels,
  UNIVERSITY_LIST_CAPABILITIES,
  universityFilterOptions,
  universitiesListQueryKey,
  type UniversityFilterOptions,
  type UniversityListItem,
  type UniversityListQuery,
  type UniversityFilters,
  type UniversitySortColumn,
} from '@/shared/lib/universities-repository';
import {
  catalogQueryKeys,
  getCatalogReferenceData,
  type CatalogReferenceData,
} from '@/shared/lib/catalogs-repository';
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
type QueryPatch = Record<string, string | number | string[] | null>;

const SORT_COLUMNS = new Set<UniversitySortColumn>(['name', 'responsible', 'programs', 'stage', 'health_score', 'last_interaction']);
const HEALTH_STATUSES = new Set<HealthStatus>(['green', 'yellow', 'red']);

function normalizeFilters(filters: UniversityFilters): UniversityFilters {
  return {
    ...filters,
    search: filters.search.trim(),
    universityIds: [...filters.universityIds].sort(),
    programIds: [...filters.programIds].sort(),
    productIds: [...filters.productIds].sort(),
    responsibleIds: [...filters.responsibleIds].sort(),
    healthStatuses: [...filters.healthStatuses].sort(),
  };
}

function parsePositiveInteger(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseUrlState(searchParams: SearchParamsLike): UniversityUrlState {
  const sortValue = searchParams.get('sort');
  const parseList = (key: string) => (searchParams.get(key) ?? '').split(',').map((value) => value.trim()).filter(Boolean);
  const parsedHealthStatuses = parseList('health_status').filter((value): value is HealthStatus => HEALTH_STATUSES.has(value as HealthStatus));
  const healthStatuses = UNIVERSITY_LIST_CAPABILITIES.healthStatusSelection === 'single'
    ? parsedHealthStatuses.slice(-1)
    : parsedHealthStatuses;
  const pageSizeValue = parsePositiveInteger(searchParams.get('page_size'), DEFAULT_PAGE_SIZE);
  const rawDateFrom = searchParams.get('date_from') ?? '';
  const rawDateTo = searchParams.get('date_to') ?? '';
  const dateFrom = rawDateFrom && rawDateTo && rawDateFrom > rawDateTo ? rawDateTo : rawDateFrom;
  const dateTo = rawDateFrom && rawDateTo && rawDateFrom > rawDateTo ? rawDateFrom : rawDateTo;

  return {
      filters: normalizeFilters({
      search: searchParams.get('search') ?? '',
      city: searchParams.get('city') ?? '',
      externalSource: searchParams.get('external_source') === 'lms' || searchParams.get('external_source') === 'website' ? searchParams.get('external_source') as 'lms' | 'website' : '',
      universityIds: parseList('university'),
      programIds: parseList('program'),
      productIds: parseList('product'),
      responsibleIds: parseList('responsible'),
      healthStatuses,
      workflowStageId: searchParams.get('stage') ?? '',
      dateFrom,
      dateTo,
      }),
    sort: SORT_COLUMNS.has(sortValue as UniversitySortColumn)
      && UNIVERSITY_LIST_CAPABILITIES.sorts[sortValue as UniversitySortColumn]
      ? sortValue as UniversitySortColumn
      : null,
    order: searchParams.get('order') === 'desc' ? 'desc' : 'asc',
    page: parsePositiveInteger(searchParams.get('page'), 1),
    pageSize: PAGE_SIZE_OPTIONS.includes(pageSizeValue) ? pageSizeValue : DEFAULT_PAGE_SIZE,
  };
}

const EMPTY_FILTERS: UniversityFilters = {
  search: '',
  city: '',
  externalSource: '',
  universityIds: [],
  programIds: [],
  productIds: [],
  responsibleIds: [],
  healthStatuses: [],
  workflowStageId: '',
  dateFrom: '',
  dateTo: '',
};

const FILTER_STORAGE_KEY = 'universities.filters.v1';

function filtersFromState(state: UniversityUrlState): UniversityFilters {
  return state.filters;
}

function hasActiveFilters(filters: UniversityFilters): boolean {
  return Boolean(
    filters.search || filters.city || filters.externalSource || filters.universityIds.length || filters.programIds.length ||
    filters.productIds.length || filters.responsibleIds.length || filters.healthStatuses.length ||
    filters.workflowStageId || filters.dateFrom || filters.dateTo,
  );
}

function parseStoredFilters(value: string | null): UniversityFilters | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<UniversityFilters>;
    if (!parsed || typeof parsed !== 'object') return null;
    const storedFilters: UniversityFilters = {
      ...EMPTY_FILTERS,
      ...parsed,
      universityIds: Array.isArray(parsed.universityIds) ? parsed.universityIds.filter((item): item is string => typeof item === 'string') : [],
      programIds: Array.isArray(parsed.programIds) ? parsed.programIds.filter((item): item is string => typeof item === 'string') : [],
      productIds: Array.isArray(parsed.productIds) ? parsed.productIds.filter((item): item is string => typeof item === 'string') : [],
      responsibleIds: Array.isArray(parsed.responsibleIds) ? parsed.responsibleIds.filter((item): item is string => typeof item === 'string') : [],
      healthStatuses: Array.isArray(parsed.healthStatuses) ? parsed.healthStatuses.filter((item): item is HealthStatus => HEALTH_STATUSES.has(item as HealthStatus)) : [],
      search: typeof parsed.search === 'string' ? parsed.search : '',
      city: typeof parsed.city === 'string' ? parsed.city : '',
      externalSource: parsed.externalSource === 'lms' || parsed.externalSource === 'website' ? parsed.externalSource : '',
      workflowStageId: typeof parsed.workflowStageId === 'string' ? parsed.workflowStageId : '',
      dateFrom: typeof parsed.dateFrom === 'string' ? parsed.dateFrom : '',
      dateTo: typeof parsed.dateTo === 'string' ? parsed.dateTo : '',
    };
    if (storedFilters.dateFrom && storedFilters.dateTo && storedFilters.dateFrom > storedFilters.dateTo) {
      [storedFilters.dateFrom, storedFilters.dateTo] = [storedFilters.dateTo, storedFilters.dateFrom];
    }
    return normalizeFilters(storedFilters);
  } catch {
    return null;
  }
}

function filtersPatch(filters: UniversityFilters): QueryPatch {
  return {
    search: filters.search || null,
    city: filters.city || null,
    external_source: filters.externalSource || null,
    university: filters.universityIds,
    program: filters.programIds,
    product: filters.productIds,
    responsible: filters.responsibleIds,
    health_status: filters.healthStatuses,
    stage: filters.workflowStageId || null,
    date_from: filters.dateFrom || null,
    date_to: filters.dateTo || null,
    page: 1,
  };
}

const URL_FILTER_KEYS = ['search', 'city', 'external_source', 'university', 'program', 'product', 'responsible', 'health_status', 'stage', 'date_from', 'date_to'];

function hasUrlFilterParams(searchParams: SearchParamsLike): boolean {
  return URL_FILTER_KEYS.some((key) => searchParams.get(key) !== null);
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
  return <SemanticStatusBadge intent={meta.tone}>{meta.label}</SemanticStatusBadge>;
}

function StageBadge({ item }: { item: UniversityListItem }) {
  if (item.availability?.stage === false) return <span>—</span>;
  return <SemanticStatusBadge intent={item.currentStage.tone}>{item.currentStage.name}</SemanticStatusBadge>;
}

function ProgramsCell({ item }: { item: UniversityListItem }) {
  if (item.availability?.programs === false) return <span>—</span>;
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

function Filters({ state, options, catalogsLoading, catalogsUnavailable, searchInput, setSearchInput, onPatch, compact = false }: {
  state: UniversityUrlState;
  options: UniversityFilterOptions;
  catalogsLoading: boolean;
  catalogsUnavailable: boolean;
  searchInput: string;
  setSearchInput: (value: string) => void;
  onPatch: (patch: QueryPatch) => void;
  compact?: boolean;
}) {
  const filters = filtersFromState(state);
  const searchId = compact ? 'universities-search-mobile' : 'universities-search';
  const updateDateRange = (key: 'date_from' | 'date_to', value: string) => {
    if (key === 'date_from' && value && filters.dateTo && value > filters.dateTo) {
      onPatch({ date_from: value, date_to: value, page: 1 });
      return;
    }
    if (key === 'date_to' && value && filters.dateFrom && value < filters.dateFrom) {
      onPatch({ date_from: value, date_to: value, page: 1 });
      return;
    }
    onPatch({ [key]: value, page: 1 });
  };

  return (
    <section className={styles.filters} aria-label="Фильтры списка вузов">
      <div className={`${styles.field} ${styles.searchField}`}>
        <label htmlFor={searchId}>Поиск по названию вуза</label>
        <div className={styles.inputWrap}>
          <Search size={18} fill="currentColor" />
          <input id={searchId} type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Поиск по названию вуза" />
        </div>
      </div>
      <MultiSelect label="Вуз" labelPlacement="outside" options={options.universities} values={filters.universityIds} onChange={(values) => onPatch({ university: values, page: 1 })} searchable loading={catalogsLoading} disabled={catalogsUnavailable} />
      <MultiSelect label="Программа" labelPlacement="outside" options={options.programs} values={filters.programIds} onChange={(values) => onPatch({ program: values, page: 1 })} loading={catalogsLoading} disabled={catalogsUnavailable} />
      <MultiSelect label="Продукт" labelPlacement="outside" options={options.products} values={filters.productIds} onChange={(values) => onPatch({ product: values, page: 1 })} loading={catalogsLoading} disabled={catalogsUnavailable} />
      <label className={styles.field}>
        <span>Город</span>
        <Select disabled={catalogsLoading || catalogsUnavailable} value={filters.city} onChange={(event) => onPatch({ city: event.target.value, page: 1 })}>
          <option value="">Все города</option>
          {options.cities.map((city) => <option key={city} value={city}>{city}</option>)}
        </Select>
      </label>
      <MultiSelect label="Ответственный" labelPlacement="outside" options={options.responsibles.map((person) => ({ id: person.id, name: person.name, description: person.role }))} values={filters.responsibleIds} onChange={(values) => onPatch({ responsible: values, page: 1 })} loading={catalogsLoading} disabled={catalogsUnavailable} />
      <MultiSelect label="Health Score" labelPlacement="outside" options={HEALTH_STATUS_OPTIONS.map((option) => ({ id: option.value, name: option.label }))} values={filters.healthStatuses} onChange={(values) => onPatch({ health_status: UNIVERSITY_LIST_CAPABILITIES.healthStatusSelection === 'single' ? values.slice(-1) : values, page: 1 })} renderOption={(option) => <StatusBadge status={option.id as HealthStatus} />} hint={UNIVERSITY_LIST_CAPABILITIES.healthStatusSelection === 'single' ? 'Backend поддерживает выбор одного статуса.' : undefined} />
      <label className={styles.field} title={!UNIVERSITY_LIST_CAPABILITIES.filters.stage ? 'Backend пока не публикует фильтр по текущему этапу.' : undefined}>
        <span>Текущий этап</span>
        <Select disabled={!UNIVERSITY_LIST_CAPABILITIES.filters.stage} value={filters.workflowStageId} onChange={(event) => onPatch({ stage: event.target.value, page: 1 })}>
          <option value="">Все этапы</option>
          {options.stages.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
      </label>
      <div className={styles.periodField}><DateRangeField presets label={UNIVERSITY_LIST_CAPABILITIES.dateMeaning === 'created-at' ? 'Период создания' : 'Период последнего взаимодействия'} from={filters.dateFrom} to={filters.dateTo} onFromChange={(value) => updateDateRange('date_from', value)} onToChange={(value) => updateDateRange('date_to', value)} onRangeChange={(dateFrom, dateTo) => onPatch({ date_from: dateFrom, date_to: dateTo, page: 1 })} /></div>
    </section>
  );
}

function selectedNames(values: string[], options: Array<{ id: string; name: string }>): string {
  const names = values.map((value) => options.find((option) => option.id === value)?.name ?? value);
  if (names.length <= 2) return names.join(', ');
  return `${names.slice(0, 2).join(', ')} +${names.length - 2}`;
}

function ActiveFilterChips({ filters, options, onPatch, onReset }: { filters: UniversityFilters; options: UniversityFilterOptions; onPatch: (patch: QueryPatch) => void; onReset: () => void }) {
  const chips: Array<{ key: string; label: string; patch: QueryPatch }> = [];
  if (filters.search) chips.push({ key: 'search', label: `Поиск: ${filters.search}`, patch: { search: null, page: 1 } });
  if (filters.universityIds.length) chips.push({ key: 'university', label: `Вуз: ${selectedNames(filters.universityIds, options.universities)}`, patch: { university: null, page: 1 } });
  if (filters.programIds.length) chips.push({ key: 'program', label: `Программа: ${selectedNames(filters.programIds, options.programs)}`, patch: { program: null, page: 1 } });
  if (filters.productIds.length) chips.push({ key: 'product', label: `Продукт: ${selectedNames(filters.productIds, options.products)}`, patch: { product: null, page: 1 } });
  if (filters.city) chips.push({ key: 'city', label: `Город: ${filters.city}`, patch: { city: null, page: 1 } });
  if (filters.externalSource) chips.push({ key: 'external_source', label: filters.externalSource === 'lms' ? 'Источник: LMS' : 'Источник: сайт', patch: { external_source: null, page: 1 } });
  if (filters.responsibleIds.length) chips.push({ key: 'responsible', label: `Ответственный: ${selectedNames(filters.responsibleIds, options.responsibles)}`, patch: { responsible: null, page: 1 } });
  if (filters.healthStatuses.length) chips.push({ key: 'health_status', label: `Health Score: ${selectedNames(filters.healthStatuses, HEALTH_STATUS_OPTIONS.map((option) => ({ id: option.value, name: option.label })))}`, patch: { health_status: null, page: 1 } });
  if (filters.workflowStageId) chips.push({ key: 'stage', label: `Этап: ${options.stages.find((item) => item.id === filters.workflowStageId)?.name ?? filters.workflowStageId}`, patch: { stage: null, page: 1 } });
  if (filters.dateFrom || filters.dateTo) chips.push({ key: 'date', label: `Период: ${filters.dateFrom || '…'} — ${filters.dateTo || '…'}`, patch: { date_from: null, date_to: null, page: 1 } });
  if (!chips.length) return null;

  return (
    <div className={styles.activeFilters} aria-label="Активные фильтры">
      <span className={styles.activeFiltersLabel}>Активные фильтры</span>
      <div className={styles.chipList}>
        {chips.map((chip) => <button className={styles.filterChip} type="button" key={chip.key} onClick={() => onPatch(chip.patch)} aria-label={`Удалить фильтр «${chip.label}»`}>{chip.label}<CloseSmall size={14} fill="currentColor" aria-hidden="true" /></button>)}
        <button className={styles.clearAllButton} type="button" onClick={onReset}>Сбросить всё</button>
      </div>
    </div>
  );
}

function filterOptionsFromCatalogs(references?: CatalogReferenceData): UniversityFilterOptions {
  if (!references) {
    return { cities: [], responsibles: [], stages: universityFilterOptions.stages, universities: [], programs: [], products: [] };
  }
  return {
    cities: [...new Set(references.universities.map((item) => item.description).filter((city): city is string => Boolean(city)))].sort((left, right) => left.localeCompare(right, 'ru')),
    responsibles: references.responsibles.map((item) => ({ id: item.id, name: item.name, role: item.description })),
    stages: universityFilterOptions.stages,
    universities: references.universities,
    programs: references.programs,
    products: references.products,
  };
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
          <div className={styles.mobileCardScore}><span>Health Score</span>{item.availability?.healthScore === false ? <strong>—</strong> : <><strong>{item.healthScore}</strong><StatusBadge status={getHealthStatus(item.healthScore)} /></>}</div>
          <dl className={styles.mobileDetails}>
            <div><dt>Этап</dt><dd><StageBadge item={item} /></dd></div>
            <div><dt>Ответственный</dt><dd>{item.responsible?.name ?? '—'}</dd></div>
            <div><dt>Программы</dt><dd>{item.availability?.programs === false ? '—' : item.programsCount}</dd></div>
            <div><dt>Последнее взаимодействие</dt><dd title={item.availability?.lastInteraction === false ? undefined : formatFullDate(item.lastInteractionAt)}>{item.availability?.lastInteraction === false ? '—' : formatRelativeTime(item.lastInteractionAt)}</dd></div>
          </dl>
          <span className={styles.mobileCardAction}>Открыть</span>
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
          {table.getRowModel().rows.map((row) => <tr key={row.id} data-testid={`university-row-${row.original.id}`}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}
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
  const [searchInput, setSearchInput] = useState(state.filters.search);
  const storageRestoredRef = useRef(false);
  const storageReadyRef = useRef(false);
  const pendingStoredFiltersRef = useRef<UniversityFilters | null>(null);

  const goToState = useCallback((patch: QueryPatch) => {
    router.replace(`${pathname}${updateSearchParams(searchParams, patch)}`, { scroll: false });
  }, [pathname, router, searchParams]);

  useEffect(() => setSearchInput(state.filters.search), [state.filters.search]);
  useEffect(() => {
    if (searchInput === state.filters.search) return undefined;
    const timeout = window.setTimeout(() => goToState({ search: searchInput, page: 1 }), 300);
    return () => window.clearTimeout(timeout);
  }, [goToState, searchInput, state.filters.search]);

  useEffect(() => {
    if (storageRestoredRef.current) return;
    if (hasUrlFilterParams(searchParams)) {
      storageRestoredRef.current = true;
      storageReadyRef.current = true;
      return;
    }
    storageRestoredRef.current = true;
    const storedFilters = parseStoredFilters(window.localStorage.getItem(FILTER_STORAGE_KEY));
    if (storedFilters && hasActiveFilters(storedFilters)) {
      pendingStoredFiltersRef.current = storedFilters;
      goToState(filtersPatch(storedFilters));
    } else {
      storageReadyRef.current = true;
    }
  }, [goToState, searchParams]);

  useEffect(() => {
    if (pendingStoredFiltersRef.current) {
      if (JSON.stringify(state.filters) !== JSON.stringify(pendingStoredFiltersRef.current)) return;
      pendingStoredFiltersRef.current = null;
      storageReadyRef.current = true;
    }
    if (!storageReadyRef.current) return;
    window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(state.filters));
  }, [state.filters]);

  const query = useQuery({
    queryKey: universitiesListQueryKey(state),
    queryFn: ({ signal }) => getUniversities(state, signal),
    placeholderData: keepPreviousData,
  });
  const catalogsQuery = useQuery({
    queryKey: catalogQueryKeys.references,
    queryFn: ({ signal }) => getCatalogReferenceData(signal),
    staleTime: 5 * 60_000,
  });
  const filterOptions = useMemo(() => filterOptionsFromCatalogs(catalogsQuery.data), [catalogsQuery.data]);

  const sorting: SortingState = state.sort ? [{ id: state.sort, desc: state.order === 'desc' }] : [];
  const columns = useMemo<ColumnDef<UniversityListItem>[]>(() => [
    { accessorKey: 'name', header: 'ВУЗ', cell: ({ row }) => <Link className={styles.universityLink} href={`/universities/${row.original.id}`}>{row.original.name}</Link> },
    { id: 'responsible', accessorFn: (row) => row.responsible?.name ?? '', enableSorting: UNIVERSITY_LIST_CAPABILITIES.sorts.responsible, header: 'Ответственный', cell: ({ row }) => row.original.responsible?.name ?? '—' },
    { id: 'programs', accessorFn: (row) => row.programsCount, enableSorting: UNIVERSITY_LIST_CAPABILITIES.sorts.programs, header: 'Программы', cell: ({ row }) => <ProgramsCell item={row.original} /> },
    { id: 'stage', accessorFn: (row) => row.currentStage.name, enableSorting: UNIVERSITY_LIST_CAPABILITIES.sorts.stage, header: 'Текущий этап', cell: ({ row }) => <StageBadge item={row.original} /> },
    { id: 'health_score', accessorFn: (row) => row.healthScore, enableSorting: UNIVERSITY_LIST_CAPABILITIES.sorts.health_score, header: 'Health Score', cell: ({ row }) => row.original.availability?.healthScore === false ? '—' : <div className={styles.healthCell}><strong>{row.original.healthScore}</strong><StatusBadge status={getHealthStatus(row.original.healthScore)} /></div> },
    { id: 'last_interaction', accessorFn: (row) => row.lastInteractionAt, enableSorting: UNIVERSITY_LIST_CAPABILITIES.sorts.last_interaction, header: 'Последнее взаимодействие', cell: ({ row }) => row.original.availability?.lastInteraction === false ? '—' : <time dateTime={row.original.lastInteractionAt} title={formatFullDate(row.original.lastInteractionAt)}>{formatRelativeTime(row.original.lastInteractionAt)}</time> },
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

  const hasFilters = hasActiveFilters(state.filters);
  const activeFilterCount = [
    state.filters.search,
    state.filters.city,
    state.filters.externalSource,
    state.filters.universityIds.length,
    state.filters.programIds.length,
    state.filters.productIds.length,
    state.filters.responsibleIds.length,
    state.filters.healthStatuses.length,
    state.filters.workflowStageId,
    state.filters.dateFrom || state.filters.dateTo,
  ].filter(Boolean).length;
  const resetFilters = () => {
    setSearchInput('');
    goToState(filtersPatch(EMPTY_FILTERS));
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>ВУЗы</h1>
          <p className={styles.description}>Учебные заведения, программы и задачи, требующие внимания команды.</p>
        </div>
      </header>
      <div className={styles.filterArea}>
        <FilterToolbar label="Фильтры списка вузов" collapsible desktopGridClassName={styles.filterGrid} controls={(mobile) => <Filters compact={mobile} state={state} options={filterOptions} catalogsLoading={catalogsQuery.isPending} catalogsUnavailable={catalogsQuery.isError} searchInput={searchInput} setSearchInput={setSearchInput} onPatch={goToState} />} onReset={resetFilters} resetDisabled={!hasFilters} mobileCount={activeFilterCount} />
        <ActiveFilterChips filters={state.filters} options={filterOptions} onPatch={goToState} onReset={resetFilters} />
        {catalogsQuery.isError ? <RouteErrorState compact onRetry={() => void catalogsQuery.refetch()} /> : null}
      </div>
      {query.isPending ? <TableSkeleton rows={6} columns={7} label="Загрузка списка вузов" /> : !query.data ? <RouteErrorState onRetry={() => void query.refetch()} /> : query.data.total === 0 ? <EmptyState icon={<Search size={20} fill="currentColor" />} title={hasFilters ? 'По заданным фильтрам ничего не найдено' : 'Вузы пока не добавлены'} description={hasFilters ? 'Измените условия поиска или сбросьте фильтры.' : 'Когда появятся записи, они будут отображены в этом списке.'} primaryAction={hasFilters ? { label: 'Сбросить фильтры', onClick: resetFilters, variant: 'secondary' } : undefined} /> : (
        <>
          <p className={styles.fetching} role="status">{query.isFetching ? 'Обновляем список…' : '\u00a0'}</p>
          <TableShell>
            <div className={styles.desktopOnly}><DesktopTable table={table} /></div>
            <div className={styles.mobileOnly}><MobileUniversityCards items={query.data.items} /></div>
            <Pagination page={query.data.page} pageSize={query.data.pageSize} total={query.data.total} onPatch={goToState} />
          </TableShell>
        </>
      )}
    </div>
  );
}

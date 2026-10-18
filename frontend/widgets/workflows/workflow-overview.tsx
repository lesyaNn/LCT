'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWorkflowOverview, workflowOverviewQueryKey, type WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { Input } from '@/shared/ui/rtk/form-controls';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { DEFAULT_PAGE_SIZE, Pagination } from '@/shared/ui/rtk/pagination';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { EmptyState } from '@/shared/ui/empty-state';
import { WorkflowCard } from './workflow-card';
import { WorkflowBoard } from './workflow-board';
import styles from './workflow-overview.module.css';

type View = 'list' | 'board';
const viewTabs = [{ id: 'list', label: 'Список' }, { id: 'board', label: 'Канбан' }] as const;
type SelectionKey = 'university' | 'city' | 'program' | 'responsible' | 'status' | 'stage';
type Filters = { search: string } & Record<SelectionKey, string[]>;
const initialFilters: Filters = { search: '', university: [], city: [], program: [], responsible: [], status: [], stage: [] };
const statusOptions = [
  { id: 'in_progress', name: 'В работе' },
  { id: 'overdue', name: 'Просрочен' },
  { id: 'completed', name: 'Завершён' },
];
const selects = [
  { key: 'university', label: 'ВУЗ', all: 'Все ВУЗы' },
  { key: 'city', label: 'Город', all: 'Все города' },
  { key: 'program', label: 'ИТ-программа', all: 'Все ИТ-программы' },
  { key: 'responsible', label: 'Ответственный за этап', all: 'Все сотрудники' },
  { key: 'stage', label: 'Текущий этап', all: 'Все этапы' },
  { key: 'status', label: 'Статус', all: 'Все статусы' },
] as const;

function WorkflowList({ items }: { items: WorkflowOverviewItem[] }) {
  return <div className={styles.list}>{items.map((item) => <WorkflowCard item={item} key={item.instanceId} />)}</div>;
}

function options(items: WorkflowOverviewItem[], field: 'university' | 'city' | 'program' | 'responsible' | 'stage') {
  const map = new Map<string, string>();
  for (const item of items) {
    const value = field === 'university' ? [item.universityId, item.universityName]
      : field === 'city' ? [item.universityCity, item.universityCity]
      : field === 'program' ? [item.programName, item.programName]
        : field === 'responsible' ? [item.responsible?.id, item.responsible?.name]
          : [item.stageKey, item.stage.name];
    if (value[0] && value[1]) map.set(value[0], value[1]);
  }
  return [...map].sort((a, b) => a[1].localeCompare(b[1], 'ru'));
}

export function WorkflowOverviewPage() {
  const [view, setView] = useState<View>('list');
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const query = useQuery({ queryKey: workflowOverviewQueryKey, queryFn: getWorkflowOverview, staleTime: 30_000 });
  const items = query.data?.items ?? [];
  const update = (key: SelectionKey, values: string[]) => {
    setFilters((current) => ({ ...current, [key]: values }));
    setPage(1);
  };
  const filtered = items.filter((item) => {
    const search = filters.search.trim().toLocaleLowerCase('ru-RU');
    return (!search || `${item.universityName} ${item.programName ?? ''} ${item.stage.name} ${item.responsible?.name ?? ''}`.toLocaleLowerCase('ru-RU').includes(search))
      && (!filters.university.length || filters.university.includes(item.universityId))
      && (!filters.city.length || (item.universityCity !== null && filters.city.includes(item.universityCity)))
      && (!filters.program.length || (item.programName !== null && filters.program.includes(item.programName)))
      && (!filters.responsible.length || (item.responsible !== null && filters.responsible.includes(item.responsible.id)))
      && (!filters.status.length || filters.status.includes(item.status))
      && (!filters.stage.length || filters.stage.includes(item.stageKey));
  });
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / pageSize)));
  const visibleItems = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const filterControls = () => <><label><span>Поиск</span><Input type="search" placeholder="ВУЗ, программа или этап" value={filters.search} onChange={(event) => { setFilters((current) => ({ ...current, search: event.target.value })); setPage(1); }} /></label>{selects.map(({ key, label, all }) => <MultiSelect key={key} label={label} labelPlacement="outside" values={filters[key]} onChange={(values) => update(key, values)} options={key === 'status' ? statusOptions : options(items, key).map(([id, name]) => ({ id, name }))} searchable placeholder={all} hint={query.data?.limited ? 'Поиск среди загруженных процессов.' : undefined} />)}</>;
  const activeSelections = selects.filter(({ key }) => filters[key].length > 0);
  const hasFilters = Boolean(filters.search || activeSelections.length);
  return <div className={styles.page}><header className={styles.heading}><div><h1>Workflow</h1><p>Процессы взаимодействия с ВУЗами</p></div><Tabs items={viewTabs} activeId={view} onChange={(id) => setView(id as View)} label="Представление Workflow" prefix="workflow-view" panelPrefix="workflow-view-panel" alternating /></header>
    <FilterToolbar activeFilters={[...(filters.search ? [{ id: 'search', label: `Поиск: ${filters.search}`, onRemove: () => { setFilters((current) => ({ ...current, search: '' })); setPage(1); } }] : []), ...activeSelections.map(({ key, label }) => ({ id: key, label: `${label}: выбрано ${filters[key].length}`, onRemove: () => update(key, []) }))]} label="Фильтры Workflow" collapsible controls={filterControls} onReset={() => { setFilters(initialFilters); setPage(1); }} resetDisabled={!hasFilters} mobileCount={Number(Boolean(filters.search)) + activeSelections.length} />
    <section className={styles.content} id={`workflow-view-panel-${view}`} role="tabpanel" aria-labelledby={`workflow-view-${view}`}>
        {query.isPending ? <p className={styles.message}>Загрузка процессов…</p> : !query.data ? <RouteErrorState onRetry={() => void query.refetch()} /> : <><div className={styles.summary}><strong>{filtered.length} процессов</strong>{query.data.limited ? <span>Загружена только часть процессов. Обновите страницу позже.</span> : null}{query.data.unavailableUniversities ? <span>Часть данных ВУЗов недоступна.</span> : null}</div>{filtered.length ? view === 'board' ? <WorkflowBoard items={filtered} /> : <div className={styles.listView}><WorkflowList items={visibleItems} /><Pagination label="Пагинация списка Workflow" page={currentPage} pageSize={pageSize} total={filtered.length} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} /></div> : <EmptyState title="Процессы не найдены" description={items.length ? 'Измените фильтры.' : 'Процессы появятся после запуска работы с вузами.'} />}</>}
    </section>
  </div>;
}

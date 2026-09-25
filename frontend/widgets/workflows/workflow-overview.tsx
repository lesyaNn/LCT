'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWorkflowOverview, workflowOverviewQueryKey, type WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { EmptyState } from '@/shared/ui/empty-state';
import { WorkflowCard } from './workflow-card';
import { WorkflowBoard } from './workflow-board';
import styles from './workflow-overview.module.css';

type View = 'list' | 'board';
type Filters = { search: string; university: string; program: string; responsible: string; status: string; stage: string };
const initialFilters: Filters = { search: '', university: '', program: '', responsible: '', status: '', stage: '' };

function WorkflowList({ items }: { items: WorkflowOverviewItem[] }) {
  return <div className={styles.list}>{items.map((item) => <WorkflowCard item={item} key={item.instanceId} />)}</div>;
}

function options(items: WorkflowOverviewItem[], field: 'university' | 'program' | 'responsible' | 'stage') {
  const map = new Map<string, string>();
  for (const item of items) {
    const value = field === 'university' ? [item.universityId, item.universityName]
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
  const query = useQuery({ queryKey: workflowOverviewQueryKey, queryFn: getWorkflowOverview, staleTime: 30_000 });
  const items = query.data?.items ?? [];
  const update = (key: keyof Filters, value: string) => setFilters((current) => ({ ...current, [key]: value }));
  const filtered = items.filter((item) => {
    const search = filters.search.trim().toLocaleLowerCase('ru-RU');
    return (!search || `${item.universityName} ${item.programName ?? ''} ${item.stage.name} ${item.responsible?.name ?? ''}`.toLocaleLowerCase('ru-RU').includes(search))
      && (!filters.university || item.universityId === filters.university)
      && (!filters.program || item.programName === filters.program)
      && (!filters.responsible || item.responsible?.id === filters.responsible)
      && (!filters.status || item.status === filters.status)
      && (!filters.stage || item.stageKey === filters.stage);
  });
  const selects = [
    { key: 'university', label: 'ВУЗ', all: 'Все ВУЗы' },
    { key: 'program', label: 'Программа', all: 'Все программы' },
    { key: 'responsible', label: 'Ответственный за ВУЗ', all: 'Все сотрудники' },
    { key: 'stage', label: 'Этап', all: 'Все этапы' },
  ] as const;
  const filterControls = () => <><label><span>Поиск</span><Input type="search" placeholder="ВУЗ, программа или этап" value={filters.search} onChange={(event) => update('search', event.target.value)} /></label>{selects.map(({ key, label, all }) => <label key={key}><span>{label}</span><Select value={filters[key]} onChange={(event) => update(key, event.target.value)}><option value="">{all}</option>{options(items, key).map(([id, name]) => <option value={id} key={id}>{name}</option>)}</Select></label>)}<label><span>Статус</span><Select value={filters.status} onChange={(event) => update('status', event.target.value)}><option value="">Все статусы</option><option value="in_progress">В работе</option><option value="overdue">Просрочен</option><option value="completed">Завершён</option></Select></label></>;
  return <div className={styles.page}><header className={styles.heading}><div><h1>Workflow</h1><p>Процессы взаимодействия с ВУЗами</p></div><Tabs items={[{ id: 'list', label: 'Список' }, { id: 'board', label: 'Доска' }]} activeId={view} onChange={(id) => setView(id as View)} label="Представление Workflow" prefix="workflow-view" /></header>
    <FilterToolbar label="Фильтры Workflow" controls={filterControls} onReset={() => setFilters(initialFilters)} resetDisabled={Object.values(filters).every((value) => !value)} mobileCount={Object.values(filters).filter(Boolean).length} />
    {query.isPending ? <p className={styles.message}>Загрузка процессов…</p> : query.isError ? <RouteErrorState onRetry={() => void query.refetch()} /> : <section className={styles.content} id={`workflow-view-panel`} role="tabpanel" aria-labelledby={`workflow-view-${view}`}><div className={styles.summary}><strong>{filtered.length} процессов</strong>{query.data?.limited ? <span>Показаны первые 100 процессов. Остальные доступны на следующих страницах API.</span> : null}{query.data?.unavailableUniversities ? <span>Часть данных ВУЗов недоступна.</span> : null}</div>{filtered.length ? view === 'board' ? <WorkflowBoard items={filtered} /> : <WorkflowList items={filtered} /> : <EmptyState title="Процессы не найдены" description={items.length ? 'Измените фильтры.' : 'В доступных данных пока нет связанных Workflow-инстансов.'} />}</section>}
  </div>;
}

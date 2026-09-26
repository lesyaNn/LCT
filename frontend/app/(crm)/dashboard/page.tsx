'use client';

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import Education from '@atomaro/icons/24/culture/Education';
import Book from '@atomaro/icons/24/culture/Book';
import Group from '@atomaro/icons/24/business/Group';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import Attention from '@atomaro/icons/24/action/Attention';
import Time from '@atomaro/icons/24/alert/TimeStroke';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Checklist from '@atomaro/icons/24/action/Checklist';
import { dashboardDataQueryKey, EMPTY_DASHBOARD_FILTERS, getDashboardData, type DashboardFilters, type DashboardOverview } from '@/shared/lib/dashboard-repository';
import { catalogQueryKeys, getCatalogReferenceData } from '@/shared/lib/catalogs-repository';
import { DateRangeField } from '@/shared/ui/rtk/date-range-field';
import { FilterToolbar } from '@/shared/ui/rtk/filter-surface';
import { MultiSelect } from '@/shared/ui/rtk/multiselect';
import { PageIntro } from '@/shared/ui/page-intro';
import { PageSkeleton } from '@/shared/ui/page-skeleton';
import { BackgroundRefreshNotice } from '@/shared/ui/background-refresh-notice';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { KpiCard, type KpiTone } from '@/widgets/dashboard/kpi-card';
import { DashboardAnalytics } from '@/widgets/dashboard/dashboard-charts';
import styles from '@/widgets/dashboard/dashboard.module.css';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { formatDateTimeRu } from '@/shared/lib/formatters';

const numberFormatter = new Intl.NumberFormat('ru-RU');
const scoreFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function formatCount(value: number | null) {
  return value === null ? '—' : numberFormatter.format(value);
}

function formatScore(value: number | null) {
  return value === null ? '—' : `${scoreFormatter.format(value)}%`;
}

interface KpiDefinition {
  title: string;
  caption: string;
  tone: KpiTone;
  icon: typeof Education;
  href?: string;
  ariaLabel?: string;
  value: (overview: DashboardOverview) => string;
  tooltip?: (overview: DashboardOverview) => string;
}

const kpiDefinitions: KpiDefinition[] = [
  { title: 'Вузы', caption: 'в реестре', tone: 'brand', icon: Education, value: (overview) => formatCount(overview.universitiesTotal) },
  { title: 'Средний Health Score', caption: 'среднее по вузам', tone: 'brand', icon: StatisticsBoard, value: (overview) => formatScore(overview.averageHealthScore) },
  { title: 'Красные вузы', caption: 'нуждаются во внимании', tone: 'danger', icon: Attention, href: '/universities?health_status=red', ariaLabel: 'Перейти к красным вузам', value: (overview) => formatCount(overview.redUniversities) },
  { title: 'Просроченные этапы', caption: 'требуют контроля', tone: 'danger', icon: Time, href: '/workflows?overdue=true', ariaLabel: 'Перейти к просроченным этапам workflow', value: (overview) => formatCount(overview.overdueStages) },
  { title: 'Истекающие лицензии', caption: 'до истечения 30 дней', tone: 'warning', icon: DocumentText, value: (overview) => formatCount(overview.expiringLicenses) },
  { title: 'Активные программы', caption: 'запущены', tone: 'orange', icon: Book, value: (overview) => formatCount(overview.activePrograms) },
  { title: 'Преподаватели к повышению', caption: 'требуют внимания', tone: 'warning', icon: Group, value: (overview) => formatCount(overview.teachersNeedUpgrade) },
  {
    title: 'Заявки с сайта за 7 дней',
    caption: 'новые заявки',
    tone: 'orange',
    icon: Checklist,
    href: '/universities?external_source=website',
    ariaLabel: 'Открыть список ВУЗов с заявками с сайта',
    value: (overview) => formatCount(overview.websiteApplications7d),
    tooltip: (overview) => `Источник: сайт${overview.mode === 'mock' ? ' (тестовые данные)' : overview.mode === 'import' ? ' (данные импорта)' : ''}\nСинхронизировано: ${overview.websiteSyncedAt ? formatDateTimeRu(overview.websiteSyncedAt) : 'недоступно'}`,
  },
  {
    title: 'Обучающиеся в LMS',
    caption: 'активные записи',
    tone: 'brand',
    icon: Group,
    href: '/universities?external_source=lms',
    ariaLabel: 'Открыть список ВУЗов с данными LMS',
    value: (overview) => formatCount(overview.lmsStudents),
    tooltip: (overview) => `Источник: LMS${overview.mode === 'mock' ? ' (тестовые данные)' : ''}\nСинхронизировано: ${overview.lmsSyncedAt ? formatDateTimeRu(overview.lmsSyncedAt) : 'недоступно'}`,
  },
];

export default function DashboardPage() {
  const [filters, setFilters] = useState<DashboardFilters>(EMPTY_DASHBOARD_FILTERS);
  const references = useQuery({ queryKey: catalogQueryKeys.references, queryFn: () => getCatalogReferenceData(), staleTime: 5 * 60_000 });
  const overviewQuery = useQuery({
    queryKey: dashboardDataQueryKey(filters),
    queryFn: () => getDashboardData(filters),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  const activeFilters = [
    ...(filters.dateFrom || filters.dateTo ? [{ id: 'period', label: `Период: ${filters.dateFrom || '…'} — ${filters.dateTo || '…'}`, onRemove: () => setFilters((current) => ({ ...current, dateFrom: '', dateTo: '' })) }] : []),
    ...([['universityIds', 'ВУЗ', references.data?.universities ?? []], ['directionIds', 'Направление', references.data?.directions ?? []], ['productIds', 'Продукт', references.data?.products ?? []], ['responsibleIds', 'Ответственный', references.data?.responsibles ?? []]] as const)
      .filter(([key]) => filters[key].length)
      .map(([key, label, entries]) => ({ id: key, label: `${label}: ${filters[key].map((id) => entries.find((item) => item.id === id)?.name ?? id).join(', ')}`, onRemove: () => setFilters((current) => ({ ...current, [key]: [] })) })),
  ];
  const filterBar = <FilterToolbar activeFilters={activeFilters} label="Фильтры аналитики" collapsible controls={() => <>
        <DateRangeField presets from={filters.dateFrom} to={filters.dateTo} onFromChange={(dateFrom) => setFilters((current) => ({ ...current, dateFrom }))} onToChange={(dateTo) => setFilters((current) => ({ ...current, dateTo }))} onRangeChange={(dateFrom, dateTo) => setFilters((current) => ({ ...current, dateFrom, dateTo }))} />
        <MultiSelect label="ВУЗ" values={filters.universityIds} options={references.data?.universities ?? []} disabled={references.isPending || references.isError} onChange={(universityIds) => setFilters((current) => ({ ...current, universityIds }))} />
        <MultiSelect label="Направление" values={filters.directionIds} options={references.data?.directions ?? []} disabled={references.isPending || references.isError} onChange={(directionIds) => setFilters((current) => ({ ...current, directionIds }))} />
        <MultiSelect label="Продукт" values={filters.productIds} options={references.data?.products ?? []} disabled={references.isPending || references.isError} onChange={(productIds) => setFilters((current) => ({ ...current, productIds }))} />
        <MultiSelect label="Ответственный" values={filters.responsibleIds} options={references.data?.responsibles ?? []} disabled={references.isPending || references.isError} onChange={(responsibleIds) => setFilters((current) => ({ ...current, responsibleIds }))} />
      </>} onReset={() => setFilters(EMPTY_DASHBOARD_FILTERS)} resetDisabled={!filters.dateFrom && !filters.dateTo && !filters.universityIds.length && !filters.directionIds.length && !filters.productIds.length && !filters.responsibleIds.length} mobileCount={[filters.dateFrom, filters.dateTo, ...filters.universityIds, ...filters.directionIds, ...filters.productIds, ...filters.responsibleIds].filter(Boolean).length} />;

  const data = overviewQuery.data;

  return (
    <div className={styles.page}>
      <PageIntro title="Обзор" description="Ключевые показатели состояния образовательной сети и операционных задач команды." />
      {filterBar}
      {!data ? overviewQuery.isPending ? <PageSkeleton cardCount={9} variant="dashboard" /> : <RouteErrorState onRetry={() => void overviewQuery.refetch()} /> : <>
      <section className={styles.section} aria-labelledby="dashboard-kpi-title" data-testid="dashboard-kpi">
        <div className={styles.sectionHeader}><h2 className={styles.sectionTitle} id="dashboard-kpi-title">Ключевые показатели</h2><div className={styles.refreshStatus} aria-live="polite">{overviewQuery.isFetching ? <span role="status">Обновляем показатели…</span> : null}{overviewQuery.isError ? <BackgroundRefreshNotice onRetry={() => void overviewQuery.refetch()} /> : null}</div></div>
        <div className={styles.grid}>
          {kpiDefinitions.map((definition) => {
            const card = <KpiCard
                ariaLabel={definition.ariaLabel}
                caption={definition.caption}
                href={definition.href}
                icon={definition.icon}
                key={definition.title}
                title={definition.title}
                tone={definition.tone}
                value={definition.value(data.overview)}
              />;
            return definition.tooltip
              ? <div className={styles.kpiTooltip} key={definition.title}><Tooltip content={<span style={{ whiteSpace: 'pre-line' }}>{definition.tooltip(data.overview)}</span>}>{card}</Tooltip></div>
              : card;
          })}
        </div>
      </section>
      <DashboardAnalytics data={data.analytics} />
      </>}
    </div>
  );
}

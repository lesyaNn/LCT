'use client';

import Link from 'next/link';
import { useId, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts';
import {
  dashboardAnalyticsQueryKey,
  getDashboardAnalytics,
  type AttentionItem,
  type DashboardAnalytics,
  type HealthScoreDistributionItem,
  type LaunchDynamicsItem,
  type ProgramStatusItem,
} from '@/shared/lib/dashboard-repository';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { attentionSeverityIntent } from '@/shared/lib/status-semantics';
import styles from './dashboard-charts.module.css';

const numberFormatter = new Intl.NumberFormat('ru-RU');

const healthColors: Record<HealthScoreDistributionItem['tone'], string> = {
  danger: 'var(--rtk-color-danger)',
  warning: 'var(--rtk-color-warning)',
  brand: 'var(--rtk-color-brand)',
  success: 'var(--rtk-color-success)',
};

const statusColors: Record<ProgramStatusItem['tone'], string> = {
  neutral: 'var(--rtk-color-text-tertiary)',
  brand: 'var(--rtk-color-brand)',
  success: 'var(--rtk-color-success)',
  dark: 'var(--rtk-color-text-primary)',
};

const severityLabels: Record<AttentionItem['severity'], string> = {
  red: 'Критично',
  orange: 'Высокий приоритет',
  yellow: 'Требует внимания',
};

function formatCount(value: number) {
  return numberFormatter.format(value);
}

interface ChartCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}

function ChartCard({ title, description, children, action }: ChartCardProps) {
  const headingId = useId();

  return (
    <article className={styles.card} aria-labelledby={headingId}>
      <header className={styles.cardHeader}>
        <div>
          <h3 className={styles.cardTitle} id={headingId}>{title}</h3>
          {description ? <p className={styles.cardDescription}>{description}</p> : null}
        </div>
        {action}
      </header>
      <div className={styles.cardBody}>{children}</div>
    </article>
  );
}

function ChartSkeleton() {
  return (
    <div className={styles.skeletonCard} aria-hidden="true">
      <span className={styles.skeletonTitle} />
      <span className={styles.skeletonChart} />
    </div>
  );
}

function HealthTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as HealthScoreDistributionItem | undefined;
  if (!point) return null;

  return (
    <div className={styles.tooltip} role="status">
      <strong>{point.range}</strong>
      <span>{formatCount(point.count)} вузов</span>
    </div>
  );
}

function ProgramTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as (ProgramStatusItem & { percentage: number }) | undefined;
  if (!point) return null;

  return (
    <div className={styles.tooltip} role="status">
      <strong>{point.label}</strong>
      <span>{formatCount(point.count)} программ · {point.percentage}%</span>
    </div>
  );
}

function LaunchTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as LaunchDynamicsItem | undefined;
  if (!point) return null;

  return (
    <div className={styles.tooltip} role="status">
      <strong>{point.monthLabel}</strong>
      <span>Фактические: {formatCount(point.actual)}</span>
      <span>Планируемые: {formatCount(point.planned)}</span>
    </div>
  );
}

function HealthScoreChart({ data }: { data: DashboardAnalytics['healthScoreDistribution'] }) {
  return (
    <div className={styles.chartStack}>
      <div className={styles.chartCanvas} role="img" aria-label="Распределение вузов по диапазонам Health Score">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="range" tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} width={28} />
            <Tooltip content={HealthTooltip} cursor={{ fill: 'var(--rtk-color-surface-hover)' }} />
            <Bar dataKey="count" name="Количество вузов" radius={[6, 6, 0, 0]}>
              {data.map((item) => <Cell fill={healthColors[item.tone]} key={item.range} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className={styles.chartNote}>Значения показывают количество вузов в каждом диапазоне.</p>
    </div>
  );
}

function ProgramStatusChart({ data }: { data: DashboardAnalytics['programStatuses'] }) {
  const total = data.reduce((sum, item) => sum + item.count, 0);
  const dataWithPercent = data.map((item) => ({
    ...item,
    percentage: total === 0 ? 0 : Math.round((item.count / total) * 100),
  }));

  return (
    <div className={styles.donutLayout}>
      <div className={styles.donutCanvas} role="img" aria-label="Распределение программ по статусам">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={dataWithPercent}
              dataKey="count"
              nameKey="label"
              innerRadius="58%"
              outerRadius="78%"
              paddingAngle={2}
              stroke="var(--rtk-color-surface)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {dataWithPercent.map((item) => <Cell fill={statusColors[item.tone]} key={item.status} />)}
            </Pie>
            <Tooltip content={ProgramTooltip} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className={styles.legend} aria-label="Статусы программ">
        {dataWithPercent.map((item) => (
          <li className={styles.legendItem} key={item.status}>
            <span className={styles.legendLabel}>
              <span className={styles.legendDot} style={{ backgroundColor: statusColors[item.tone] }} aria-hidden="true" />
              {item.label}
            </span>
            <span className={styles.legendValue}>{formatCount(item.count)} <span className={styles.legendPercent}>({item.percentage}%)</span></span>
          </li>
        ))}
      </ul>
      <p className={styles.chartNote}>Фильтрация по статусу станет доступна после появления страницы программ.</p>
    </div>
  );
}

function LaunchDynamicsChart({ data }: { data: DashboardAnalytics['launchDynamics'] }) {
  return (
    <div className={styles.chartStack}>
      <div className={styles.chartCanvas} role="img" aria-label="Динамика фактических и планируемых запусков программ за 12 месяцев">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="monthLabel" tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} width={28} />
            <Tooltip content={LaunchTooltip} cursor={{ stroke: 'var(--rtk-color-border-strong)' }} />
            <Line type="monotone" dataKey="actual" name="Фактические запуски" stroke="var(--rtk-color-brand)" strokeWidth={3} dot={{ r: 3, fill: 'var(--rtk-color-brand)' }} activeDot={{ r: 5 }} isAnimationActive={false} />
            <Line type="monotone" dataKey="planned" name="Планируемые запуски" stroke="var(--rtk-color-success)" strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul className={styles.seriesLegend} aria-label="Серии динамики запусков">
        <li><span className={`${styles.seriesMarker} ${styles.seriesActual}`} aria-hidden="true" />Фактические запуски</li>
        <li><span className={`${styles.seriesMarker} ${styles.seriesPlanned}`} aria-hidden="true" />Планируемые запуски</li>
      </ul>
    </div>
  );
}

function AttentionList({ data }: { data: DashboardAnalytics['attentionItems'] }) {
  return (
    <ol className={styles.attentionList}>
      {data.slice(0, 5).map((item) => (
        <li key={item.id}>
          <Link className={styles.attentionItem} href={`/universities/${item.universityId}`}>
            <span className={styles.severity} aria-label={`Приоритет: ${severityLabels[item.severity]}`}><StatusBadge intent={attentionSeverityIntent[item.severity]}>{severityLabels[item.severity]}</StatusBadge></span>
            <strong className={styles.universityName}>{item.universityName}</strong>
            <span className={styles.problem}>{item.problemCode} · {item.problemLabel}</span>
            <span className={styles.overdue}>{formatCount(item.overdueDays)} дн. просрочки</span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

export function DashboardAnalytics() {
  const analyticsQuery = useQuery({
    queryKey: dashboardAnalyticsQueryKey,
    queryFn: getDashboardAnalytics,
    staleTime: 30_000,
  });

  return (
    <section className={styles.section} aria-labelledby="dashboard-analytics-title">
      <div>
        <h2 className={styles.sectionTitle} id="dashboard-analytics-title">Аналитика</h2>
        <p className={styles.sectionDescription}>Сводка по состоянию вузов, программ и задач, требующих внимания.</p>
      </div>
      {analyticsQuery.isPending ? (
        <div className={styles.grid} aria-live="polite" aria-busy="true">
          {Array.from({ length: 4 }, (_, index) => <ChartSkeleton key={index} />)}
        </div>
      ) : analyticsQuery.isError || !analyticsQuery.data ? (
        <RouteErrorState onRetry={() => void analyticsQuery.refetch()} />
      ) : (
        <AnalyticsGrid data={analyticsQuery.data} />
      )}
    </section>
  );
}

function AnalyticsGrid({ data }: { data: DashboardAnalytics }) {
  return (
    <div className={styles.grid}>
      <ChartCard title="Распределение Health Score" description="Количество вузов по диапазонам показателя.">
        {data.healthScoreDistribution.length ? <HealthScoreChart data={data.healthScoreDistribution} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Программы по статусам" description="Текущее распределение программ в реестре.">
        {data.programStatuses.length ? <ProgramStatusChart data={data.programStatuses} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Динамика запусков" description="Фактические и планируемые запуски за последние 12 месяцев.">
        {data.launchDynamics.length ? <LaunchDynamicsChart data={data.launchDynamics} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Top Attention Items" description="Пять элементов, требующих первоочередного внимания.">
        {data.attentionItems.length ? <AttentionList data={data.attentionItems} /> : <EmptyChart />}
      </ChartCard>
    </div>
  );
}

function EmptyChart() {
  return <p className={styles.emptyState}>Нет данных для отображения</p>;
}

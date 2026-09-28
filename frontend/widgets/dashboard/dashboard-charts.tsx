'use client';

import Link from 'next/link';
import { useId, useRef, type ReactNode } from 'react';
import {
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
  type AttentionItem,
  type DashboardAnalytics,
  type LaunchDynamicsItem,
  type ProgramStatusItem,
} from '@/shared/lib/dashboard-repository';
import { EmptyState } from '@/shared/ui/empty-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { ChartExportMenu } from '@/shared/ui/chart-export-menu';
import { attentionSeverityIntent } from '@/shared/lib/status-semantics';
import styles from './dashboard-charts.module.css';

const numberFormatter = new Intl.NumberFormat('ru-RU');

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
  exportSlug: string;
  exportTestId: string;
  canExport: boolean;
}

function ChartCard({ title, description, children, exportSlug, exportTestId, canExport }: ChartCardProps) {
  const headingId = useId();
  const cardRef = useRef<HTMLElement>(null);

  return (
    <article className={styles.card} aria-labelledby={headingId} ref={cardRef}>
      <header className={styles.cardHeader}>
        <div>
          <h3 className={styles.cardTitle} id={headingId}>{title}</h3>
          {description ? <p className={styles.cardDescription}>{description}</p> : null}
        </div>
        {canExport ? <ChartExportMenu filenameSlug={exportSlug} targetRef={cardRef} testId={exportTestId} /> : null}
      </header>
      <div className={styles.cardBody}>{children}</div>
    </article>
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
    </div>
  );
}

function LaunchDynamicsChart({ data }: { data: DashboardAnalytics['launchDynamics'] }) {
  return (
    <div className={styles.chartStack}>
      <div className={styles.chartCanvas} role="img" aria-label="Динамика фактических и планируемых запусков программ за 12 месяцев">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="monthLabel" tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} interval={1} minTickGap={12} tickMargin={8} />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
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

export function DashboardAnalytics({ data }: { data: DashboardAnalytics }) {
  return (
    <section className={styles.section} aria-labelledby="dashboard-analytics-title">
      <div>
        <h2 className={styles.sectionTitle} id="dashboard-analytics-title">Аналитика</h2>
        <p className={styles.sectionDescription}>Сводка по состоянию вузов, программ и задач, требующих внимания.</p>
      </div>
      <AnalyticsGrid data={data} />
    </section>
  );
}

function AnalyticsGrid({ data }: { data: DashboardAnalytics }) {
  const programStatuses = data.programStatuses.filter((item) => item.count > 0);
  const hasLaunches = data.launchDynamics.some((item) => item.actual > 0 || item.planned > 0);
  return (
    <div className={styles.grid}>
      <ChartCard title="Программы по статусам" description="Текущее распределение программ в реестре." exportSlug="programs" exportTestId="chart-export-programs" canExport={programStatuses.length > 0}>
        {programStatuses.length ? <ProgramStatusChart data={programStatuses} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Динамика запусков" description="Фактические и планируемые запуски за последние 12 месяцев." exportSlug="dynamics" exportTestId="chart-export-dynamics" canExport={hasLaunches}>
        {hasLaunches ? <LaunchDynamicsChart data={data.launchDynamics} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Приоритетные задачи" description="Пять элементов, требующих первоочередного внимания." exportSlug="attention" exportTestId="chart-export-attention" canExport={data.attentionItems.length > 0}>
        {data.attentionItems.length ? <AttentionList data={data.attentionItems} /> : <EmptyChart />}
      </ChartCard>
    </div>
  );
}

function EmptyChart() {
  return <EmptyState title="Нет данных для выбранных условий" headingLevel={3} />;
}

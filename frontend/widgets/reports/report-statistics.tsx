'use client';

import { useId, useRef, type ReactNode } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartExportMenu } from '@/shared/ui/chart-export-menu';
import { EmptyState } from '@/shared/ui/empty-state';
import {
  type ReportStatSlice,
  type ReportStatistics,
} from '@/shared/lib/reports-repository';
import styles from './reports-page.module.css';

const numberFormatter = new Intl.NumberFormat('ru-RU');
const formatCount = (value: number) => numberFormatter.format(value);
const segmentColors = ['var(--rtk-color-brand)', 'var(--rtk-color-brand-secondary)', 'var(--rtk-color-success)', 'var(--rtk-color-border-strong)'];

interface ChartCardProps {
  title: string;
  exportSlug: string;
  exportTestId: string;
  children: ReactNode;
}

function ChartCard({ title, exportSlug, exportTestId, children }: ChartCardProps) {
  const headingId = useId();
  const cardRef = useRef<HTMLElement>(null);
  return (
    <article className={styles.statCard} aria-labelledby={headingId} ref={cardRef}>
      <header className={styles.statCardHeader}>
        <div>
          <h4 id={headingId}>{title}</h4>
        </div>
        <ChartExportMenu filenameSlug={exportSlug} targetRef={cardRef} testId={exportTestId} />
      </header>
      <div className={styles.statCardBody}>{children}</div>
    </article>
  );
}

interface BucketTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: { label?: string; count?: number } }>;
  unit: ReportStatSlice['unit'];
}

function BucketTooltip({ active, payload, unit }: BucketTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload?.[0]?.payload;
  if (!point || typeof point.label !== 'string' || typeof point.count !== 'number') return null;
  return (
    <div className={styles.statTooltip} role="status">
      <strong>{point.label}</strong>
      <span>
        {formatCount(point.count)} {unit === 'universities' ? 'вузов' : 'строк'}
      </span>
    </div>
  );
}

/**
 * One bar chart per dimension.
 *
 * The bar length is the count and the axis starts at zero, so a bucket can
 * never be visually inflated. Long lists scroll inside a fixed-height card.
 */
function StatBarChart({ slice }: { slice: ReportStatSlice }) {
  if (!slice.buckets.length) return <EmptyState title="Нет данных для выбранных условий" headingLevel={3} />;
  const unitWord = slice.unit === 'universities' ? 'вузов' : 'строк';
  const data = slice.buckets;
  return (
    <>
      <div className={styles.statChartViewport} data-chart-scroll role="region" aria-label={`Категории графика «${slice.title}»`} tabIndex={0}>
        <div className={styles.statChart} style={{ height: Math.max(180, data.length * 38 + 24) }} role="img" aria-label={`${slice.title}. Всего: ${formatCount(slice.total)} ${unitWord}.`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" width={110} tickFormatter={(value: string) => value.length > 15 ? `${value.slice(0, 14)}…` : value} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} interval={0} />
              <Tooltip content={<BucketTooltip unit={slice.unit} />} cursor={{ fill: 'var(--rtk-color-surface-hover)' }} position={{ x: 8, y: 8 }} />
              <Bar dataKey="count" fill="var(--rtk-color-brand)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <p className={styles.statCaption}><span className={styles.statLegendDot} aria-hidden="true" />Количество {unitWord} · всего {formatCount(slice.total)}</p>
    </>
  );
}

function StatDonutChart({ slice }: { slice: ReportStatSlice }) {
  const unitWord = slice.unit === 'universities' ? 'вузов' : 'строк';
  return <div className={styles.statDonutLayout}>
    <div className={styles.statDonut} role="img" aria-label={`${slice.title}. Всего ${formatCount(slice.total)} ${unitWord}.`}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart><Pie data={slice.buckets} dataKey="count" nameKey="label" innerRadius="58%" outerRadius="82%" paddingAngle={2} stroke="none" isAnimationActive={false}>
          {slice.buckets.map((bucket, index) => <Cell key={bucket.label} fill={segmentColors[index % segmentColors.length]} />)}
        </Pie><Tooltip content={<BucketTooltip unit={slice.unit} />} /></PieChart>
      </ResponsiveContainer>
      <span className={styles.statDonutTotal}><strong>{formatCount(slice.total)}</strong><small>{unitWord}</small></span>
    </div>
    <ul className={styles.statDonutLegend}>{slice.buckets.map((bucket, index) => <li key={bucket.label}><span style={{ background: segmentColors[index % segmentColors.length] }} aria-hidden="true" /><span>{bucket.label}</span><strong>{formatCount(bucket.count)}</strong></li>)}</ul>
  </div>;
}

interface ReportStatisticsPanelProps {
  statistics?: ReportStatistics;
  pending: boolean;
  error: unknown;
  onRetry: () => void;
}

/** Only dimensions selected for export, and only at a compatible row grain. */
export function ReportStatisticsPanel({ statistics, pending, error, onRetry }: ReportStatisticsPanelProps) {
  if (error) {
    return (
      <EmptyState
        title="Не удалось получить статистику"
        description="Повторите запрос или уточните параметры выборки."
        headingLevel={3}
        primaryAction={{ label: 'Повторить', onClick: onRetry }}
      />
    );
  }
  if (pending && !statistics) return <p className={styles.statEmpty}>Считаем статистику…</p>;
  if (!statistics) return null;
  const slices = statistics.groups.filter((slice) => slice.buckets.length);
  if (!slices.length) {
    if (statistics.universityCount > 0) return <p className={styles.statEmpty}>В выбранном составе нет данных для распределений.</p>;
    return <EmptyState title="Нет данных для выбранных условий" headingLevel={3} />;
  }

  return (
    <div className={styles.statSurface} aria-label="Графики по выбранной выборке">
      <div className={styles.statGrid}>
        {slices.map((slice) => (
            <ChartCard
              key={slice.dimension}
              title={slice.title}
              exportSlug={slice.dimension}
              exportTestId={`chart-export-${slice.dimension}`}
            >
              {slice.dimension === 'by_workflow_status' ? <StatDonutChart slice={slice} /> : <StatBarChart slice={slice} />}
            </ChartCard>
          ))}
      </div>
      {pending ? <span className={styles.previewRefreshing}>Обновляем…</span> : null}
    </div>
  );
}

'use client';

import Link from 'next/link';
import { useId, useRef, type ReactNode } from 'react';
import {
  CartesianGrid,
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Legend,
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
  type DashboardMatrix,
  type MatrixHealthState,
  type MonthlyEventItem,
  type StageFunnelItem,
} from '@/shared/lib/dashboard-repository';
import { EmptyState } from '@/shared/ui/empty-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip as RtkTooltip } from '@/shared/ui/rtk/tooltip';
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

function StageFunnelTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as StageFunnelItem | undefined;
  if (!point) return null;
  return <div className={styles.tooltip}><strong>{point.stage}</strong>{point.template ? <span>{point.template}</span> : null}<span>Дошло до этапа или дальше: {formatCount(point.reached)}</span><span>Сейчас на этапе: {formatCount(point.current)}</span><span>Завершили этап: {formatCount(point.completed)}</span></div>;
}

function StageFunnelChart({ data }: { data: DashboardAnalytics['stageFunnel'] }) {
  return <div className={styles.funnelCanvas} role="img" aria-label="Воронка этапов Workflow"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, bottom: 4, left: 8 }}><CartesianGrid stroke="var(--rtk-color-border)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} /><YAxis dataKey="stage" type="category" width={250} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(value: string) => value.length > 38 ? `${value.slice(0, 38)}…` : value} interval={0} /><Tooltip content={StageFunnelTooltip} cursor={{ fill: 'var(--rtk-color-surface-hover)' }} /><Bar dataKey="reached" name="Дошли до этапа или дальше" fill="var(--rtk-color-brand-secondary)" radius={[0, 4, 4, 0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>;
}

function MonthlyEventsTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as MonthlyEventItem | undefined;
  return point ? <div className={styles.tooltip}><strong>{point.monthLabel}</strong><span>Событий: {formatCount(point.count)}</span><span>Смены статусов: {formatCount(point.statusChanges)}</span><span>Завершено: {formatCount(point.completed)}</span></div> : null;
}

function MonthlyEventsChart({ data }: { data: DashboardAnalytics['monthlyEvents'] }) {
  return <div className={styles.chartCanvas} role="img" aria-label="Динамика событий, смен статусов и завершений по месяцам"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}><CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="monthLabel" tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} /><YAxis allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} width={36} /><Tooltip content={MonthlyEventsTooltip} cursor={{ stroke: 'var(--rtk-color-border-strong)' }} /><Legend /><Line type="monotone" dataKey="count" name="События" stroke="var(--rtk-color-brand)" strokeWidth={3} dot={{ r: 3, fill: 'var(--rtk-color-brand)' }} activeDot={{ r: 5 }} isAnimationActive={false} /><Line type="monotone" dataKey="statusChanges" name="Смены статусов" stroke="var(--rtk-color-brand-secondary)" strokeWidth={2} dot={{ r: 3, fill: 'var(--rtk-color-brand-secondary)' }} activeDot={{ r: 5 }} isAnimationActive={false} /><Line type="monotone" dataKey="completed" name="Завершено" stroke="var(--rtk-color-success)" strokeWidth={2} dot={{ r: 3, fill: 'var(--rtk-color-success)' }} activeDot={{ r: 5 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>;
}

function TopUniversitiesChart({ data }: { data: DashboardAnalytics['topUniversities'] }) {
  return <div className={styles.topUniversitiesCanvas} role="img" aria-label="Топ-10 ВУЗов по числу взаимодействий"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, bottom: 4, left: 8 }}><CartesianGrid stroke="var(--rtk-color-border)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} /><YAxis dataKey="university" type="category" width={190} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} tickFormatter={(value: string) => value.length > 27 ? `${value.slice(0, 27)}…` : value} interval={0} /><Tooltip formatter={(value) => [formatCount(Number(value)), 'Взаимодействия']} /><Bar dataKey="count" fill="var(--rtk-color-brand-secondary)" radius={[0, 4, 4, 0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>;
}

function ResponsibleWorkloadChart({ data }: { data: DashboardAnalytics['responsibleWorkload'] }) {
  return <div className={styles.workloadCanvas} role="img" aria-label="Нагрузка по ответственным"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ top: 4, right: 8, bottom: 4, left: 8 }}><CartesianGrid stroke="var(--rtk-color-border)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} /><YAxis dataKey="responsible" type="category" width={150} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} interval={0} /><Tooltip formatter={(value, name) => [formatCount(Number(value)), name === 'inProgress' ? 'В работе' : 'Завершено']} /><Legend formatter={(value) => value === 'inProgress' ? 'В работе' : 'Завершено'} /><Bar dataKey="inProgress" name="inProgress" stackId="workload" fill="var(--rtk-color-brand)" radius={[4, 0, 0, 4]} isAnimationActive={false} /><Bar dataKey="completed" name="completed" stackId="workload" fill="var(--rtk-color-success)" radius={[0, 4, 4, 0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>;
}


const matrixStateLabel: Record<MatrixHealthState, string> = {
  HEALTHY: 'Стабильно', ATTENTION: 'Требует внимания', CRITICAL: 'Критично',
  NOT_STARTED: 'Не запущено', COMPLETED: 'Завершено', NOT_LINKED: 'Не используется',
};
const matrixStateMark: Record<MatrixHealthState, string> = {
  HEALTHY: '●', ATTENTION: '!', CRITICAL: '!', NOT_STARTED: '○', COMPLETED: '✓', NOT_LINKED: '—',
};

function MatrixCellContent({ state, score }: { state: MatrixHealthState; score: number | null }) {
  return <span className={`${styles.matrixCell} ${styles[`matrix${state}`]}`}>
    <span aria-hidden="true" className={styles.matrixMark}>{matrixStateMark[state]}</span>
    <span className={styles.matrixCellText}>{state === 'HEALTHY' || state === 'ATTENTION' || state === 'CRITICAL' ? <><strong>{score ?? '—'}</strong><small>{matrixStateLabel[state]}</small></> : matrixStateLabel[state]}</span>
  </span>;
}

function UniversityProgramMatrix({ matrix }: { matrix: DashboardMatrix }) {
  const byCell = new Map(matrix.cells.map((cell) => [`${cell.universityId}:${cell.programId}`, cell]));
  const counts = matrix.rows.reduce((acc, row) => { if (row.level === 'stable') acc.stable += 1; else if (row.level === 'attention') acc.attention += 1; else if (row.level === 'critical') acc.critical += 1; return acc; }, { stable: 0, attention: 0, critical: 0 });
  if (!matrix.rows.length || !matrix.columns.length) return <EmptyChart />;
  return <div className={styles.matrixWrap}>
    <div className={styles.matrixSummary}>Стабильно: {counts.stable} · Требуют внимания: {counts.attention} · Критично: {counts.critical}</div>
    <div className={styles.matrixScroll}><table className={styles.matrix}><thead><tr><th>ВУЗ</th>{matrix.columns.map((column) => <th key={column.id} title={column.direction}>{column.name}</th>)}</tr></thead><tbody>{matrix.rows.map((row) => <tr key={row.id}><th scope="row"><Link href={`/universities/${row.id}`}>{row.name}</Link><small>{row.score === null ? 'Недостаточно данных' : `Health ${row.score} · ${row.startedPrograms} из ${row.totalPrograms} запущено`}</small></th>{matrix.columns.map((column) => {
      const cell = byCell.get(`${row.id}:${column.id}`);
      if (!cell) return <td key={column.id}>—</td>;
      const label = `${row.name}, ${column.name}: ${matrixStateLabel[cell.state]}${cell.score === null || cell.state === 'COMPLETED' ? '' : `, Health ${cell.score}`}`;
      const details = <span className={styles.matrixTooltip}><strong>{row.name} · {column.name}</strong><span>Статус: {matrixStateLabel[cell.state]}</span>{cell.state === 'COMPLETED' ? <span>Workflow завершён.</span> : cell.state === 'NOT_STARTED' ? <span>Workflow ещё не запущен.</span> : cell.state === 'NOT_LINKED' ? <span>Программа не связана с ВУЗом.</span> : <>{cell.score !== null ? <span>Health Score: {cell.score}</span> : null}{cell.milestone ? <span>Текущий этап: {cell.milestone}</span> : null}{cell.factors.length ? <span>Причины: {cell.factors.join('; ')}</span> : null}</>}</span>;
      const content = <MatrixCellContent state={cell.state} score={cell.score} />;
      const href = cell.workflowInstanceId ? `/workflows/${cell.workflowInstanceId}` : `/universities/${row.id}?tab=workflow&program=${column.id}`;
      return <td key={column.id}><RtkTooltip content={details}>{cell.state === 'NOT_LINKED' ? <span aria-label={label}>{content}</span> : <Link href={href} aria-label={label}>{content}</Link>}</RtkTooltip></td>;
    })}</tr>)}</tbody></table></div>
    <div className={styles.matrixLegend} aria-label="Легенда матрицы">{(['COMPLETED', 'HEALTHY', 'ATTENTION', 'CRITICAL', 'NOT_STARTED', 'NOT_LINKED'] as MatrixHealthState[]).map((state) => <span key={state} className={styles.matrixLegendItem}><span className={`${styles.matrixDot} ${styles[`matrix${state}`]}`}>{matrixStateMark[state]}</span>{matrixStateLabel[state]}</span>)}</div>
  </div>;
}

function AttentionList({ data }: { data: DashboardAnalytics['attentionItems'] }) {
  return (
    <ol className={styles.attentionList} tabIndex={0} aria-label="Приоритетные задачи">
      {data.map((item) => (
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
      <div className={styles.funnelWide}><ChartCard title="Воронка этапов" description="Сколько взаимодействий дошли до этапа или дальше. За всё время." exportSlug="stage-funnel" exportTestId="chart-export-stage-funnel" canExport={data.stageFunnel.length > 0}>
        {data.stageFunnel.length ? <StageFunnelChart data={data.stageFunnel} /> : <EmptyChart />}
      </ChartCard></div>
      <div className={styles.priorityPanel}><ChartCard title="Приоритетные задачи" description="Элементы, требующие первоочередного внимания." exportSlug="attention" exportTestId="chart-export-attention" canExport={data.attentionItems.length > 0}>
        {data.attentionItems.length ? <AttentionList data={data.attentionItems} /> : <EmptyChart />}
      </ChartCard></div>
      <ChartCard title="Динамика запусков" description="Фактические и планируемые запуски за последние 12 месяцев." exportSlug="dynamics" exportTestId="chart-export-dynamics" canExport={hasLaunches}>
        {hasLaunches ? <LaunchDynamicsChart data={data.launchDynamics} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Динамика по месяцам" description="События, смены этапов и завершённые Workflow за месяц. За всё время." exportSlug="monthly-events" exportTestId="chart-export-monthly-events" canExport={data.monthlyEvents.length > 0}>
        {data.monthlyEvents.length ? <MonthlyEventsChart data={data.monthlyEvents} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Топ-10 ВУЗов по числу взаимодействий" description="Встречи и заметки, сохранённые в CRM." exportSlug="top-universities" exportTestId="chart-export-top-universities" canExport={data.topUniversities.length > 0}>
        {data.topUniversities.length ? <TopUniversitiesChart data={data.topUniversities} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Нагрузка по ответственным" description="Workflow, назначенные ответственному: в работе и завершённые." exportSlug="responsible-workload" exportTestId="chart-export-responsible-workload" canExport={data.responsibleWorkload.length > 0}>
        {data.responsibleWorkload.length ? <ResponsibleWorkloadChart data={data.responsibleWorkload} /> : <EmptyChart />}
      </ChartCard>
      <ChartCard title="Программы по статусам" description="Текущее распределение программ в реестре." exportSlug="programs" exportTestId="chart-export-programs" canExport={programStatuses.length > 0}>
        {programStatuses.length ? <ProgramStatusChart data={programStatuses} /> : <EmptyChart />}
      </ChartCard>
      <div className={styles.attentionWide}><ChartCard title="ВУЗы × программы" description="Состояние взаимодействий по доступным программам." exportSlug="university-program-matrix" exportTestId="chart-export-matrix" canExport={data.matrix.rows.length > 0 && data.matrix.columns.length > 0}><UniversityProgramMatrix matrix={data.matrix} /></ChartCard></div>
    </div>
  );
}

function EmptyChart() {
  return <EmptyState title="Нет данных для выбранных условий" headingLevel={3} />;
}

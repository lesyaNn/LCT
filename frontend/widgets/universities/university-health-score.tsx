'use client';

import { useRef, useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts';
import Attention from '@atomaro/icons/24/action/Attention';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import ArrowDown from '@atomaro/icons/24/navigation/ArrowDown';
import ArrowUp from '@atomaro/icons/24/navigation/ArrowUp';
import {
  getUniversityHealthScore,
  universityHealthScoreQueryKey,
  type HealthScoreReasonSeverity,
  type UniversityHealthScore,
  type UniversityHealthScoreBreakdown,
  type UniversityHealthScoreHistoryPoint,
  type UniversityHealthScoreReason,
} from '@/shared/lib/universities-repository';
import { getHealthStatus, healthStatusMeta, type HealthStatus } from '@/shared/lib/health-score';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import { ChartExportMenu } from '@/shared/ui/chart-export-menu';
import styles from './university-health-score.module.css';

const statusDescriptions: Record<HealthStatus, string> = {
  green: 'Стабильное состояние',
  yellow: 'Требует внимания',
  red: 'Критическое состояние',
};

const severityLabels: Record<HealthScoreReasonSeverity, string> = {
  high: 'Высокий приоритет',
  medium: 'Средний приоритет',
  low: 'Низкий приоритет',
};

function formatHistoryDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short' }).format(new Date(`${value}T12:00:00`)).replace('.', '');
}

function formatLongDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(new Date(`${value}T12:00:00`));
}

function ScoreRing({ score, status }: { score: number; status: HealthStatus }) {
  const radius = 72;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.max(0, Math.min(100, score)) / 100) * circumference;
  const ringStyle = { '--score-ring-offset': `${offset}` } as CSSProperties;

  return (
    <div className={styles.scoreRingWrap}>
      <svg className={styles.scoreRing} viewBox="0 0 180 180" role="img" aria-label={`Health Score ${score} из 100`} style={ringStyle}>
        <circle className={styles.scoreRingTrack} cx="90" cy="90" r={radius} />
        <circle className={`${styles.scoreRingProgress} ${styles[`ring-${status}`]}`} cx="90" cy="90" r={radius} />
      </svg>
      <div className={styles.scoreRingValue}><strong>{score}</strong><span>из 100</span></div>
    </div>
  );
}

function HealthScoreHero({ data }: { data: UniversityHealthScore }) {
  const status = data.status;
  const delta = data.previousSnapshot ? data.currentScore - data.previousSnapshot.score : 0;
  const DeltaIcon = delta > 0 ? ArrowUp : delta < 0 ? ArrowDown : StatisticsBoard;
  const deltaTone = delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral';
  const deltaText = delta > 0 ? `+${delta}` : String(delta);

  return (
    <section className={styles.hero} aria-label="Текущая оценка состояния">
      <div className={styles.heroCopy}>
        <p className={styles.eyebrow}>ОЦЕНКА СОСТОЯНИЯ</p>
        <div className={styles.heroStatus}><span className={`${styles.statusDot} ${styles[`dot-${status}`]}`} aria-hidden="true" /><strong>{statusDescriptions[status]}</strong><span className={styles.statusLabel}>{healthStatusMeta[status].label}</span></div>
        {data.previousSnapshot ? <div className={`${styles.delta} ${styles[`delta-${deltaTone}`]}`}><DeltaIcon size={16} fill="currentColor" /><span>Изменение за неделю: <strong>{deltaText}</strong></span><small>с {formatLongDate(data.previousSnapshot.date)}</small></div> : null}
      </div>
      <ScoreRing score={data.currentScore} status={status} />
    </section>
  );
}

function BreakdownRow({ item }: { item: UniversityHealthScoreBreakdown }) {
  const status = getHealthStatus(item.score);
  return (
    <li className={styles.breakdownRow}>
      <div className={styles.breakdownHeader}><span className={styles.breakdownName}>{item.label}</span><span className={styles.breakdownWeight}>Вес {item.weight}%</span><strong>{item.score}</strong></div>
      <div className={styles.breakdownTrack} role="progressbar" aria-label={`${item.label}: ${item.score} из 100`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.score}><span className={styles[`bar-${status}`]} style={{ width: `${item.score}%` }} /></div>
      <div className={styles.breakdownCounters}>{item.inputCounters.map((counter) => <span key={counter.label}>{counter.label}: <strong>{counter.value}</strong></span>)}</div>
    </li>
  );
}

function Breakdown({ data }: { data: UniversityHealthScoreBreakdown[] }) {
  return (
    <section className={styles.section} aria-labelledby="health-score-breakdown-title">
      <div className={styles.sectionHeading}><h2 id="health-score-breakdown-title">Состав оценки</h2></div>
      {data.length ? <ul className={styles.breakdownList}>{data.map((item) => <BreakdownRow item={item} key={item.id} />)}</ul> : <EmptyState title="Нет данных для разбивки оценки" description="Состав оценки появится после расчёта показателей." headingLevel={3} />}
    </section>
  );
}

function ReasonIcon({ severity }: { severity: HealthScoreReasonSeverity }) {
  if (severity === 'high') return <Attention size={18} fill="currentColor" />;
  if (severity === 'medium') return <TimeStroke size={18} fill="currentColor" />;
  return <CheckLarge size={18} fill="currentColor" />;
}

function ReasonRow({ reason }: { reason: UniversityHealthScoreReason }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = Boolean(reason.details || reason.inputCounters?.length);
  return (
    <li className={styles.reasonRow}>
      <span className={`${styles.reasonIcon} ${styles[`reason-${reason.severity}`]}`} aria-hidden="true"><ReasonIcon severity={reason.severity} /></span>
      <div className={styles.reasonBody}><div className={styles.reasonTitleLine}><strong>{reason.title}</strong><span className={`${styles.severityBadge} ${styles[`severity-${reason.severity}`]}`}>{severityLabels[reason.severity]}</span></div><p>{reason.description}</p>{hasDetails ? <Button variant="ghost" size="s" type="button" className={styles.detailsButton} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Скрыть детали' : 'Раскрыть детали'}</Button> : null}{expanded ? <div className={styles.reasonDetails}>{reason.details ? <p>{reason.details}</p> : null}{reason.inputCounters?.length ? <dl>{reason.inputCounters.map((counter) => <div key={counter.label}><dt>{counter.label}</dt><dd>{counter.value}</dd></div>)}</dl> : null}</div> : null}</div>
    </li>
  );
}

function Reasons({ reasons }: { reasons: UniversityHealthScoreReason[] }) {
  return (
    <section className={styles.section} aria-labelledby="health-score-reasons-title">
      <div className={styles.sectionHeading}><h2 id="health-score-reasons-title">Причины</h2></div>
      {reasons.length ? <ul className={styles.reasonsList}>{reasons.map((reason) => <ReasonRow reason={reason} key={reason.id} />)}</ul> : <EmptyState icon={<CheckLarge size={18} fill="currentColor" />} title="Критичных факторов не обнаружено" description="Новых причин для внимания сейчас нет." headingLevel={3} />}
    </section>
  );
}

function HistoryTooltip({ active, payload }: TooltipContentProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload as UniversityHealthScoreHistoryPoint | undefined;
  if (!point) return null;
  return <div className={styles.tooltip} role="status"><strong>{formatLongDate(point.date)}</strong><span>Health Score: {point.score}</span></div>;
}

function History({ history, unavailable, onRetry }: { history: UniversityHealthScoreHistoryPoint[]; unavailable?: boolean; onRetry: () => void }) {
  const sectionRef = useRef<HTMLElement>(null);
  return (
    <section className={styles.section} aria-labelledby="health-score-history-title" ref={sectionRef}>
      <div className={styles.sectionHeading}><h2 id="health-score-history-title">Динамика за 30 дней</h2><ChartExportMenu filenameSlug="health-score-dynamics" targetRef={sectionRef} testId="chart-export-health-score-dynamics" /></div>
      {unavailable ? <RouteErrorState compact title="Не удалось загрузить динамику" onRetry={onRetry} /> : history.length ? <div className={styles.historyChart} role="img" aria-label="Динамика Health Score за последние 30 дней"><ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={230}><LineChart data={history} margin={{ top: 12, right: 12, bottom: 4, left: 4 }}><CartesianGrid stroke="var(--rtk-color-border)" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tickFormatter={formatHistoryDate} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} interval="preserveStartEnd" /><YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} width={34} /><Tooltip content={HistoryTooltip} cursor={{ stroke: 'var(--rtk-color-border-strong)' }} /><Line type="monotone" dataKey="score" name="Health Score" stroke="var(--health-score-line)" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} /></LineChart></ResponsiveContainer></div> : <EmptyState icon={<StatisticsBoard size={20} fill="currentColor" />} title="Нет данных о динамике" description="График появится после накопления истории." headingLevel={3} />}
      {history.length ? <div className={styles.historyLegend}><span className={styles.historyLegendLine} aria-hidden="true" />Health Score</div> : null}
    </section>
  );
}

function HealthScoreSkeleton() {
  return <SkeletonGroup label="Загрузка Health Score"><Skeleton height={240} /><Skeleton height={280} /><Skeleton height={240} /><Skeleton height={320} /></SkeletonGroup>;
}

export function UniversityHealthScore({ id }: { id: string }) {
  const query = useQuery({ queryKey: universityHealthScoreQueryKey(id), queryFn: ({ signal }) => getUniversityHealthScore(id, signal), staleTime: 30_000 });
  if (query.isPending) return <HealthScoreSkeleton />;
  if (query.isError || !query.data) return <RouteErrorState compact onRetry={() => void query.refetch()} />;

  const data = query.data;
  const status = data.status;
  return <div className={`${styles.page} ${styles[`theme-${status}`]}`}><HealthScoreHero data={data} /><Breakdown data={data.breakdown} /><Reasons reasons={data.reasons} /><History history={data.history} unavailable={data.historyUnavailable} onRetry={() => void query.refetch()} /></div>;
}

'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import Checklist from '@atomaro/icons/24/action/Checklist';
import Attention from '@atomaro/icons/24/action/Attention';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import CheckSmall from '@atomaro/icons/24/navigation/CheckSmall';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { getUniversityHealth, type MatrixHealthState, type UniversityHealthProgram } from '@/shared/lib/dashboard-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton } from '@/shared/ui/skeleton';
import styles from './university-health.module.css';

const stateLabel: Record<MatrixHealthState, string> = {
  HEALTHY: 'Стабильно', ATTENTION: 'Требует внимания', CRITICAL: 'Критично',
  NOT_STARTED: 'Не запущено', COMPLETED: 'Завершён', NOT_LINKED: 'Не используется',
};
const stateMark: Record<MatrixHealthState, string> = {
  HEALTHY: '●', ATTENTION: '!', CRITICAL: '!', NOT_STARTED: '○', COMPLETED: '✓', NOT_LINKED: '—',
};
const levelLabel = { stable: 'Стабильно', attention: 'Требует внимания', critical: 'Критично', no_data: 'Недостаточно данных' } as const;

function formatDate(value: string | null) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

function ProgressBar({ value }: { value: number | null }) {
  const width = Math.max(0, Math.min(100, value ?? 0));
  return <span className={styles.progressTrack} aria-hidden="true"><span style={{ width: `${width}%` }} /></span>;
}

function MetricIcon({ tone, children }: { tone: 'brand' | 'warning' | 'danger'; children: ReactNode }) {
  return <span className={`${styles.metricIcon} ${styles[`metricIcon${tone}`]}`}>{children}</span>;
}

function HealthHistory({ history }: { history: Array<{ date: string; score: number; level?: string }> }) {
  const [period, setPeriod] = useState<6 | 12 | 24>(6);
  const points = useMemo(() => history.slice(-period), [history, period]);
  const chartPoints = points.map((point, index) => {
    const x = points.length === 1 ? 320 : 24 + index * (592 / (points.length - 1));
    const y = 188 - (Math.max(0, Math.min(100, point.score)) / 100) * 150;
    return { ...point, x, y };
  });
  const line = chartPoints.map((point) => `${point.x},${point.y}`).join(' ');
  const area = chartPoints.length ? `24,188 ${line} ${chartPoints.at(-1)?.x ?? 24},188` : '';

  return <div className={styles.historyBlock}>
    <div className={styles.historyHeader}><h2>Динамика Health Score <span className={styles.info} title="История рассчитанных значений Health Score">i</span></h2><div className={styles.periods} role="group" aria-label="Период истории">{([6, 12, 24] as const).map((item) => <button className={period === item ? styles.periodActive : styles.period} key={item} type="button" onClick={() => setPeriod(item)}>{item} мес.</button>)}</div></div>
    {points.length < 2 ? <p className={styles.historyEmpty}>Динамика появится после накопления истории Health Score.</p> : <div className={styles.lineChart} role="img" aria-label="График динамики Health Score"><div className={styles.yAxis}><span>100</span><span>75</span><span>50</span><span>25</span><span>0</span></div><svg viewBox="0 0 640 220" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="health-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="currentColor" stopOpacity=".18" /><stop offset="100%" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>{[38, 75, 113, 150, 188].map((y) => <line className={styles.gridLine} key={y} x1="24" x2="616" y1={y} y2={y} />)}<polygon className={styles.area} points={area} /><polyline className={styles.chartLine} fill="none" points={line} />{chartPoints.map((point) => <circle className={styles.chartPoint} cx={point.x} cy={point.y} key={`${point.date}-${point.x}`} r="4"><title>{`${formatDate(point.date)}: ${point.score}`}</title></circle>)}</svg><div className={styles.xAxis}>{chartPoints.map((point) => <span key={`${point.date}-label`}>{formatDate(point.date)}</span>)}</div></div>}
  </div>;
}

function ProgramRow({ program, universityId }: { program: UniversityHealthProgram; universityId: string }) {
  const href = program.workflow_instance_id ? `/workflows/${program.workflow_instance_id}` : `/universities/${universityId}?tab=workflow&program=${program.program_id}`;
  const progress = program.state === 'COMPLETED' ? 100 : program.workflow_progress;
  const progressLabel = program.state === 'NOT_STARTED' ? '—' : program.state === 'COMPLETED' ? 'Завершён' : `${program.stages_completed} из ${program.stages_total}`;
  return <Link className={styles.program} href={href} aria-label={`${program.program_name}: ${stateLabel[program.state]}`}><span className={styles.programName}>{program.program_name}</span><span className={styles.programBar}><ProgressBar value={progress} /><small>{progressLabel}</small></span><span className={`${styles.badge} ${styles[`badge${program.state}`]}`}><span aria-hidden="true">{stateMark[program.state]}</span>{stateLabel[program.state]}</span><span className={styles.workflowState}>{program.state === 'NOT_STARTED' ? 'Workflow не запущен' : program.state === 'COMPLETED' ? 'Завершён' : 'Workflow активен'}</span><strong>{program.state === 'COMPLETED' || program.state === 'NOT_STARTED' ? '—' : `${program.score ?? '—'} / 100`}</strong><ArrowRight className={styles.rowArrow} size={18} fill="currentColor" /></Link>;
}

export function UniversityHealth({ universityId }: { universityId: string }) {
  const query = useQuery({ queryKey: queryKeys.universities.health(universityId), queryFn: () => getUniversityHealth(universityId), staleTime: 30_000 });
  if (query.isPending) return <Skeleton height={560} />;
  if (query.isError) return <RouteErrorState onRetry={() => void query.refetch()} />;
  const health = query.data;
  if (!health) return <p className={styles.empty}>Health Score доступен при подключении к CRM.</p>;
  const coverage = health.total_programs ? health.active_workflows / health.total_programs * 100 : 0;
  return <div className={styles.page}>
    <section className={styles.summary} aria-labelledby="health-title"><div className={styles.scoreBlock}><h2 className={styles.eyebrow} id="health-title">Текущее состояние взаимодействия <span className={styles.info} title="Оценка показывает текущее состояние взаимодействия с вузом">i</span></h2><div className={styles.scoreRow}><div className={styles.scoreRing} data-level={health.level} style={{ '--score': `${health.score ?? 0}%` } as CSSProperties}><div><strong>{health.score === null ? '—' : health.score}</strong><span>/ 100</span></div></div><div className={styles.scoreIdentity}><strong>Health Score</strong><span className={`${styles.level} ${styles[`level${health.level}`]}`}>{health.level === 'critical' ? <ErrorStroke size={16} fill="currentColor" /> : health.level === 'attention' ? <Attention size={16} fill="currentColor" /> : <CheckSmall size={16} fill="currentColor" />}{levelLabel[health.level]}</span></div></div></div><dl className={styles.summaryStats}><div><dt><MetricIcon tone="brand"><Checklist size={18} fill="currentColor" /></MetricIcon>Workflow активны</dt><dd>{health.active_workflows} из {health.total_programs}</dd></div><div><dt><MetricIcon tone="warning"><TimeStroke size={18} fill="currentColor" /></MetricIcon>Требуют внимания</dt><dd data-tone="warning">{health.attention_count}</dd></div><div><dt><MetricIcon tone="danger"><ErrorStroke size={18} fill="currentColor" /></MetricIcon>Критично</dt><dd data-tone="danger">{health.critical_count}</dd></div><div><dt><MetricIcon tone="brand"><StatisticsBoard size={18} fill="currentColor" /></MetricIcon>Охват программ</dt><dd>{health.total_programs ? `${Math.round(coverage)}%` : '—'}</dd><ProgressBar value={coverage} /></div></dl><aside className={styles.summaryInfo}><span className={styles.infoSurface}><span className={styles.info}>i</span></span><p>Оценка показывает текущее состояние взаимодействия с вузом: Workflow, сроки, задачи и связанные активности.</p></aside></section>
    <section className={styles.surface} aria-labelledby="health-why"><h2 id="health-why">Почему такая оценка</h2><div className={styles.whyGrid}><div className={styles.factorColumn}><h3><MetricIcon tone="brand"><CheckSmall size={16} fill="currentColor" /></MetricIcon>Положительные факторы</h3>{health.positive_factors.length ? <ul className={styles.factors}>{health.positive_factors.map((factor) => <li key={factor.label}><CheckSmall size={16} fill="currentColor" />{factor.label}</li>)}</ul> : <p className={styles.empty}>Положительные факторы не зафиксированы.</p>}</div><div className={styles.factorColumn}><h3><MetricIcon tone="warning"><Attention size={16} fill="currentColor" /></MetricIcon>Факторы, требующие внимания</h3>{health.factors.length ? <ul className={styles.factors}>{health.factors.map((factor) => <li key={factor.label}><Attention size={16} fill="currentColor" />{factor.label}</li>)}</ul> : <p className={styles.empty}>Нет активных проблем.</p>}</div><HealthHistory history={health.history} /></div></section>
    <section className={styles.surface} aria-labelledby="health-coverage"><div className={styles.sectionHeader}><h2 id="health-coverage">Охват программ <span className={styles.info} title="Доля связанных программ с активным Workflow">i</span></h2><div className={styles.coverageSummary}><span>{health.active_workflows} из {health.total_programs} программ с активным процессом</span><ProgressBar value={coverage} /><strong>{health.total_programs ? `${Math.round(coverage)}%` : '—'}</strong></div></div>{health.programs.length ? <div className={styles.programs}>{health.programs.map((program) => <ProgramRow key={program.program_id} program={program} universityId={universityId} />)}</div> : <p className={styles.empty}>У ВУЗа пока нет связанных программ.</p>}</section>
  </div>;
}

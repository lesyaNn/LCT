'use client';

import Link from 'next/link';
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts';
import Checklist from '@atomaro/icons/24/action/Checklist';
import SecurityCheck from '@atomaro/icons/24/action/SecurityCheck';
import StatisticsColumn from '@atomaro/icons/24/business/StatisticsColumn';
import Education from '@atomaro/icons/24/culture/Education';
import Globe from '@atomaro/icons/24/culture/Globe';
import Book from '@atomaro/icons/24/culture/Book';
import AttentionStroke from '@atomaro/icons/24/alert/AttentionStroke';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import OkStroke from '@atomaro/icons/24/alert/OkStroke';
import ChevronRight from '@atomaro/icons/24/navigation/ChevronRight';
import { getUniversityHealth, type MatrixHealthState, type UniversityHealth, type UniversityHealthProgram } from '@/shared/lib/dashboard-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import { Progress } from '@/shared/ui/rtk/progress';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton } from '@/shared/ui/skeleton';
import styles from './university-health.module.css';

const stateMeta: Record<MatrixHealthState, { label: string; intent: SemanticIntent }> = {
  HEALTHY: { label: 'Стабильно', intent: 'success' },
  ATTENTION: { label: 'Требует внимания', intent: 'warning' },
  CRITICAL: { label: 'Критично', intent: 'danger' },
  NOT_STARTED: { label: 'Не запущено', intent: 'neutral' },
  COMPLETED: { label: 'Завершён', intent: 'success' },
  NOT_LINKED: { label: 'Не используется', intent: 'neutral' },
};
const levelMeta: Record<UniversityHealth['level'], { label: string; intent: SemanticIntent }> = {
  stable: { label: 'Стабильно', intent: 'success' },
  attention: { label: 'Требует внимания', intent: 'warning' },
  critical: { label: 'Критично', intent: 'danger' },
  no_data: { label: 'Недостаточно данных', intent: 'neutral' },
};
const periods = [6, 12, 24] as const;

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value.slice(0, 10)}T12:00:00`));
}

function formatHistoryDate(value: string) {
  if (!value.includes('T')) return formatDate(value);
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

function InfoHint({ content }: { content: string }) {
  return <Tooltip content={content}><button className={styles.infoButton} type="button" aria-label={content}><InformationStroke size={16} /></button></Tooltip>;
}

function IconSurface({ tone = 'brand', children }: { tone?: 'brand' | 'warning' | 'danger' | 'success'; children: ReactNode }) {
  return <span className={`${styles.iconSurface} ${styles[`icon${tone}`]}`} aria-hidden="true">{children}</span>;
}

function ProgramIcon({ name }: { name: string }) {
  const icon = /безопас/i.test(name) ? <SecurityCheck size={19} /> : /сет|интернет/i.test(name) ? <Globe size={19} /> : /образован|обучен/i.test(name) ? <Education size={19} /> : <Book size={19} />;
  return <IconSurface>{icon}</IconSurface>;
}

function ProgramStatus({ state }: { state: MatrixHealthState }) {
  return <StatusBadge intent={stateMeta[state].intent}>{stateMeta[state].label}</StatusBadge>;
}

function programHref(program: UniversityHealthProgram, universityId: string) {
  return program.workflow_instance_id ? `/workflows/${program.workflow_instance_id}` : `/universities/${universityId}?tab=workflow`;
}

function workflowLabel(program: UniversityHealthProgram) {
  if (!program.workflow_instance_id) return 'Workflow не запущен';
  return program.state === 'COMPLETED' ? 'Завершён' : 'Workflow активен';
}

function WorkflowProgress({ program }: { program: UniversityHealthProgram }) {
  if (!program.workflow_instance_id) return <span className={styles.stageCount}>Workflow не запущен</span>;
  return <div className={styles.workflowProgress}>
    {program.workflow_progress === null ? <span className={styles.muted}>—</span> : <Progress value={program.workflow_progress} label={`Пройдено этапов программы «${program.program_name}»`} />}
    <span className={styles.stageCount}>{program.stages_completed} из {program.stages_total}</span>
  </div>;
}

function HistoryChart({ history, currentScore }: { history: UniversityHealth['history']; currentScore: number | null }) {
  const [period, setPeriod] = useState<(typeof periods)[number]>(6);
  const points = useMemo(() => {
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - period);
    return history.filter((item) => new Date(item.date) >= cutoff).map((item, index) => ({
      ...item, index, label: formatHistoryDate(item.date), axisLabel: formatDate(item.date),
    }));
  }, [history, period]);
  const previous = points.at(-2);
  const last = points.at(-1);
  const change = last && previous ? last.score - previous.score : null;
  return <section className={`${styles.card} ${styles.historyCard}`} aria-labelledby="health-history">
    <div className={styles.cardHeader}>
      <h2 id="health-history">Динамика Health Score <InfoHint content="Текущая оценка сохраняется на сервере при открытии вкладки. Новая точка появляется, когда балл или статус изменится. История доступна за 24 месяца." /></h2>
      <div className={styles.periods} role="group" aria-label="Период истории">{periods.map((item) => <button type="button" key={item} className={period === item ? styles.periodActive : styles.period} aria-pressed={period === item} onClick={() => setPeriod(item)}>{item} мес.</button>)}</div>
    </div>
    {points.length ? <div className={styles.chart} role="img" aria-label={`История Health Score: ${points.map((item) => `${item.label} — ${item.score}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 20, right: 18, left: -22, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--rtk-color-border)" />
          <XAxis dataKey="index" tickFormatter={(index: number) => points[index]?.axisLabel ?? ''} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={22} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: 'var(--rtk-color-text-secondary)', fontSize: 11 }} tickLine={false} axisLine={false} />
          <ChartTooltip labelFormatter={(index) => points[Number(index)]?.label ?? ''} formatter={(value) => [`${value} / 100`, 'Health Score']} contentStyle={{ border: '1px solid var(--rtk-color-border)', borderRadius: 'var(--rtk-radius-small)', background: 'var(--rtk-color-surface-elevated)', fontSize: 12 }} />
          <Area type="linear" dataKey="score" stroke="var(--rtk-color-brand)" strokeWidth={2} fill="var(--rtk-color-brand-soft)" dot={{ r: 4, strokeWidth: 2, fill: 'var(--rtk-color-surface-elevated)' }} activeDot={{ r: 5 }} isAnimationActive={false}>
            <LabelList dataKey="score" position="top" fill="var(--rtk-color-text-primary)" fontSize={11} />
          </Area>
        </AreaChart>
      </ResponsiveContainer>
    </div> : <p className={styles.chartEmpty}>{currentScore === null ? 'Оценка появится после запуска Workflow.' : 'История оценок пока пуста.'}</p>}
    {points.length === 1 ? <p className={styles.snapshotCompare}>Текущая оценка показана на графике. Линия появится после изменения балла.</p> : change !== null ? <p className={styles.snapshotCompare}>Последнее изменение: {change > 0 ? `+${change}` : change} по сравнению с {formatHistoryDate(previous!.date)}</p> : null}
  </section>;
}

function CoverageRow({ program, universityId }: { program: UniversityHealthProgram; universityId: string }) {
  return <Link className={styles.coverageRow} href={programHref(program, universityId)} aria-label={`${program.program_name}, ${stateMeta[program.state].label}. Открыть Workflow`}>
    <span className={styles.programIdentity}><ProgramIcon name={program.program_name} /><span>{program.program_name}</span></span>
    <span className={styles.coverageBar}>{program.score === null ? <span className={styles.muted}>—</span> : <Progress value={program.score} label={`Health Score программы «${program.program_name}»`} />}</span>
    <span className={styles.programScore}>{program.score === null ? '—' : <><strong>{program.score}</strong> / 100</>}</span>
    <span className={styles.coverageStatus}><ProgramStatus state={program.state} /></span>
    <span className={styles.workflowText}>{workflowLabel(program)}</span>
    <ChevronRight className={styles.chevron} size={17} />
  </Link>;
}

function Deadline({ program }: { program: UniversityHealthProgram }) {
  if (program.deadline) return <span className={program.overdue_days ? styles.overdue : undefined}>{formatDate(program.deadline)}{program.overdue_days ? ` · ${program.overdue_days} дн. просрочено` : ''}</span>;
  return <span className={styles.muted}>{program.state === 'COMPLETED' ? 'Завершён' : program.workflow_instance_id ? 'Не указан' : '—'}</span>;
}

function ProgramTable({ programs, universityId }: { programs: UniversityHealthProgram[]; universityId: string }) {
  return <section className={`${styles.card} ${styles.tableCard}`} aria-labelledby="health-program-table"><h2 id="health-program-table">По программам <InfoHint content="Статус и оценка показывают состояние взаимодействия. Прогресс отражает пройденные этапы Workflow." /></h2>
    {programs.length ? <><div className={styles.tableDesktop}><table className={styles.table}><thead><tr><th>Программа</th><th>Статус</th><th>Workflow</th><th>Срок</th><th>Оценка</th><th><span className={styles.srOnly}>Открыть</span></th></tr></thead><tbody>{programs.map((program) => <tr key={program.program_id}><td><Link className={styles.tableName} href={programHref(program, universityId)}><ProgramIcon name={program.program_name} />{program.program_name}</Link></td><td><ProgramStatus state={program.state} /></td><td><WorkflowProgress program={program} /></td><td><Deadline program={program} /></td><td className={styles.tableScore}>{program.score === null ? '—' : <><strong>{program.score}</strong> / 100</>}</td><td><Link className={styles.rowLink} href={programHref(program, universityId)} aria-label={`Открыть ${program.program_name}`}><ChevronRight size={17} /></Link></td></tr>)}</tbody></table></div><div className={styles.tableMobile}>{programs.map((program) => <Link className={styles.mobileProgram} key={program.program_id} href={programHref(program, universityId)}><span className={styles.programIdentity}><ProgramIcon name={program.program_name} /><strong>{program.program_name}</strong></span><ProgramStatus state={program.state} /><span className={styles.mobileDetails}><span>Workflow <b>{program.workflow_instance_id ? `${program.stages_completed} из ${program.stages_total}` : 'не запущен'}</b></span><span>Срок <Deadline program={program} /></span><span>Оценка <b>{program.score === null ? '—' : `${program.score} / 100`}</b></span></span><ChevronRight className={styles.chevron} size={17} /></Link>)}</div></> : <p className={styles.empty}>Связанных программ пока нет.</p>}
  </section>;
}

function ScoreBreakdown({ health }: { health: UniversityHealth }) {
  const calculation = health.calculation;
  return <section className={`${styles.card} ${styles.breakdownCard}`} aria-labelledby="health-breakdown">
    <h2 id="health-breakdown">Из чего складывается оценка <InfoHint content="Баллы и правила расчёта поступают из действующей модели Health Score." /></h2>
    <p className={styles.calculationIntro}>Каждый запущенный Workflow {calculation ? `начинается со ${calculation.base_score} баллов` : 'получает базовую оценку'}. При проблемах баллы снижаются:</p>
    {calculation ? <dl className={styles.calculationRules}>{calculation.penalties.map((rule) => <div key={rule.label}><dt>{rule.label}</dt><dd>−{rule.points}{rule.maximum ? <small> за задачу, не более −{rule.maximum}</small> : null}</dd></div>)}</dl> : null}
    <p className={styles.calculationNote}>Итог по вузу — среднее оценок запущенных и завершённых Workflow. Незапущенные программы в среднее не входят. Завершённый Workflow получает {calculation ? `${calculation.base_score} баллов` : 'максимальную оценку'}.{calculation ? ` При критичной программе итог не выше ${calculation.critical_cap}; при предупреждении и отсутствии критичных программ — не выше ${calculation.attention_cap}, если среднее было стабильным.` : ''}</p>
  </section>;
}

export function UniversityHealth({ universityId }: { universityId: string }) {
  const query = useQuery({ queryKey: queryKeys.universities.health(universityId), queryFn: () => getUniversityHealth(universityId), staleTime: 30_000 });
  if (query.isPending) return <div className={styles.loading}><Skeleton height={205} /><div className={styles.loadingPair}><Skeleton height={218} /><Skeleton height={218} /></div><Skeleton height={180} /></div>;
  if (query.isError) return <RouteErrorState onRetry={() => void query.refetch()} />;
  const health = query.data;
  if (!health) return <p className={styles.empty}>Health Score пока недоступен.</p>;
  const coverage = health.total_programs ? Math.round(health.active_workflows / health.total_programs * 100) : null;
  return <div className={styles.page}>
    <section className={`${styles.card} ${styles.summary}`} aria-labelledby="health-title"><h2 id="health-title">Текущее состояние взаимодействия <InfoHint content="Текущая оценка взаимодействия с вузом по данным Workflow и связанных задач, этапов, ответственных и лицензий." /></h2><div className={styles.summaryBody}>
      <div className={styles.scoreBlock}><div className={styles.scoreRing} data-level={health.level} style={{ '--score': `${health.score ?? 0}%` } as CSSProperties}><div><strong>{health.score ?? '—'}</strong><span>/ 100</span></div></div><div className={styles.scoreIdentity}><strong>Health Score</strong><StatusBadge intent={levelMeta[health.level].intent}>{levelMeta[health.level].label}</StatusBadge></div></div>
      <dl className={styles.metrics}><div className={styles.metric}><dt><IconSurface><Checklist size={19} /></IconSurface><span>Workflow активны</span></dt><dd>{health.active_workflows} из {health.total_programs}</dd></div><div className={styles.metric}><dt><IconSurface tone="warning"><AttentionStroke size={19} /></IconSurface><span>Требуют внимания</span></dt><dd>{health.attention_count}</dd></div><div className={styles.metric}><dt><IconSurface tone="danger"><ErrorStroke size={19} /></IconSurface><span>Критично</span></dt><dd>{health.critical_count}</dd></div><div className={styles.metric}><dt><IconSurface><StatisticsColumn size={19} /></IconSurface><span>Охват программ</span></dt><dd>{coverage === null ? '—' : `${coverage}%`}</dd>{coverage !== null ? <Progress value={coverage} label="Охват программ активными Workflow" /> : null}</div></dl>
      <aside className={styles.summaryInfo}><IconSurface><InformationStroke size={20} /></IconSurface><p>Оценка показывает текущее состояние взаимодействия с вузом: этапы Workflow, задачи, назначение ответственных и связанные лицензии. Она не отражает академический рейтинг вуза.</p></aside>
    </div></section>
    <div className={styles.secondRow}><section className={`${styles.card} ${styles.reasonsCard}`} aria-labelledby="health-why"><h2 id="health-why">Почему такая оценка <InfoHint content="Причины и положительные факторы получены из текущего Health Score." /></h2><div className={styles.reasonColumns}><div className={styles.reasonColumn}><h3><IconSurface tone="success"><OkStroke size={18} /></IconSurface>Положительные факторы</h3>{health.positive_factors.length ? <ul>{health.positive_factors.map((factor, index) => <li key={`${factor.label}-${index}`}><OkStroke size={17} />{factor.label}</li>)}</ul> : <p className={styles.empty}>Положительные факторы не зафиксированы.</p>}</div><div className={styles.reasonColumn}><h3><IconSurface tone="warning"><AttentionStroke size={18} /></IconSurface>Факторы, требующие внимания</h3>{health.factors.length ? <ul>{health.factors.map((factor, index) => <li key={`${factor.label}-${index}`}><AttentionStroke size={17} />{factor.label}</li>)}</ul> : <p className={styles.empty}>Факторы риска не зафиксированы.</p>}</div></div></section><HistoryChart history={health.history} currentScore={health.score} /></div>
    <section className={`${styles.card} ${styles.coverageCard}`} aria-labelledby="health-coverage"><div className={styles.cardHeader}><h2 id="health-coverage">Охват программ <InfoHint content="Общий процент — доля программ с активным Workflow. Полоса в каждой строке показывает Health Score этой программы." /></h2><div className={styles.coverageSummary}><span>{health.active_workflows} из {health.total_programs} программ с активным процессом</span><span className={styles.coverageSummaryBar}>{coverage !== null ? <Progress value={coverage} label="Охват программ активными Workflow" /> : null}</span><strong>{coverage === null ? '—' : `${coverage}%`}</strong></div></div>{health.programs.length ? <div className={styles.coverageRows}>{health.programs.map((program) => <CoverageRow key={program.program_id} program={program} universityId={universityId} />)}</div> : <p className={styles.empty}>У вуза пока нет связанных программ.</p>}</section>
    <ProgramTable programs={health.programs} universityId={universityId} />
    <ScoreBreakdown health={health} />
  </div>;
}

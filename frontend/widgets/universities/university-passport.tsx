'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useSyncExternalStore } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Checklist from '@atomaro/icons/24/action/Checklist';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import Group from '@atomaro/icons/24/business/Group';
import StatisticsBoard from '@atomaro/icons/24/business/StatisticsBoard';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import HistoryAction from '@atomaro/icons/24/communication/HistoryAction';
import Book from '@atomaro/icons/24/culture/Book';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import Education from '@atomaro/icons/24/culture/Education';
import Edit from '@atomaro/icons/24/editor/Edit';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { healthStatusMeta, type HealthStatus } from '@/shared/lib/health-score';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { workflowStatusIntent } from '@/shared/lib/status-semantics';
import {
  getUniversityPassport,
  getUniversityHealthScore,
  universityPassportQueryKey,
  universityHealthScoreQueryKey,
  UNIVERSITY_PASSPORT_CAPABILITIES,
  type UniversityPassport,
  type UniversityPassportEvent,
  type UniversityPassportEventType,
} from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { TabbedSurface } from '@/shared/ui/rtk/tabbed-surface';
import { EmptyState } from '@/shared/ui/empty-state';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { StatusBadge as SemanticStatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { NotFoundState } from '@/shared/ui/not-found-state';
import { ForbiddenState } from '@/shared/ui/access-state';
import { MetricCardSkeleton, Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import { UniversityHealthScore } from './university-health-score';
import { UniversityHistory } from './university-history';
import { DocumentsSection, LicensesSection, MeetingsSection, ProductsSection, ProgramsSection, ResponsiblesSection, StudentsSection, TeachersSection } from './university-passport-sections';
import { UniversityWorkflow } from './university-workflow';
import styles from './university-passport.module.css';

const mobileLayoutQuery = '(max-width: 768px)';

function subscribeToMobileLayout(listener: () => void) {
  const media = window.matchMedia(mobileLayoutQuery);
  media.addEventListener('change', listener);
  return () => media.removeEventListener('change', listener);
}

function isMobileLayout() {
  return window.matchMedia(mobileLayoutQuery).matches;
}

const tabDefinitions = [
  { id: 'overview', label: 'Обзор' },
  { id: 'health-score', label: 'Health Score' },
  { id: 'programs', label: 'Программы' },
  { id: 'teachers', label: 'Преподаватели' },
  { id: 'students', label: 'Студенты' },
  { id: 'products', label: 'Продукты' },
  { id: 'licenses', label: 'Лицензии' },
  { id: 'documents', label: 'Документы' },
  { id: 'meetings', label: 'Встречи' },
  { id: 'responsibles', label: 'Ответственные' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'history', label: 'История' },
] as const;

type PassportTabId = (typeof tabDefinitions)[number]['id'];

const tabIds = new Set<PassportTabId>(tabDefinitions.map((tab) => tab.id));

function parseTab(value: string | null): PassportTabId {
  return value && tabIds.has(value as PassportTabId) ? value as PassportTabId : 'overview';
}

function getInitials(name: string): string {
  return name.split(/\s+/).map((part) => part[0]).filter(Boolean).slice(0, 2).join('').toLocaleUpperCase('ru-RU');
}

function StatusBadge({ status }: { status: HealthStatus }) {
  const meta = healthStatusMeta[status];
  return <SemanticStatusBadge intent={meta.tone}>{meta.label}</SemanticStatusBadge>;
}

function HeaderHealth({ score, status, onDetails }: { score: number | null; status: HealthStatus | null; onDetails: () => void }) {
  if (score === null || status === null) return <div className={styles.healthSummary}><span className={styles.overline}>Health Score</span><strong className={styles.healthScore}>—</strong><button className={styles.textAction} type="button" onClick={onDetails}>Подробнее <ArrowRight size={14} fill="currentColor" /></button></div>;
  return (
    <div className={styles.healthSummary}>
      <div className={styles.healthSummaryTop}>
        <div>
          <span className={styles.overline}>Health Score</span>
          <strong className={styles.healthScore}>{score}</strong>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className={styles.healthMeter} role="progressbar" aria-label={`Health Score ${score} из 100`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={score}>
        <span className={`${styles.healthMeterFill} ${styles[`meter-${status}`]}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <button className={styles.textAction} type="button" onClick={onDetails}>Подробнее <ArrowRight size={14} fill="currentColor" /></button>
    </div>
  );
}

function PassportHeader({ passport, healthScore, healthStatus, canEdit, canReport, onTabChange }: { passport: UniversityPassport; healthScore: number | null; healthStatus: HealthStatus | null; canEdit: boolean; canReport: boolean; onTabChange: (tab: PassportTabId) => void }) {
  return (
    <header className={styles.header}>
      <div className={styles.headerMain}>
        <div className={styles.titleBlock}>
          <h1>{passport.name}</h1>
          <p className={styles.city}>{passport.city}</p>
        </div>
        <div className={styles.headerSide}>
          <HeaderHealth score={healthScore} status={healthStatus} onDetails={() => onTabChange('health-score')} />
          <div className={styles.headerActions} aria-label="Действия с вузом">
            {canEdit ? <Button variant="secondary" size="s" type="button" disabled title="Редактирование подключится после появления API"><Edit size={16} fill="currentColor" />Редактировать</Button> : null}
            {canReport ? <Button variant="secondary" size="s" type="button" disabled title="Формирование отчёта подключится после появления API"><DocumentText size={16} fill="currentColor" />Отчёт</Button> : null}
            <Button variant="primary" size="s" type="button" onClick={() => onTabChange('workflow')}><Checklist size={16} fill="currentColor" />Workflow</Button>
          </div>
        </div>
      </div>
    </header>
  );
}

function OverviewMetrics({ passport }: { passport: UniversityPassport }) {
  const { metrics } = passport;
  const licensesTotal = metrics.licenses.active + metrics.licenses.expiring + metrics.licenses.overdue;
  return (
    <section className={styles.section} aria-labelledby="passport-metrics-title">
      <div className={styles.sectionHeading}><h2 id="passport-metrics-title">Ключевые показатели</h2></div>
      <div className={styles.metricsGrid}>
        <MetricCard label="Активные программы" value={metrics.activePrograms} icon={Book} />
        <MetricCard label="Преподаватели" value={metrics.teachers.total} icon={Group} indicators={[{ value: metrics.teachers.ready, label: 'готовы', intent: 'success' }, { value: metrics.teachers.attention, label: 'требуют внимания', intent: 'warning' }]} />
        <MetricCard label="Лицензии" value={licensesTotal} icon={Education} indicators={[{ value: metrics.licenses.active, label: 'действуют', intent: 'success' }, { value: metrics.licenses.expiring, label: 'истекают', intent: 'warning' }, { value: metrics.licenses.overdue, label: 'просрочены', intent: 'danger' }]} />
        <MetricCard label="Документы" value={metrics.documents.limited ? `≥${metrics.documents.total}` : metrics.documents.total} icon={DocumentText} indicators={metrics.documents.limited ? undefined : [{ value: metrics.documents.signed, label: 'подписано', intent: 'success' }, { value: metrics.documents.overdue, label: 'просрочено', intent: 'danger' }]} />
      </div>
    </section>
  );
}

function WorkflowOverview({ passport, canAdvance, onTabChange }: { passport: UniversityPassport; canAdvance: boolean; onTabChange: (tab: PassportTabId) => void }) {
  const { workflow } = passport;
  const progress = Math.round((workflow.completedSteps / workflow.totalSteps) * 100);
  const overdue = workflow.overdue;
  const statusLabel = workflow.status === 'completed' ? 'Завершён' : workflow.status === 'attention' ? 'Требует внимания' : 'В работе';

  return (
    <section className={styles.workflowCard} aria-labelledby="passport-workflow-title">
      <div className={styles.sectionHeading}><h2 id="passport-workflow-title">Текущий этап Workflow</h2><button className={styles.textAction} type="button" onClick={() => onTabChange('workflow')}>Открыть Workflow <ArrowRight size={14} fill="currentColor" /></button></div>
      <div className={styles.workflowLayout}>
        <div className={styles.workflowStage}><span className={styles.overline}>Текущий этап</span><strong>{workflow.currentStage.name}</strong><SemanticStatusBadge intent={workflowStatusIntent[workflow.status]}>{statusLabel}</SemanticStatusBadge></div>
        <div className={styles.workflowDetails}>
          <div><span className={styles.detailLabel}>Дедлайн</span><strong className={overdue ? styles.overdue : undefined}><TimeStroke size={16} fill="currentColor" />{formatDateRu(workflow.deadline)}</strong>{overdue ? <span className={styles.detailWarning}>Срок просрочен</span> : null}</div>
          <div><span className={styles.detailLabel}>Ответственный</span><strong className={styles.responsibleValue}>{workflow.responsible ? <><Avatar initials={getInitials(workflow.responsible.name)} size="s" />{workflow.responsible.name}</> : 'Не назначен'}</strong></div>
        </div>
        <div className={styles.workflowProgress}>
          <div className={styles.progressLabel}><span>Прогресс</span><strong>{workflow.completedSteps} из {workflow.totalSteps} этапов</strong></div>
          <div className={styles.progressTrack} role="progressbar" aria-label={`Пройдено ${workflow.completedSteps} из ${workflow.totalSteps} этапов`} aria-valuemin={0} aria-valuemax={workflow.totalSteps} aria-valuenow={workflow.completedSteps}><span style={{ width: `${progress}%` }} /></div>
        </div>
        {canAdvance && workflow.nextStage ? <div className={styles.workflowAction}><Button variant="secondary" size="s" type="button" disabled title="Переход подключится после появления API">Перевести на следующий этап <ArrowRight size={16} fill="currentColor" /></Button><span>Следующий этап: {workflow.nextStage.name}</span></div> : null}
      </div>
    </section>
  );
}

function EventIcon({ type }: { type: UniversityPassportEventType }) {
  if (type === 'meeting') return <Calendar size={18} fill="currentColor" />;
  if (type === 'document') return <DocumentText size={18} fill="currentColor" />;
  if (type === 'workflow') return <HistoryAction size={18} fill="currentColor" />;
  return <Edit size={18} fill="currentColor" />;
}

function TimelineItem({ event }: { event: UniversityPassportEvent }) {
  return <li className={styles.timelineItem}><span className={styles.timelineIcon} aria-hidden="true"><EventIcon type={event.type} /></span><div className={styles.timelineBody}><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time><p>{event.description}</p></div></li>;
}

function RecentInteractions({ events, onTabChange }: { events: UniversityPassportEvent[]; onTabChange: (tab: PassportTabId) => void }) {
  return (
    <section className={styles.timelineCard} aria-labelledby="passport-timeline-title">
      <div className={styles.sectionHeading}><h2 id="passport-timeline-title">Последние взаимодействия</h2><Button variant="ghost" size="s" type="button" onClick={() => onTabChange('history')}>Показать всё <ArrowRight size={14} fill="currentColor" /></Button></div>
      {events.length ? <ol className={styles.timeline}>{events.slice(0, 5).map((event) => <TimelineItem event={event} key={event.id} />)}</ol> : <EmptyState title="Взаимодействий пока нет" description="Встречи, документы и изменения Workflow появятся здесь." headingLevel={3} />}
    </section>
  );
}

function OverviewContent({ passport, canAdvance, onTabChange }: { passport: UniversityPassport; canAdvance: boolean; onTabChange: (tab: PassportTabId) => void }) {
  return <div className={styles.overviewContent}><OverviewMetrics passport={passport} /><WorkflowOverview passport={passport} canAdvance={canAdvance} onTabChange={onTabChange} /><RecentInteractions events={passport.timeline} onTabChange={onTabChange} /></div>;
}

function PlaceholderContent({ tab }: { tab: (typeof tabDefinitions)[number] }) {
  return <EmptyState icon={<StatisticsBoard size={24} fill="currentColor" />} title={`${tab.label}: данных пока нет`} description="Данные появятся после подключения модуля." />;
}

function PassportSkeleton() {
  return <SkeletonGroup label="Загрузка паспорта вуза"><Skeleton variant="text" width="220px" /><Skeleton variant="text" width="min(72%, 520px)" height={36} /><Skeleton height={180} /><MetricCardSkeleton count={4} /><Skeleton height={260} /><Skeleton height={220} /></SkeletonGroup>;
}

export function UniversityPassport({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const mobileLayout = useSyncExternalStore(subscribeToMobileLayout, isMobileLayout, () => false);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const activeTab = parseTab(searchParams.get('tab'));
  const query = useQuery({ queryKey: universityPassportQueryKey(id), queryFn: () => getUniversityPassport(id, queryClient), staleTime: 30_000 });
  const healthQuery = useQuery({ queryKey: universityHealthScoreQueryKey(id), queryFn: ({ signal }) => getUniversityHealthScore(id, signal), enabled: query.isSuccess, staleTime: 30_000 });
  const canEdit = user?.role === 'admin';
  const canReport = user?.role === 'admin' || user?.role === 'manager';
  const canAdvance = canReport && UNIVERSITY_PASSPORT_CAPABILITIES.mutations;
  const activeTabDefinition = useMemo(() => tabDefinitions.find((tab) => tab.id === activeTab) ?? tabDefinitions[0], [activeTab]);

  const selectTab = (tab: PassportTabId) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', tab);
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  };

  if (query.isPending) return <PassportSkeleton />;
  if (query.isError && normalizeApiError(query.error).kind === 'not-found') return <NotFoundState />;
  if (query.isError && normalizeApiError(query.error).kind === 'permission') return <ForbiddenState />;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  const passport = query.data;
  const renderContent = (tab: PassportTabId) => tab === 'overview'
    ? <OverviewContent passport={passport} canAdvance={canAdvance} onTabChange={selectTab} />
    : tab === 'health-score'
      ? <UniversityHealthScore id={id} />
    : tab === 'programs'
      ? <ProgramsSection id={id} />
    : tab === 'teachers'
      ? <TeachersSection id={id} />
    : tab === 'students'
      ? <StudentsSection id={id} />
    : tab === 'products'
      ? <ProductsSection id={id} />
    : tab === 'licenses'
      ? <LicensesSection id={id} />
    : tab === 'documents'
      ? <DocumentsSection id={id} />
    : tab === 'meetings'
      ? <MeetingsSection id={id} canAdd={hasPermission(user, 'university.edit')} />
    : tab === 'responsibles'
      ? <ResponsiblesSection id={id} canEdit={hasPermission(user, 'university.edit')} />
    : tab === 'workflow'
      ? <UniversityWorkflow id={id} canAdvance={canAdvance} />
    : tab === 'history'
      ? <UniversityHistory id={id} />
    : <PlaceholderContent tab={tabDefinitions.find((definition) => definition.id === tab) ?? activeTabDefinition} />;

  return (
    <div className={styles.page}>
      <PassportHeader passport={passport} healthScore={healthQuery.data?.currentScore ?? null} healthStatus={healthQuery.data?.status ?? null} canEdit={canEdit && UNIVERSITY_PASSPORT_CAPABILITIES.mutations} canReport={canReport} onTabChange={selectTab} />
      <TabbedSurface tabs={!mobileLayout ? <Tabs items={tabDefinitions} activeId={activeTab} onChange={(id) => selectTab(id as PassportTabId)} label="Разделы паспорта вуза" prefix="passport-tab" /> : undefined}>
      {!mobileLayout ? <div className={styles.desktopPanel} id="passport-panel" role="tabpanel" aria-labelledby={`passport-tab-${activeTab}`}>{renderContent(activeTab)}</div> : null}
      {mobileLayout ? <div className={styles.mobileAccordion} aria-label="Разделы паспорта вуза">
        {tabDefinitions.map((tab) => {
          const isOpen = activeTab === tab.id;
          return <section className={styles.accordionItem} key={tab.id}><button className={isOpen ? styles.accordionTriggerActive : styles.accordionTrigger} type="button" aria-expanded={isOpen} onClick={() => selectTab(tab.id)}><span>{tab.label}</span><ArrowRight size={18} fill="currentColor" /></button>{isOpen ? <div className={styles.accordionPanel}>{renderContent(tab.id)}</div> : null}</section>;
        })}
      </div> : null}
      </TabbedSurface>
    </div>
  );
}

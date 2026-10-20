'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useState, useSyncExternalStore } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
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
import { formatDateTimeRu } from '@/shared/lib/formatters';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { getUniversityHealth } from '@/shared/lib/dashboard-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { healthLevelMeta } from '@/shared/lib/status-semantics';
import {
  getWorkflowSelectorPrograms,
  getUniversityPassport,
  isRealWorkflowMode,
  universityPassportQueryKey,
  workflowProgramsQueryKey,
  type UniversityPassport,
  type UniversityPassportEvent,
  type UniversityPassportEventType,
} from '@/shared/lib/universities-repository';
import { listUniversityWorkflowInstances, universityWorkflowInstancesQueryKey } from '@/shared/lib/workflow-creation-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { TabbedSurface } from '@/shared/ui/rtk/tabbed-surface';
import { EmptyState } from '@/shared/ui/empty-state';
import { MetricCard } from '@/shared/ui/rtk/metric-card';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { NotFoundState } from '@/shared/ui/not-found-state';
import { ForbiddenState } from '@/shared/ui/access-state';
import { MetricCardSkeleton, Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import { UniversityHistory } from './university-history';
import { DocumentsSection, LicensesSection, MeetingsSection, ProductsSection } from './university-passport-sections';
import { ResponsiblesSection } from './university-responsibles-section';
import { UniversityWorkflow } from './university-workflow';
import { WorkflowCreateModal } from './workflow-create-modal';
import { PassportWorkflowCard } from './passport-workflow-card';
import { UniversityHealth } from './university-health';
import { UniversityLocalClock } from './university-local-clock';
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
  { id: 'health', label: 'Health Score' },
  { id: 'products', label: 'ИТ-продукты' },
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

function PassportHeader({ passport }: { passport: UniversityPassport }) {
  return (
    <header className={styles.header}>
      <div className={styles.headerMain}>
        <div className={styles.titleBlock}>
          <h1>{passport.name}</h1>
          <p className={styles.city}>{passport.city}</p>
        </div>
        <div className={styles.headerSide}>
          <UniversityLocalClock city={passport.city} timeZone={passport.timeZone} />
        </div>
      </div>
    </header>
  );
}

function OverviewMetrics({ passport }: { passport: UniversityPassport }) {
  const { metrics } = passport;
  const healthQuery = useQuery({ queryKey: queryKeys.universities.health(passport.id), queryFn: () => getUniversityHealth(passport.id), staleTime: 30_000 });
  const health = healthQuery.data;
  const licensesTotal = metrics.licenses.active + metrics.licenses.expiring + metrics.licenses.overdue;
  return (
    <section className={styles.section} aria-labelledby="passport-metrics-title">
      <div className={styles.sectionHeading}><h2 id="passport-metrics-title">Ключевые показатели</h2></div>
      <div className={styles.metricsGrid}>
        <MetricCard label="Активные программы" value={health?.active_workflows ?? '—'} icon={Book} />
        <MetricCard label="Health Score" value={health?.score === null || health?.score === undefined ? '—' : <><span style={{ color: `var(--rtk-color-${healthLevelMeta[health.level].intent}, var(--rtk-color-text-primary))` }}>{health.score}</span> / 100</>} icon={StatisticsBoard} />
        <MetricCard label="Лицензии" value={licensesTotal} icon={Education} indicators={[{ value: metrics.licenses.active, label: 'действуют', intent: 'success' }, { value: metrics.licenses.expiring, label: 'истекают', intent: 'warning' }, { value: metrics.licenses.overdue, label: 'просрочены', intent: 'danger' }]} />
        <MetricCard label="Документы" value={metrics.documents.limited ? `≥${metrics.documents.total}` : metrics.documents.total} icon={DocumentText} indicators={metrics.documents.limited ? undefined : [{ value: metrics.documents.signed, label: 'подписано', intent: 'success' }, { value: metrics.documents.overdue, label: 'просрочено', intent: 'danger' }]} />
      </div>
    </section>
  );
}

function WorkflowOverview({ passport }: { passport: UniversityPassport }) {
  const { user } = useAuth();
  const [launchProgramId, setLaunchProgramId] = useState<string | null>(null);
  const realWorkflow = isRealWorkflowMode();
  const canCreate = realWorkflow && hasPermission(user, 'workflow.change_status');
  const instancesQuery = useQuery({ queryKey: universityWorkflowInstancesQueryKey(passport.id), queryFn: ({ signal }) => listUniversityWorkflowInstances(passport.id, signal), enabled: realWorkflow, staleTime: 30_000 });
  const programsQuery = useQuery({ queryKey: workflowProgramsQueryKey(passport.id), queryFn: ({ signal }) => getWorkflowSelectorPrograms(passport.id, signal), enabled: realWorkflow, staleTime: 30_000 });
  const instances = instancesQuery.data ?? [];
  const unstartedPrograms = (programsQuery.data ?? []).filter((program) => !instances.some((instance) => instance.program_id === program.id));

  return <section className={styles.workflowCard} aria-labelledby="passport-workflow-title">
    <div className={styles.sectionHeading}><h2 id="passport-workflow-title">Workflow</h2></div>
    {realWorkflow && (instancesQuery.isPending || programsQuery.isPending) ? <Skeleton height={136} />
      : realWorkflow && (instancesQuery.isError || programsQuery.isError) ? <RouteErrorState compact onRetry={() => { void instancesQuery.refetch(); void programsQuery.refetch(); }} />
        : <div className={styles.workflowCards}>
          {instances.map((instance) => <PassportWorkflowCard key={instance.id} instance={instance} />)}
          {(unstartedPrograms.length ? unstartedPrograms : instances.length ? [] : [{ id: '', name: 'Workflow' }]).map((program) => <PassportWorkflowCard key={program.id || 'empty'} programName={program.name} onLaunch={canCreate ? () => setLaunchProgramId(program.id) : undefined} />)}
        </div>}
    {launchProgramId !== null ? <WorkflowCreateModal universityId={passport.id} initialProgramId={launchProgramId || undefined} onClose={() => setLaunchProgramId(null)} onCreated={() => setLaunchProgramId(null)} /> : null}
  </section>;
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

function OverviewContent({ passport, onTabChange }: { passport: UniversityPassport; onTabChange: (tab: PassportTabId) => void }) {
  return <div className={styles.overviewContent}><OverviewMetrics passport={passport} /><WorkflowOverview passport={passport} /><RecentInteractions events={passport.timeline} onTabChange={onTabChange} /></div>;
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
  const [collapsedMobileTab, setCollapsedMobileTab] = useState<{ universityId: string; tab: PassportTabId } | null>(null);
  const query = useQuery({ queryKey: universityPassportQueryKey(id), queryFn: () => getUniversityPassport(id, queryClient), staleTime: 30_000 });
  const activeTabDefinition = useMemo(() => tabDefinitions.find((tab) => tab.id === activeTab) ?? tabDefinitions[0], [activeTab]);

  const selectTab = (tab: PassportTabId) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', tab);
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  };

  if (query.isPending) return <PassportSkeleton />;
  if (query.isError && normalizeApiError(query.error).kind === 'not-found') return <NotFoundState />;
  if (query.isError && normalizeApiError(query.error).kind === 'permission') return <ForbiddenState />;
  if (!query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  const passport = query.data;
  const renderContent = (tab: PassportTabId) => tab === 'overview'
    ? <OverviewContent passport={passport} onTabChange={selectTab} />
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
      ? <UniversityWorkflow id={id} />
    : tab === 'health'
      ? <UniversityHealth universityId={id} />
    : tab === 'history'
      ? <UniversityHistory id={id} />
    : <PlaceholderContent tab={tabDefinitions.find((definition) => definition.id === tab) ?? activeTabDefinition} />;

  return (
    <div className={styles.page}>
      <PassportHeader passport={passport} />
      <TabbedSurface contentClassName={styles.passportContent} tabs={!mobileLayout ? <Tabs items={tabDefinitions} activeId={activeTab} onChange={(id) => selectTab(id as PassportTabId)} label="Разделы паспорта вуза" prefix="passport-tab" alternating /> : undefined}>
      {!mobileLayout ? <div className={`${styles.desktopPanel} ${activeTab === 'overview' || activeTab === 'health' || activeTab === 'meetings' ? styles.flushPanel : ''}`} id="passport-panel" role="tabpanel" aria-labelledby={`passport-tab-${activeTab}`}>{renderContent(activeTab)}</div> : null}
      {mobileLayout ? <div className={styles.mobileAccordion} aria-label="Разделы паспорта вуза">
        {tabDefinitions.map((tab) => {
          const isOpen = activeTab === tab.id && (collapsedMobileTab?.universityId !== id || collapsedMobileTab.tab !== tab.id);
          return <section className={styles.accordionItem} key={tab.id}><button className={isOpen ? styles.accordionTriggerActive : styles.accordionTrigger} type="button" aria-expanded={isOpen} onClick={() => {
            setCollapsedMobileTab(isOpen ? { universityId: id, tab: tab.id } : null);
            if (!isOpen && activeTab !== tab.id) selectTab(tab.id);
          }}><span>{tab.label}</span><ArrowRight size={18} fill="currentColor" /></button>{isOpen ? <div className={`${styles.accordionPanel} ${tab.id === 'overview' || tab.id === 'health' || tab.id === 'meetings' ? styles.flushPanel : ''}`}>{renderContent(tab.id)}</div> : null}</section>;
        })}
      </div> : null}
      </TabbedSurface>
    </div>
  );
}

'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMemo, type ComponentType, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { getHealthStatus, healthStatusMeta, type HealthStatus } from '@/shared/lib/health-score';
import {
  getUniversityPassport,
  type UniversityPassport,
  type UniversityPassportEvent,
  type UniversityPassportEventType,
} from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { UniversityHealthScore } from './university-health-score';
import { ProductsSection, ProgramsSection, StudentsSection, TeachersSection } from './university-passport-sections';
import styles from './university-passport.module.css';

const passportQueryKey = (id: string) => ['university-passport', id] as const;

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
type IconProps = { fill?: string; size?: number };

const tabIds = new Set<PassportTabId>(tabDefinitions.map((tab) => tab.id));

function parseTab(value: string | null): PassportTabId {
  return value && tabIds.has(value as PassportTabId) ? value as PassportTabId : 'overview';
}

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium' }).format(new Date(isoDate));
}

function formatDateTime(isoDate: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(isoDate));
}

function getInitials(name: string): string {
  return name.split(/\s+/).map((part) => part[0]).filter(Boolean).slice(0, 2).join('').toLocaleUpperCase('ru-RU');
}

function StatusBadge({ status }: { status: HealthStatus }) {
  const meta = healthStatusMeta[status];
  return <span className={`${styles.statusBadge} ${styles[`status-${status}`]}`}><span aria-hidden="true" />{meta.label}</span>;
}

function HeaderHealth({ score, onDetails }: { score: number; onDetails: () => void }) {
  const status = getHealthStatus(score);
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

function PassportHeader({ passport, canEdit, canReport, onTabChange }: { passport: UniversityPassport; canEdit: boolean; canReport: boolean; onTabChange: (tab: PassportTabId) => void }) {
  return (
    <header className={styles.header}>
      <div className={styles.breadcrumbs}><Link href="/universities">Вузы</Link><span aria-hidden="true">/</span><span>{passport.city}</span></div>
      <div className={styles.headerMain}>
        <div className={styles.titleBlock}>
          <p className={styles.eyebrow}>ПАСПОРТ ВУЗА</p>
          <h1>{passport.name}</h1>
          <p className={styles.city}>{passport.city}</p>
        </div>
        <div className={styles.headerSide}>
          <HeaderHealth score={passport.healthScore} onDetails={() => onTabChange('health-score')} />
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

function OverviewMetricCard({ title, icon: Icon, children }: { title: string; icon: ComponentType<IconProps>; children: ReactNode }) {
  return (
    <article className={styles.metricCard}>
      <div className={styles.metricHeader}><span className={styles.metricIcon} aria-hidden="true"><Icon size={20} fill="currentColor" /></span><h3>{title}</h3></div>
      {children}
    </article>
  );
}

function MetricValue({ value, label, tone = 'neutral' }: { value: number; label: string; tone?: 'neutral' | 'success' | 'warning' | 'danger' }) {
  return <div className={styles.metricValue}><strong>{value}</strong><span className={styles[`metric-${tone}`]}>{label}</span></div>;
}

function OverviewMetrics({ passport }: { passport: UniversityPassport }) {
  const { metrics } = passport;
  return (
    <section className={styles.section} aria-labelledby="passport-metrics-title">
      <div className={styles.sectionHeading}><h2 id="passport-metrics-title">Ключевые показатели</h2><span className={styles.sectionHint}>Актуальные данные паспорта</span></div>
      <div className={styles.metricsGrid}>
        <OverviewMetricCard title="Активные программы" icon={Book}><div className={styles.metricPrimary}><strong>{metrics.activePrograms}</strong><span>программ</span></div></OverviewMetricCard>
        <OverviewMetricCard title="Преподаватели" icon={Group}><div className={styles.metricPrimary}><strong>{metrics.teachers.total}</strong><span>всего</span></div><div className={styles.metricSubvalues}><MetricValue value={metrics.teachers.ready} label="готовы" tone="success" /><MetricValue value={metrics.teachers.attention} label="требуют внимания" tone="warning" /></div></OverviewMetricCard>
        <OverviewMetricCard title="Лицензии" icon={Education}><div className={styles.metricSubvalues}><MetricValue value={metrics.licenses.active} label="действуют" tone="success" /><MetricValue value={metrics.licenses.expiring} label="истекают" tone="warning" /><MetricValue value={metrics.licenses.overdue} label="просрочены" tone="danger" /></div></OverviewMetricCard>
        <OverviewMetricCard title="Документы" icon={DocumentText}><div className={styles.metricPrimary}><strong>{metrics.documents.total}</strong><span>всего</span></div><div className={styles.metricSubvalues}><MetricValue value={metrics.documents.signed} label="подписано" tone="success" /><MetricValue value={metrics.documents.overdue} label="просрочено" tone="danger" /></div></OverviewMetricCard>
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
      <div className={styles.sectionHeading}><div><h2 id="passport-workflow-title">Текущий этап Workflow</h2><span className={styles.sectionHint}>Статус прохождения onboarding-процесса</span></div><button className={styles.textAction} type="button" onClick={() => onTabChange('workflow')}>Открыть Workflow <ArrowRight size={14} fill="currentColor" /></button></div>
      <div className={styles.workflowLayout}>
        <div className={styles.workflowStage}><span className={styles.overline}>Текущий этап</span><strong>{workflow.currentStage.name}</strong><span className={`${styles.workflowStatus} ${styles[`workflow-${workflow.status}`]}`}>{statusLabel}</span></div>
        <div className={styles.workflowDetails}>
          <div><span className={styles.detailLabel}>Deadline</span><strong className={overdue ? styles.overdue : undefined}><TimeStroke size={16} fill="currentColor" />{formatDate(workflow.deadline)}</strong>{overdue ? <span className={styles.detailWarning}>Срок просрочен</span> : null}</div>
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
  return <li className={styles.timelineItem}><span className={styles.timelineIcon} aria-hidden="true"><EventIcon type={event.type} /></span><div className={styles.timelineBody}><time dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time><p>{event.description}</p></div></li>;
}

function RecentInteractions({ events, onTabChange }: { events: UniversityPassportEvent[]; onTabChange: (tab: PassportTabId) => void }) {
  return (
    <section className={styles.timelineCard} aria-labelledby="passport-timeline-title">
      <div className={styles.sectionHeading}><div><h2 id="passport-timeline-title">Последние взаимодействия</h2><span className={styles.sectionHint}>Последние события по вузу</span></div><Button variant="ghost" size="s" type="button" onClick={() => onTabChange('history')}>Показать всё <ArrowRight size={14} fill="currentColor" /></Button></div>
      <ol className={styles.timeline}>{events.slice(0, 5).map((event) => <TimelineItem event={event} key={event.id} />)}</ol>
    </section>
  );
}

function OverviewContent({ passport, canAdvance, onTabChange }: { passport: UniversityPassport; canAdvance: boolean; onTabChange: (tab: PassportTabId) => void }) {
  return <div className={styles.overviewContent}><OverviewMetrics passport={passport} /><WorkflowOverview passport={passport} canAdvance={canAdvance} onTabChange={onTabChange} /><RecentInteractions events={passport.timeline} onTabChange={onTabChange} /></div>;
}

function PlaceholderContent({ tab }: { tab: (typeof tabDefinitions)[number] }) {
  return <section className={styles.placeholderPanel} aria-labelledby={`${tab.id}-placeholder-title`}><span className={styles.placeholderIcon} aria-hidden="true"><StatisticsBoard size={24} fill="currentColor" /></span><h2 id={`${tab.id}-placeholder-title`}>{tab.label}</h2><p>Раздел подготовлен в структуре паспорта. Бизнес-данные подключатся в следующем frontend-модуле.</p></section>;
}

function PassportSkeleton() {
  return <div className={styles.skeletonPage} aria-live="polite" aria-busy="true"><span className={styles.skeletonLine} /><span className={`${styles.skeletonLine} ${styles.skeletonTitle}`} /><div className={styles.skeletonHeader} /><div className={styles.skeletonMetrics}>{Array.from({ length: 4 }, (_, index) => <span className={styles.skeletonCard} key={index} />)}</div><span className={`${styles.skeletonLine} ${styles.skeletonSection}`} /><div className={styles.skeletonBlock} /><div className={styles.skeletonBlock} /></div>;
}

export function UniversityPassport({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const activeTab = parseTab(searchParams.get('tab'));
  const query = useQuery({ queryKey: passportQueryKey(id), queryFn: () => getUniversityPassport(id), staleTime: 30_000 });
  const canEdit = user?.role === 'admin';
  const canReport = user?.role === 'admin' || user?.role === 'manager';
  const canAdvance = canReport;
  const activeTabDefinition = useMemo(() => tabDefinitions.find((tab) => tab.id === activeTab) ?? tabDefinitions[0], [activeTab]);

  const selectTab = (tab: PassportTabId) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('tab', tab);
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  };

  if (query.isPending) return <PassportSkeleton />;
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
    : <PlaceholderContent tab={tabDefinitions.find((definition) => definition.id === tab) ?? activeTabDefinition} />;

  return (
    <div className={styles.page}>
      <PassportHeader passport={passport} canEdit={canEdit} canReport={canReport} onTabChange={selectTab} />
      <nav className={styles.desktopTabs} aria-label="Разделы паспорта вуза">
        <div className={styles.tabList} role="tablist">
          {tabDefinitions.map((tab) => <button className={activeTab === tab.id ? styles.tabActive : styles.tab} id={`passport-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls="passport-panel" key={tab.id} onClick={() => selectTab(tab.id)}>{tab.label}</button>)}
        </div>
      </nav>
      <div className={styles.desktopPanel} id="passport-panel" role="tabpanel" aria-labelledby={`passport-tab-${activeTab}`}>{renderContent(activeTab)}</div>
      <div className={styles.mobileAccordion} aria-label="Разделы паспорта вуза">
        {tabDefinitions.map((tab) => {
          const isOpen = activeTab === tab.id;
          return <section className={styles.accordionItem} key={tab.id}><button className={isOpen ? styles.accordionTriggerActive : styles.accordionTrigger} type="button" aria-expanded={isOpen} onClick={() => selectTab(tab.id)}><span>{tab.label}</span><ArrowRight size={18} fill="currentColor" /></button>{isOpen ? <div className={styles.accordionPanel}>{renderContent(tab.id)}</div> : null}</section>;
        })}
      </div>
    </div>
  );
}

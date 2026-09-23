'use client';

import Link from 'next/link';
import type { ComponentType } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Attachment from '@atomaro/icons/24/action/Attachment';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import Comments from '@atomaro/icons/24/communication/Comments';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import History from '@atomaro/icons/24/communication/History';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import SkipStroke from '@atomaro/icons/24/alert/SkipStroke';
import Task from '@atomaro/icons/24/communication/Task';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateRu, formatDateTimeRu, getRelativeDueDateRu } from '@/shared/lib/formatters';
import { workflowStageStatusSemantics, type WorkflowStageIcon } from '@/shared/lib/status-semantics';
import { getUniversityWorkflow, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowStage, type UniversityWorkflowStageStatus } from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Toast } from '@/shared/ui/rtk/toast';
import { WorkflowComments } from './workflow-comments';
import { WorkflowAttachments } from './workflow-attachments';
import { WorkflowTransitionModal, type WorkflowTransitionNotification } from './workflow-transition-modal';
import styles from './university-workflow.module.css';

export type WorkflowViewMode = 'page' | 'embedded';

const statusIcons: Record<WorkflowStageIcon, ComponentType<{ size?: number; fill?: string }>> = {
  check: CheckLarge,
  information: InformationStroke,
  time: TimeStroke,
  skip: SkipStroke,
  error: ErrorStroke,
};

function getInitials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('ru-RU') || '—';
}

function StageStatusIcon({ status, size = 16 }: { status: UniversityWorkflowStageStatus; size?: number }) {
  const Icon = statusIcons[workflowStageStatusSemantics[status].icon];
  return <Icon size={size} fill="currentColor" />;
}

function StageDeadline({ stage }: { stage: UniversityWorkflowStage }) {
  const relative = getRelativeDueDateRu(stage.deadline);
  const isOverdue = stage.status === 'overdue';
  const showRelative = stage.status === 'current' || stage.status === 'pending' || isOverdue;
  const relativeLabel = isOverdue ? relative.overdueLabel ?? relative.label : relative.label;
  const dueSoon = !isOverdue ? relative.dueSoonLabel : null;
  return (
    <span className={`${styles.stageDeadline} ${isOverdue ? styles.overdue : ''}`}>
      <span><TimeStroke size={14} fill="currentColor" /><time dateTime={stage.deadline}>{formatDateRu(stage.deadline)}</time></span>
      {showRelative ? <small className={dueSoon ? styles.dueSoon : undefined}>{dueSoon ?? relativeLabel}</small> : null}
    </span>
  );
}

function StageAssignee({ stage }: { stage: UniversityWorkflowStage }) {
  const responsible = stage.responsible;
  if (!responsible) return <span className={`${styles.stageResponsible} ${styles.unassigned}`}>Не назначен</span>;
  const email = responsible.email ?? 'Email не указан';
  const role = responsible.role ?? 'Роль не указана';
  return (
    <Tooltip content={<><strong>{responsible.name}</strong><span>{email}</span><span>{role}</span></>}>
      <span className={styles.assigneeTrigger} tabIndex={0} aria-label={`Ответственный: ${responsible.name}. ${email}. ${role}`}>
        <Avatar initials={getInitials(responsible.name)} size="s" />
        <span>{responsible.name}</span>
      </span>
    </Tooltip>
  );
}

function StageSummary({ stage }: { stage: UniversityWorkflowStage }) {
  const completedTasks = stage.tasks.filter((task) => task.completed).length;
  const items = [
    { key: 'comments', icon: Comments, label: 'Комментарии', value: String(stage.comments.length) },
    { key: 'attachments', icon: Attachment, label: 'Вложения', value: String(stage.attachments.length) },
    { key: 'tasks', icon: Task, label: 'Задачи', value: `${completedTasks}/${stage.tasks.length}` },
  ];
  if (!items.some((item) => item.value !== '0' && item.value !== `0/${stage.tasks.length}`)) return null;
  return <div className={styles.stageSummary} aria-label="Сводка этапа">{items.map(({ key, icon: Icon, label, value }) => <span key={key}><Icon size={14} fill="currentColor" /><span>{label} {value}</span></span>)}</div>;
}

function WorkflowStageItem({ stage, selected, detailsId, onSelect }: { stage: UniversityWorkflowStage; selected: boolean; detailsId: string; onSelect: () => void }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const titleClass = semantics.titleDecoration === 'strike' ? styles.stageTitleMuted : undefined;
  return (
    <li className={`${styles.stageItem} ${selected ? styles.stageItemSelected : ''} ${semantics.muted ? styles.stageItemMuted : ''}`}>
      <button className={`${styles.stageButton} ${semantics.emphasis === 'current' ? styles.stageButtonCurrent : ''} ${semantics.emphasis === 'error' ? styles.stageButtonError : ''}`} type="button" aria-expanded={selected} aria-controls={detailsId} aria-current={stage.status === 'current' ? 'step' : undefined} onClick={onSelect}>
        <span className={`${styles.stageMarker} ${styles[`status-${stage.status}`]}`} aria-hidden="true"><StageStatusIcon status={stage.status} /></span>
        <span className={styles.stageContent}>
          <span className={styles.stageTopline}><span className={styles.stageOrder}>{stage.orderIndex}</span><strong className={titleClass}>{stage.name}</strong></span>
          <span className={styles.stageMeta}><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge><StageDeadline stage={stage} /></span>
          <StageAssignee stage={stage} />
          <StageSummary stage={stage} />
        </span>
      </button>
    </li>
  );
}

type WorkflowAction = { label: string; variant: 'primary' | 'secondary'; title: string };

function getStageActions(stage: UniversityWorkflowStage, canManage: boolean, canRestore: boolean): WorkflowAction[] {
  if (stage.status === 'current' && canManage) return [
    { label: 'Перевести на следующий этап', variant: 'primary', title: 'Переход подключится после появления API' },
    { label: 'Добавить комментарий', variant: 'secondary', title: 'Добавление комментариев подключится после появления API' },
    { label: 'Добавить файл', variant: 'secondary', title: 'Загрузка файлов подключится после появления API' },
  ];
  if (stage.status === 'overdue' && canManage) return [
    { label: 'Перевести', variant: 'primary', title: 'Переход подключится после появления API' },
    { label: 'Эскалация', variant: 'secondary', title: 'Эскалация подключится после появления API' },
  ];
  if (stage.status === 'pending' && !stage.responsible && canManage) return [
    { label: 'Назначить ответственного', variant: 'primary', title: 'Назначение подключится после появления API' },
  ];
  if (stage.status === 'skipped' && canRestore) return [
    { label: 'Восстановить', variant: 'secondary', title: 'Восстановление подключится после появления API' },
  ];
  return [];
}

function StageActionPanel({ stage, stages, instanceId, universityId, userId, canManage, canRestore, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; canRestore: boolean; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const [transitionContext, setTransitionContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const actions = getStageActions(stage, canManage, canRestore);
  const transitionAction = actions.find((action) => action.label === 'Перевести на следующий этап');
  if (!actions.length && !transitionContext) return null;
  return <div className={styles.stageAction} aria-label="Действия этапа"><div className={styles.stageActionButtons}>{actions.map((action) => { const canOpenTransition = action === transitionAction; return <Button key={action.label} variant={action.variant} size="s" type="button" disabled={!canOpenTransition} title={canOpenTransition ? undefined : action.title} onClick={canOpenTransition ? () => { onTransitionOpen(); setTransitionContext({ currentStage: stage, stages }); } : undefined}>{action.label}</Button>; })}</div>{transitionAction ? <span>Комментарий и подтверждение обязательны для перехода.</span> : <span>Действия станут доступны после подключения API.</span>}{transitionContext ? <WorkflowTransitionModal open instanceId={instanceId} universityId={universityId} currentStage={transitionContext.currentStage} stages={transitionContext.stages} userId={userId} onClose={() => { setTransitionContext(null); onTransitionClose(); }} onSuccess={() => { setTransitionContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}</div>;
}

function CompletionSummary({ stage }: { stage: UniversityWorkflowStage }) {
  if (stage.status !== 'completed' || !stage.completedAt || !stage.completion) return null;
  const onTime = stage.completion === 'on_time';
  return <div className={`${styles.completionSummary} ${onTime ? styles.completionOnTime : styles.completionLate}`}><span aria-hidden="true">{onTime ? <CheckLarge size={16} fill="currentColor" /> : <ErrorStroke size={16} fill="currentColor" />}</span><span>{onTime ? 'Выполнено вовремя' : 'Завершено после дедлайна'}</span><time dateTime={stage.completedAt}>Завершено: {formatDateTimeRu(stage.completedAt)}</time></div>;
}

function WorkflowStageDetails({ stage, stages, instanceId, universityId, userId, canManage, canRestore, idPrefix, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; canRestore: boolean; idPrefix: string; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const completedTasks = stage.tasks.filter((task) => task.completed).length;
  const taskProgress = stage.tasks.length ? Math.round((completedTasks / stage.tasks.length) * 100) : 0;
  const headingId = `${idPrefix}-stage-details-title`;
  return (
    <section className={`${styles.detailPanel} ${styles[`detail-${stage.status}`]}`} aria-labelledby={headingId} id={idPrefix}>
      <div className={styles.detailHeader}><div><span className={styles.eyebrow}>Детали этапа {stage.orderIndex} из 14</span><h2 id={headingId}>{stage.name}</h2></div><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge></div>
      <CompletionSummary stage={stage} />
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-overview-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-overview-title`}><InformationStroke size={18} fill="currentColor" />Основная информация</h3></div><dl className={styles.detailFacts}><div><dt>{stage.status === 'completed' ? 'Дедлайн был' : 'Дедлайн'}</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><StageDeadline stage={stage} /></dd></div>{stage.startedAt ? <div><dt>Начат</dt><dd><time dateTime={stage.startedAt}>{formatDateTimeRu(stage.startedAt)}</time></dd></div> : null}{stage.completedAt && stage.status !== 'completed' ? <div><dt>Завершён</dt><dd><time dateTime={stage.completedAt}>{formatDateTimeRu(stage.completedAt)}</time></dd></div> : null}<div><dt>Ответственный</dt><dd><StageAssignee stage={stage} /></dd></div></dl></section>
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-tasks-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-tasks-title`}><Task size={18} fill="currentColor" />Задачи этапа</h3><span className={styles.taskCount}>Выполнено {completedTasks} из {stage.tasks.length}</span></div><div className={styles.taskProgress} role="progressbar" aria-label={`Задачи этапа: выполнено ${completedTasks} из ${stage.tasks.length}`} aria-valuemin={0} aria-valuemax={stage.tasks.length} aria-valuenow={completedTasks}><span style={{ width: `${taskProgress}%` }} /></div><ul className={styles.taskList}>{stage.tasks.map((task) => <li key={task.id}><label><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></label></li>)}</ul></section>
      <WorkflowComments instanceId={instanceId} stageId={stage.templateStageId ?? stage.id} comments={stage.comments} onNotify={onNotify} />
      <WorkflowAttachments instanceId={instanceId} attachments={stage.attachments} />
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-transition-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-transition-title`}><History size={18} fill="currentColor" />История переходов</h3></div>{stage.transitions.length ? <ol className={styles.transitionList}>{stage.transitions.map((transition) => <li key={transition.id}><div><strong>{transition.actor}</strong><time dateTime={transition.occurredAt}>{formatDateTimeRu(transition.occurredAt)}</time></div><p>{workflowStageStatusSemantics[transition.fromStatus].label} → {workflowStageStatusSemantics[transition.toStatus].label}. {transition.comment}</p></li>)}</ol> : <p className={styles.muted}>Переходов пока нет</p>}</section>
      <StageActionPanel stage={stage} stages={stages} instanceId={instanceId} universityId={universityId} userId={userId} canManage={canManage} canRestore={canRestore} onTransitionOpen={onTransitionOpen} onTransitionClose={onTransitionClose} onTransitionSuccess={onTransitionSuccess} onNotify={onNotify} />
    </section>
  );
}

function WorkflowHeader({ workflow }: { workflow: UniversityWorkflow }) {
  const currentStage = workflow.currentStage;
  const currentSemantics = currentStage ? workflowStageStatusSemantics[currentStage.status] : null;
  const progress = workflow.totalSteps ? Math.round((workflow.completedSteps / workflow.totalSteps) * 100) : 0;
  return (
    <header className={styles.pageHeader}>
      <nav className={styles.breadcrumbs} aria-label="Навигация Workflow"><Link href="/universities">ВУЗы</Link><span aria-hidden="true">/</span><Link href={`/universities/${workflow.universityId}?tab=workflow`}>{workflow.universityName}</Link><span aria-hidden="true">/</span><span>Workflow</span></nav>
      <div className={styles.headerMain}><div><p className={styles.eyebrow}>WORKFLOW</p><h1>Взаимодействие с вузом</h1><p className={styles.headerContext}>{workflow.universityName} · {workflow.universityCity} · {workflow.workflowName}</p></div>{currentStage && currentSemantics ? <div className={styles.headerCurrent}><span>Текущий этап</span><strong>{currentStage.name}</strong><StatusBadge intent={currentSemantics.intent} icon={<StageStatusIcon status={currentStage.status} />}>{currentSemantics.label}</StatusBadge></div> : null}</div>
      <div className={styles.overallProgress}><div className={styles.progressLabel}><span>Прогресс Workflow</span><strong>{workflow.completedSteps} из {workflow.totalSteps} этапов завершено</strong></div><div className={styles.progressTrack} role="progressbar" aria-label={`Прогресс Workflow: завершено ${workflow.completedSteps} из ${workflow.totalSteps} этапов`} aria-valuemin={0} aria-valuemax={workflow.totalSteps} aria-valuenow={workflow.completedSteps}><span style={{ width: `${progress}%` }} /></div></div>
    </header>
  );
}

function WorkflowSkeleton({ mode }: { mode: WorkflowViewMode }) {
  return <div className={`${styles.skeleton} ${mode === 'page' ? styles.skeletonPage : ''}`} aria-live="polite" aria-busy="true">{mode === 'page' ? <div className={styles.skeletonHeader}><span /><span /><span /></div> : null}<div className={styles.skeletonLayout}><div className={styles.skeletonStages}>{Array.from({ length: 8 }, (_, index) => <span key={index} />)}</div><div className={styles.skeletonDetails}><span /><span /><span /><span /></div></div></div>;
}

function WorkflowEmptyState() {
  return <div className={styles.emptyState} role="status"><InformationStroke size={22} fill="currentColor" /><p>Этапы Workflow пока не добавлены</p></div>;
}

export function WorkflowView({ instanceId, mode, canAdvance: canAdvanceOverride }: { instanceId: string; mode: WorkflowViewMode; canAdvance?: boolean }) {
  const { user } = useAuth();
  const query = useQuery({ queryKey: workflowQueryKey(instanceId), queryFn: () => getUniversityWorkflow(instanceId), staleTime: 30_000 });
  const canManage = canAdvanceOverride ?? (user?.role === 'admin' || user?.role === 'manager');
  const canRestore = user?.role === 'admin';
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notification, setNotification] = useState<WorkflowTransitionNotification | null>(null);
  useEffect(() => {
    if (!notification) return undefined;
    const timer = window.setTimeout(() => setNotification(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notification]);
  const stages = useMemo(() => query.data?.stages.slice().sort((left, right) => left.orderIndex - right.orderIndex) ?? [], [query.data]);
  const selectedStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === selectedId) ?? stages.find((stage) => stage.status === 'current') ?? query.data?.currentStage ?? stages[0];
  }, [query.data?.currentStage, selectedId, stages]);
  const idPrefix = `workflow-${instanceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const detailsId = `${idPrefix}-details`;

  if (query.isPending) return <WorkflowSkeleton mode={mode} />;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  if (!stages.length || !selectedStage) return <WorkflowEmptyState />;

  return <div className={`${styles.page} ${mode === 'embedded' ? styles.embedded : ''}`}>{mode === 'page' ? <WorkflowHeader workflow={query.data} /> : null}<div className={styles.layout}><section className={styles.stagesPanel} aria-labelledby={`${idPrefix}-stages-title`}><div className={styles.panelHeading}><div><span className={styles.eyebrow}>Жизненный цикл проекта</span><h2 id={`${idPrefix}-stages-title`}>Этапы Workflow</h2></div><span className={styles.totalLabel}>{stages.length} этапов</span></div><ol className={styles.stageList}>{stages.map((stage) => <WorkflowStageItem key={stage.id} stage={stage} selected={stage.id === selectedStage.id} detailsId={detailsId} onSelect={() => setSelectedId(stage.id)} />)}</ol></section><WorkflowStageDetails key={selectedStage.id} stage={selectedStage} stages={stages} instanceId={instanceId} universityId={query.data.universityId} userId={user?.id} canManage={canManage} canRestore={canRestore} idPrefix={detailsId} onTransitionOpen={() => setSelectedId(selectedStage.id)} onTransitionClose={() => setSelectedId(null)} onTransitionSuccess={() => setSelectedId(null)} onNotify={setNotification} /></div>{notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}</div>;
}

export function UniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  return <WorkflowView instanceId={id} mode="embedded" canAdvance={canAdvance} />;
}

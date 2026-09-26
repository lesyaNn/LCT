'use client';

import type { ComponentType } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { hasPermission, hasRole } from '@/shared/lib/access-control';
import type { WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { formatDateRu, formatDateTimeRu, getRelativeDueDateRu } from '@/shared/lib/formatters';
import { workflowStageStatusSemantics, type WorkflowStageIcon } from '@/shared/lib/status-semantics';
import { createProgramWorkflow, getUniversityWorkflow, getWorkflowByProgram, getApiUniversityWorkflow, getWorkflowAllowedTransitions, isRealWorkflowMode, listWorkflowTasksPage, listWorkflowAttachmentsPage, listWorkflowHistory, workflowByProgramQueryKey, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowAttachment, type UniversityWorkflowStage, type UniversityWorkflowStageStatus, type UniversityWorkflowTask } from '@/shared/lib/universities-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { workflowAttachmentFromApi } from '@/shared/lib/workflow-attachments';
import { getWorkflowSelectorPrograms, workflowProgramsQueryKey } from '@/shared/lib/universities-repository';
import { listWorkflowTemplates, workflowTemplateListQueryKey } from '@/shared/lib/workflow-templates-repository';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { getUniversityExternalData, universityExternalDataQueryKey } from '@/shared/lib/external-integrations-repository';
import { Select } from '@/shared/ui/rtk/form-controls';
import { FilterField } from '@/shared/ui/rtk/filter-field';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { ListSkeleton, Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
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
  const completedTasks = stage.taskCompleted ?? stage.tasks.filter((task) => task.completed).length;
  const totalTasks = stage.taskTotal ?? stage.tasks.length;
  const items = [
    { key: 'comments', icon: Comments, label: 'Комментарии', value: String(stage.comments.length) },
    { key: 'attachments', icon: Attachment, label: 'Вложения', value: String(stage.attachments.length) },
    { key: 'tasks', icon: Task, label: 'Задачи', value: `${completedTasks}/${totalTasks}` },
  ];
  if (!stage.comments.length && !stage.attachments.length && !totalTasks) return null;
  return <div className={styles.stageSummary} aria-label="Сводка этапа">{items.map(({ key, icon: Icon, label, value }) => <span key={key}><Icon size={14} fill="currentColor" /><span>{label} {value}</span></span>)}</div>;
}

function WorkflowStageItem({ stage, selected, detailsId, onSelect }: { stage: UniversityWorkflowStage; selected: boolean; detailsId: string; onSelect: () => void }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const titleClass = semantics.titleDecoration === 'strike' ? styles.stageTitleMuted : undefined;
  return (
    <li className={`${styles.stageItem} ${selected ? styles.stageItemSelected : ''} ${semantics.muted ? styles.stageItemMuted : ''}`}>
      <button className={`${styles.stageButton} ${semantics.emphasis === 'current' ? styles.stageButtonCurrent : ''} ${semantics.emphasis === 'error' ? styles.stageButtonError : ''}`} type="button" aria-expanded={selected} aria-controls={detailsId} aria-current={stage.status === 'current' ? 'step' : undefined} data-testid={stage.status === 'current' ? 'workflow-current-stage' : undefined} onClick={onSelect}>
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

type WorkflowAction = { label: string; variant: 'primary' | 'secondary' };

function getStageActions(stage: UniversityWorkflowStage, canManage: boolean): WorkflowAction[] {
  if ((stage.status === 'current' || stage.status === 'overdue') && canManage) return [
    { label: 'Перевести на следующий этап', variant: 'primary' },
  ];
  return [];
}

function StageActionPanel({ stage, stages, instanceId, universityId, userId, canManage, allowedTargets, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; allowedTargets?: WorkflowTransitionTarget[]; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const [transitionContext, setTransitionContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const actions = getStageActions(stage, canManage && (allowedTargets === undefined || allowedTargets.length > 0));
  const transitionAction = actions.find((action) => action.label.startsWith('Перевести'));
  if (!actions.length && !transitionContext) return null;
  return <div className={styles.stageAction} aria-label="Действия этапа"><div className={styles.stageActionButtons}>{actions.map((action) => { const canOpenTransition = action === transitionAction; return <Button key={action.label} variant={action.variant} size="s" type="button" disabled={!canOpenTransition} onClick={canOpenTransition ? () => { onTransitionOpen(); setTransitionContext({ currentStage: stage, stages }); } : undefined}>{action.label}</Button>; })}</div><span>Комментарий и подтверждение обязательны для перехода.</span>{transitionContext ? <WorkflowTransitionModal open instanceId={instanceId} universityId={universityId} currentStage={transitionContext.currentStage} stages={transitionContext.stages} allowedTargets={allowedTargets} userId={userId} onClose={() => { setTransitionContext(null); onTransitionClose(); }} onSuccess={() => { setTransitionContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}</div>;
}

function CompletionSummary({ stage }: { stage: UniversityWorkflowStage }) {
  if (stage.status !== 'completed' || !stage.completedAt || !stage.completion) return null;
  const onTime = stage.completion === 'on_time';
  return <div className={`${styles.completionSummary} ${onTime ? styles.completionOnTime : styles.completionLate}`}><span aria-hidden="true">{onTime ? <CheckLarge size={16} fill="currentColor" /> : <ErrorStroke size={16} fill="currentColor" />}</span><span>{onTime ? 'Выполнено вовремя' : 'Завершено после дедлайна'}</span><time dateTime={stage.completedAt}>Завершено: {formatDateTimeRu(stage.completedAt)}</time></div>;
}

type WorkflowResourceState = { loading: boolean; error: boolean; retry: () => void; hasMore?: boolean; loadingMore?: boolean; loadMore?: () => void };

function WorkflowStageDetails({ stage, stages, instanceId, universityId, userId, canManage, idPrefix, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify, tasksState, attachmentsState, historyState, allowedState, allowedTargets }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; idPrefix: string; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void; tasksState?: WorkflowResourceState; attachmentsState?: WorkflowResourceState; historyState?: WorkflowResourceState; allowedState?: WorkflowResourceState; allowedTargets?: WorkflowTransitionTarget[] }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const completedTasks = stage.taskCompleted ?? stage.tasks.filter((task) => task.completed).length;
  const totalTasks = stage.taskTotal ?? stage.tasks.length;
  const taskProgress = totalTasks ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const headingId = `${idPrefix}-stage-details-title`;
  return (
    <section className={`${styles.detailPanel} ${styles[`detail-${stage.status}`]}`} aria-labelledby={headingId} id={idPrefix}>
      <div className={styles.detailHeader}><div><h2 id={headingId}>{stage.name}</h2></div><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge></div>
      <CompletionSummary stage={stage} />
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-overview-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-overview-title`}><InformationStroke size={18} fill="currentColor" />Основная информация</h3></div><dl className={styles.detailFacts}><div><dt>{stage.status === 'completed' ? 'Дедлайн был' : 'Дедлайн'}</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><StageDeadline stage={stage} /></dd></div>{stage.startedAt ? <div><dt>Начат</dt><dd><time dateTime={stage.startedAt}>{formatDateTimeRu(stage.startedAt)}</time></dd></div> : null}{stage.completedAt && stage.status !== 'completed' ? <div><dt>Завершён</dt><dd><time dateTime={stage.completedAt}>{formatDateTimeRu(stage.completedAt)}</time></dd></div> : null}<div><dt>Ответственный</dt><dd><StageAssignee stage={stage} /></dd></div></dl></section>
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-tasks-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-tasks-title`}><Task size={18} fill="currentColor" />Задачи этапа</h3><span className={styles.taskCount}>Выполнено {completedTasks} из {totalTasks}</span></div>{tasksState?.loading ? <ListSkeleton items={3} /> : tasksState?.error ? <ErrorState title="Не удалось загрузить задачи" headingLevel={3} onRetry={tasksState.retry} /> : <><div className={styles.taskProgress} role="progressbar" aria-label={`Задачи этапа: выполнено ${completedTasks} из ${totalTasks}`} aria-valuemin={0} aria-valuemax={totalTasks} aria-valuenow={completedTasks}><span style={{ width: `${taskProgress}%` }} /></div><ul className={styles.taskList}>{stage.tasks.map((task) => <li key={task.id}><label><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></label></li>)}</ul>{tasksState?.hasMore ? <Button variant="ghost" size="s" type="button" loading={tasksState.loadingMore} onClick={tasksState.loadMore}>Загрузить ещё задачи</Button> : null}</>}</section>
      <WorkflowComments instanceId={instanceId} stageId={stage.templateStageId ?? stage.id} comments={stage.comments} readOnly={stage.status !== 'current' && stage.status !== 'overdue'} onNotify={onNotify} />
      {attachmentsState?.loading ? <ListSkeleton items={2} /> : attachmentsState?.error ? <ErrorState title="Не удалось загрузить вложения" headingLevel={3} onRetry={attachmentsState.retry} /> : <><WorkflowAttachments instanceId={instanceId} stageId={stage.id} attachments={stage.attachments} readOnly={stage.status !== 'current' && stage.status !== 'overdue'} onNotify={onNotify} />{attachmentsState?.hasMore ? <Button variant="ghost" size="s" type="button" loading={attachmentsState.loadingMore} onClick={attachmentsState.loadMore}>Загрузить ещё вложения</Button> : null}</>}
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-transition-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-transition-title`}><History size={18} fill="currentColor" />История переходов</h3></div>{historyState?.loading ? <ListSkeleton items={2} /> : historyState?.error ? <ErrorState title="Не удалось загрузить историю" headingLevel={3} onRetry={historyState.retry} /> : stage.transitions.length ? <ol className={styles.transitionList}>{stage.transitions.map((transition) => <li key={transition.id}><div><strong>{transition.actor}</strong><time dateTime={transition.occurredAt}>{formatDateTimeRu(transition.occurredAt)}</time></div><p>{transition.description ?? `${workflowStageStatusSemantics[transition.fromStatus].label} → ${workflowStageStatusSemantics[transition.toStatus].label}`}. {transition.comment}</p></li>)}</ol> : <EmptyState title="Переходов пока нет" description="История появится после первого изменения этапа." headingLevel={3} />}</section>
      {allowedState ? <section className={styles.detailSection} aria-labelledby={`${idPrefix}-allowed-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-allowed-title`}>Доступные переходы</h3></div>{allowedState.loading ? <ListSkeleton items={1} /> : allowedState.error ? <ErrorState title="Не удалось загрузить доступные переходы" headingLevel={3} onRetry={allowedState.retry} /> : <p>{allowedTargets?.length ? allowedTargets.map((item) => item.name).join(', ') : 'Нет доступных переходов.'}</p>}</section> : null}
      <StageActionPanel stage={stage} stages={stages} instanceId={instanceId} universityId={universityId} userId={userId} canManage={canManage} allowedTargets={allowedTargets} onTransitionOpen={onTransitionOpen} onTransitionClose={onTransitionClose} onTransitionSuccess={onTransitionSuccess} onNotify={onNotify} />
    </section>
  );
}

function WorkflowHeader({ workflow }: { workflow: UniversityWorkflow }) {
  const currentStage = workflow.currentStage;
  const currentSemantics = currentStage ? workflowStageStatusSemantics[currentStage.status] : null;
  const progress = workflow.totalSteps ? Math.round((workflow.completedSteps / workflow.totalSteps) * 100) : 0;
  return (
    <header className={styles.pageHeader}>
      <div className={styles.headerMain}><div><h1>Взаимодействие с вузом</h1><p className={styles.headerContext}>{[workflow.universityName, workflow.universityCity, workflow.workflowName].filter((part, index, parts) => part && parts.findIndex((other) => other.toLocaleLowerCase('ru-RU') === part.toLocaleLowerCase('ru-RU')) === index).join(' · ')}</p></div>{currentStage && currentSemantics ? <div className={styles.headerCurrent}><span>Текущий этап</span><strong>{currentStage.name}</strong><StatusBadge intent={currentSemantics.intent} icon={<StageStatusIcon status={currentStage.status} />}>{currentSemantics.label}</StatusBadge></div> : null}</div>
      <div className={styles.overallProgress}><div className={styles.progressLabel}><span>Прогресс Workflow</span><strong>{workflow.completedSteps} из {workflow.totalSteps} этапов завершено</strong></div><div className={styles.progressTrack} role="progressbar" aria-label={`Прогресс Workflow: завершено ${workflow.completedSteps} из ${workflow.totalSteps} этапов`} aria-valuemin={0} aria-valuemax={workflow.totalSteps} aria-valuenow={workflow.completedSteps}><span style={{ width: `${progress}%` }} /></div></div>
    </header>
  );
}

function WorkflowSkeleton({ mode }: { mode: WorkflowViewMode }) {
  return <SkeletonGroup label="Загрузка Workflow">{mode === 'page' ? <><Skeleton variant="text" width="220px" /><Skeleton variant="text" width="min(72%, 520px)" height={36} /><Skeleton height={96} /></> : null}<div className={styles.skeletonLayout}><ListSkeleton items={6} withAvatar /><Skeleton height={520} /></div></SkeletonGroup>;
}

function WorkflowGlobalResources({ instanceId, tasks, attachments, readOnly }: { instanceId: string; tasks: UniversityWorkflowTask[]; attachments: UniversityWorkflowAttachment[]; readOnly: boolean }) {
  if (!tasks.length && !attachments.length) return null;
  return <section className={styles.detailSection} aria-label="Общие материалы Workflow">
    <h2>Общие материалы Workflow</h2>
    {tasks.length ? <><h3>Задачи без привязки к этапу</h3><ul className={styles.taskList}>{tasks.map((task) => <li key={task.id}><label><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></label></li>)}</ul></> : null}
    {attachments.length ? <WorkflowAttachments instanceId={instanceId} stageId="general" attachments={attachments} readOnly={readOnly} /> : null}
  </section>;
}

export function WorkflowView({ instanceId, mode, canAdvance: canAdvanceOverride }: { instanceId: string; mode: WorkflowViewMode; canAdvance?: boolean }) {
  const { user } = useAuth();
  const realWorkflow = isRealWorkflowMode();
  const query = useQuery({ queryKey: workflowQueryKey(instanceId), queryFn: () => getUniversityWorkflow(instanceId), staleTime: 30_000 });
  const tasksQuery = useInfiniteQuery({ queryKey: queryKeys.universities.workflowTasks(instanceId), queryFn: ({ pageParam }) => listWorkflowTasksPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const attachmentsQuery = useInfiniteQuery({ queryKey: queryKeys.universities.workflowAttachments(instanceId), queryFn: ({ pageParam }) => listWorkflowAttachmentsPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const historyQuery = useQuery({ queryKey: queryKeys.universities.workflowHistory(instanceId), queryFn: () => listWorkflowHistory(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const allowedQuery = useQuery({ queryKey: queryKeys.universities.workflowAllowed(instanceId), queryFn: () => getWorkflowAllowedTransitions(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const canManage = realWorkflow ? hasPermission(user, 'workflow.change_status') : (canAdvanceOverride ?? (user?.role === 'admin' || user?.role === 'manager'));
  const allowedTargets = realWorkflow ? allowedQuery.data?.map((item) => ({ id: item.id, orderIndex: item.order_index, name: item.name })) ?? [] : undefined;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notification, setNotification] = useState<WorkflowTransitionNotification | null>(null);
  useEffect(() => {
    if (!notification) return undefined;
    const timer = window.setTimeout(() => setNotification(null), 5000);
    return () => window.clearTimeout(timer);
  }, [notification]);
  const stages = useMemo(() => query.data?.stages.map((stage) => realWorkflow ? {
    ...stage,
    tasks: (tasksQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((task) => task.stage_id === stage.templateStageId).map((task) => ({ id: task.id, label: task.title, completed: task.status === 'done' })),
    attachments: (attachmentsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((attachment) => attachment.stage_id === stage.templateStageId).map((attachment) => workflowAttachmentFromApi(attachment, null)),
    transitions: (historyQuery.data ?? []).filter((event) => event.from_stage_id === stage.templateStageId || event.to_stage_id === stage.templateStageId).map((event) => ({ id: event.id, occurredAt: event.created_at, actor: event.actor_keycloak_sub, fromStatus: event.from_stage_id ? 'completed' as const : 'pending' as const, toStatus: event.to_stage_id ? 'current' as const : 'completed' as const, comment: event.comment, description: `${query.data.stages.find((row) => row.templateStageId === event.from_stage_id)?.name ?? 'Создание'} → ${query.data.stages.find((row) => row.templateStageId === event.to_stage_id)?.name ?? 'Завершение'}` })),
  } : stage).sort((left, right) => left.orderIndex - right.orderIndex) ?? [], [query.data, realWorkflow, tasksQuery.data, attachmentsQuery.data, historyQuery.data]);
  const selectedStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === selectedId) ?? stages.find((stage) => stage.id === query.data?.currentStage?.id) ?? stages[0];
  }, [query.data?.currentStage, selectedId, stages]);
  const commonTasks = useMemo(() => (tasksQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((task) => !task.stage_id).map((task) => ({ id: task.id, label: task.title, completed: task.status === 'done' })), [tasksQuery.data]);
  const commonAttachments = useMemo(() => (attachmentsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((attachment) => !attachment.stage_id).map((attachment) => workflowAttachmentFromApi(attachment, null)), [attachmentsQuery.data]);
  const idPrefix = `workflow-${instanceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const detailsId = `${idPrefix}-details`;

  if (query.isPending) return <WorkflowSkeleton mode={mode} />;
  if (!query.data) return <RouteErrorState compact={mode === 'embedded'} onRetry={() => void query.refetch()} />;
  if (!stages.length || !selectedStage) return <EmptyState presentation={mode === 'page' ? 'large' : 'compact'} icon={mode === 'embedded' ? <InformationStroke size={22} fill="currentColor" /> : undefined} title="Этапы Workflow пока не добавлены" description="Настроенные этапы появятся здесь после запуска процесса." />;

  return <div className={`${styles.page} ${mode === 'embedded' ? styles.embedded : ''}`}>
    {mode === 'page' ? <WorkflowHeader workflow={query.data} /> : null}
    <div className={styles.layout}>
      <section className={styles.stagesPanel} aria-labelledby={`${idPrefix}-stages-title`}>
        <div className={styles.panelHeading}><div><h2 id={`${idPrefix}-stages-title`}>Этапы Workflow</h2></div><span className={styles.totalLabel}>{stages.length} этапов</span></div>
        <ol className={styles.stageList}>{stages.map((stage) => <WorkflowStageItem key={stage.id} stage={stage} selected={stage.id === selectedStage.id} detailsId={detailsId} onSelect={() => setSelectedId(stage.id)} />)}</ol>
      </section>
      <WorkflowStageDetails key={selectedStage.id} stage={selectedStage} stages={stages} instanceId={instanceId} universityId={query.data.universityId} userId={user?.id} canManage={canManage} idPrefix={detailsId} onTransitionOpen={() => setSelectedId(selectedStage.id)} onTransitionClose={() => setSelectedId(null)} onTransitionSuccess={() => setSelectedId(null)} onNotify={setNotification} tasksState={realWorkflow ? { loading: tasksQuery.isPending, error: tasksQuery.isError && !tasksQuery.data, retry: () => void tasksQuery.refetch(), hasMore: tasksQuery.hasNextPage, loadingMore: tasksQuery.isFetchingNextPage, loadMore: () => void tasksQuery.fetchNextPage() } : undefined} attachmentsState={realWorkflow ? { loading: attachmentsQuery.isPending, error: attachmentsQuery.isError && !attachmentsQuery.data, retry: () => void attachmentsQuery.refetch(), hasMore: attachmentsQuery.hasNextPage, loadingMore: attachmentsQuery.isFetchingNextPage, loadMore: () => void attachmentsQuery.fetchNextPage() } : undefined} historyState={realWorkflow ? { loading: historyQuery.isPending, error: historyQuery.isError && !historyQuery.data, retry: () => void historyQuery.refetch() } : undefined} allowedTargets={allowedTargets} allowedState={realWorkflow && selectedStage.id === query.data.currentStage?.id ? { loading: allowedQuery.isPending, error: allowedQuery.isError && !allowedQuery.data, retry: () => void allowedQuery.refetch() } : undefined} />
    </div>
    {realWorkflow ? <WorkflowGlobalResources instanceId={instanceId} tasks={commonTasks} attachments={commonAttachments} readOnly={!canManage || !query.data.currentStage || query.data.currentStage.status === 'completed'} /> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}

export function UniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  const realWorkflow = isRealWorkflowMode();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const programsQuery = useQuery({ queryKey: workflowProgramsQueryKey(id), queryFn: ({ signal }) => getWorkflowSelectorPrograms(id, signal), staleTime: 30_000 });
  const externalQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'website'), queryFn: () => getUniversityExternalData(id, 'website'), enabled: !realWorkflow, staleTime: 30_000 });
  const programs = useMemo(() => {
    const base = programsQuery.data ?? [];
    if (realWorkflow) return base.map((program) => ({ key: program.id, name: program.name, instanceId: null, externalIds: [] as string[] }));
    const applications = realWorkflow ? [] : externalQuery.data?.applications ?? [];
    const result = new Map<string, { key: string; name: string; instanceId: string | null; externalIds: string[] }>();
    for (const program of base) {
      const nameKey = program.name.trim().toLocaleLowerCase('ru-RU');
      if (!result.has(nameKey)) result.set(nameKey, { key: program.id, name: program.name, instanceId: null, externalIds: [] });
    }
    for (const application of applications) {
      const nameKey = application.programName.trim().toLocaleLowerCase('ru-RU');
      const program = result.get(nameKey) ?? { key: application.id, name: application.programName, instanceId: null, externalIds: [] };
      program.externalIds.push(application.id);
      if (application.workflowInstanceId) program.instanceId = application.workflowInstanceId;
      result.set(nameKey, program);
    }
    return [...result.values()];
  }, [programsQuery.data, externalQuery.data, realWorkflow]);
  const requestedProgram = searchParams.get('program');
  const selected = programs.find((program) => program.key === requestedProgram || (requestedProgram && program.externalIds.includes(requestedProgram))) ?? programs[0];
  const [chosenTemplateId, setChosenTemplateId] = useState('');
  const workflowByProgram = useQuery({ queryKey: workflowByProgramQueryKey(id, selected?.key ?? ''), queryFn: async () => {
    const result = await getWorkflowByProgram(id, selected!.key);
    if (result) queryClient.setQueryData(workflowQueryKey(result.id), getApiUniversityWorkflow(result));
    return result;
  }, enabled: realWorkflow && Boolean(selected), staleTime: 30_000 });
  const mockInstanceId = selected && requestedProgram && (selected.key === requestedProgram || selected.externalIds.includes(requestedProgram)) ? searchParams.get('workflow') ?? selected.instanceId : selected?.instanceId;
  const instanceId = realWorkflow ? workflowByProgram.data?.id : mockInstanceId;
  const canCreate = realWorkflow && hasPermission(user, 'workflow.change_status') && hasRole(user, 'admin');
  const templatesQuery = useQuery({ queryKey: workflowTemplateListQueryKey(1, 100), queryFn: () => listWorkflowTemplates(1, 100), enabled: canCreate && Boolean(selected) && workflowByProgram.data === null, staleTime: 30_000 });
  const activeTemplates = templatesQuery.data?.items.filter((template) => template.isActive) ?? [];
  const templateId = activeTemplates.some((template) => template.id === chosenTemplateId) ? chosenTemplateId : activeTemplates[0]?.id ?? '';
  const create = useMutation({
    mutationFn: () => createProgramWorkflow(id, selected!.key, templateId),
    onSuccess: async (record) => {
      queryClient.setQueryData(workflowByProgramQueryKey(id, selected!.key), record);
      queryClient.setQueryData(workflowQueryKey(record.id), getApiUniversityWorkflow(record));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.passport(id) }),
      ]);
    },
    onError: (cause) => {
      if (normalizeApiError(cause).status === 409) void workflowByProgram.refetch();
    },
  });
  const selectProgram = (key: string) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('program', key);
    next.delete('workflow');
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  if (programsQuery.isPending || (!realWorkflow && externalQuery.isPending)) return <WorkflowSkeleton mode="embedded" />;
  if (!programsQuery.data) return <RouteErrorState compact onRetry={() => void programsQuery.refetch()} />;
  return <div className={styles.programWorkflow}>
    {programs.length > 1 ? <FilterField className={styles.programSelector} label="Программа"><Select value={selected?.key ?? ''} onChange={(event) => selectProgram(event.target.value)}>{programs.map((program) => <option key={program.key} value={program.key}>{program.name}</option>)}</Select></FilterField> : selected ? <p className={styles.programName}>Программа: <strong>{selected.name}</strong></p> : null}
    {realWorkflow && workflowByProgram.isPending && selected ? <WorkflowSkeleton mode="embedded" /> : realWorkflow && workflowByProgram.isError && !workflowByProgram.data ? <RouteErrorState compact onRetry={() => void workflowByProgram.refetch()} /> : instanceId ? <WorkflowView key={instanceId} instanceId={instanceId} mode="embedded" canAdvance={canAdvance} /> : <>
      <EmptyState title="Workflow ещё не создан" description={realWorkflow ? 'Для выбранной программы процесс пока не создан.' : 'Создать его можно из заявки с сайта в разделе «Программы».'} primaryAction={realWorkflow ? undefined : { label: 'Открыть программы', onClick: () => { const next = new URLSearchParams(searchParams.toString()); next.set('tab', 'programs'); router.push(`${pathname}?${next.toString()}`, { scroll: false }); } }} />
      {canCreate && selected ? <>
        {templatesQuery.isError ? <ErrorState title="Не удалось загрузить шаблоны Workflow" onRetry={() => void templatesQuery.refetch()} /> : null}
        {activeTemplates.length > 1 ? <label className={styles.programSelector}><span>Шаблон Workflow</span><Select value={templateId} onChange={(event) => setChosenTemplateId(event.target.value)}>{activeTemplates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</Select></label> : null}
        {templatesQuery.isSuccess && !activeTemplates.length ? <p className={styles.externalHint}>Нет активного шаблона Workflow.</p> : null}
        <Button variant="primary" size="s" type="button" loading={create.isPending} disabled={!templateId || create.isPending} onClick={() => { if (!create.isPending && templateId) create.mutate(); }}>Создать Workflow</Button>
        {create.isError ? <p role="alert" className={styles.externalHint}>{normalizeApiError(create.error).message}</p> : null}
      </> : null}
    </>}
    {!realWorkflow && externalQuery.isError ? <p className={styles.externalHint}>Связь с заявками сайта сейчас недоступна; показаны программы ВУЗа.</p> : null}
  </div>;
}

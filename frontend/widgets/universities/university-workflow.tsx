'use client';

import type { ComponentType, FormEvent } from 'react';
import { useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Attachment from '@atomaro/icons/24/action/Attachment';
import Edit from '@atomaro/icons/24/editor/Edit';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import Education from '@atomaro/icons/24/culture/Education';
import Comments from '@atomaro/icons/24/communication/Comments';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import History from '@atomaro/icons/24/communication/History';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import SkipStroke from '@atomaro/icons/24/alert/SkipStroke';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import CalendarOpen from '@atomaro/icons/24/communication/CalendarOpen';
import User from '@atomaro/icons/24/communication/User';
import Task from '@atomaro/icons/24/communication/Task';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import type { WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { formatDateRu, formatDateTimeRu, getRelativeDueDateRu } from '@/shared/lib/formatters';
import { workflowStageStatusSemantics, type WorkflowStageIcon } from '@/shared/lib/status-semantics';
import { completeWorkflowInstance, getApiUniversityWorkflow, getUniversityPassport, getUniversityResponsibles, getUniversityWorkflow, getWorkflowAllowedTransitions, getWorkflowRollbackTargets, isMeetingAgendaStage, isRealWorkflowMode, listWorkflowTasksPage, universityPassportQueryKey, universityResponsiblesQueryKey, updateWorkflowResponsible, updateWorkflowStageResponsible, updateWorkflowStageDueDate, updateWorkflowStageName, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowAttachment, type UniversityWorkflowStage, type UniversityWorkflowStageStatus, type UniversityWorkflowTask } from '@/shared/lib/universities-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { invalidateWorkflowRelatedQueries } from '@/shared/lib/workflow-cache';
import { workflowAttachmentFromApi } from '@/shared/lib/workflow-attachments';
import { buildMockWorkflowHistory, buildWorkflowHistory, countWorkflowStageResources, loadWorkflowHistory, workflowHistoryPresentation, type WorkflowHistoryEvent } from '@/shared/lib/workflow-history';
import { getWorkflowSelectorPrograms, workflowProgramsQueryKey } from '@/shared/lib/universities-repository';
import { incompleteWorkflowTasksMessage, normalizeApiError } from '@/shared/lib/api-errors';
import { listUniversityWorkflowInstances, universityWorkflowInstancesQueryKey } from '@/shared/lib/workflow-creation-repository';
import { Input } from '@/shared/ui/rtk/form-controls';
import { SearchableSelect } from '@/shared/ui/rtk/multiselect';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { ListSkeleton, Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import { Toast } from '@/shared/ui/rtk/toast';
import { Modal } from '@/shared/ui/rtk/modal';
import { WorkflowComments } from './workflow-comments';
import { MeetingAgendaPdfAction } from './workflow-meeting-agenda';
import { WorkflowStageTasks } from './workflow-stage-tasks';
import { AttachmentRow, WorkflowAttachments } from './workflow-attachments';
import { WorkflowCreateModal } from './workflow-create-modal';
import { PassportWorkflowCard } from './passport-workflow-card';
import { WorkflowTransitionModal, type WorkflowTransitionNotification } from './workflow-transition-modal';
import { WorkflowRollbackModal } from './workflow-rollback-modal';
import { PassportSectionHeader } from './passport-section-header';
import { UniversityLocalClock } from './university-local-clock';
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
  if (!stage.deadline) return null;
  const relative = getRelativeDueDateRu(stage.deadline);
  const isOverdue = stage.status === 'overdue';
  const showRelative = stage.status === 'current' || isOverdue;
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
  if (!responsible) return null;
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
  const totalTasks = stage.taskTotal ?? stage.tasks.length;
  const comments = stage.commentTotal === null ? '—' : stage.commentTotal ?? stage.comments.length;
  const attachments = stage.attachmentTotal === null ? '—' : stage.attachmentTotal ?? stage.attachments.length;
  const items = [
    { key: 'comments', icon: Comments, label: 'Комментарии', value: String(comments), empty: comments === 0 },
    { key: 'attachments', icon: Attachment, label: 'Вложения', value: String(attachments), empty: attachments === 0 },
    { key: 'tasks', icon: Task, label: 'Задачи', value: String(totalTasks), empty: totalTasks === 0 },
  ];
  return <span className={styles.stageSummary} aria-label="Сводка этапа">{items.map(({ key, icon: Icon, label, value, empty }) => <span key={key} data-empty={empty} aria-label={`${label}: ${value}`} title={`${label}: ${value}`}><Icon size={14} fill="currentColor" aria-hidden="true" /><span>{value}</span></span>)}</span>;
}

function StageRenameAction({ stage, onSave }: { stage: UniversityWorkflowStage; onSave: (stageId: string, name: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(stage.name);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const close = () => { if (!pending) { setOpen(false); setError(''); } };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = value.trim();
    if (!name) { setError('Введите название этапа.'); return; }
    if (name === stage.name) { close(); return; }
    setPending(true);
    setError('');
    try {
      await onSave(stage.id, name);
      setOpen(false);
    } catch (cause) {
      setError(normalizeApiError(cause).message);
    } finally {
      setPending(false);
    }
  };
  return <>
    <Tooltip content="Переименовать этап"><IconButton icon={<Edit size={16} fill="currentColor" />} label={`Переименовать этап ${stage.name}`} size={16} onClick={() => { setValue(stage.name); setError(''); setOpen(true); }} /></Tooltip>
    {open ? <Modal title="Название этапа" onClose={close} initialFocusRef={inputRef}>
      <form className={styles.editForm} onSubmit={submit}>
        <label>Название этапа<Input ref={inputRef} value={value} maxLength={512} disabled={pending} onChange={(event) => setValue(event.target.value)} /></label>
        {error ? <span className={styles.stageRenameError} role="alert">{error}</span> : null}
        <div className={styles.editActions}>
          <Button variant="ghost" size="s" type="button" disabled={pending} onClick={close}>Отмена</Button>
          <Button variant="primary" size="s" type="submit" loading={pending} disabled={pending || !value.trim() || value.trim() === stage.name}>Сохранить</Button>
        </div>
      </form>
    </Modal> : null}
  </>;
}

function WorkflowStageItem({ stage, selected, detailsId, onSelect }: { stage: UniversityWorkflowStage; selected: boolean; detailsId: string; onSelect: () => void }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const titleClass = stage.status === 'skipped' ? styles.stageTitleMuted : undefined;
  return (
    <li className={`${styles.stageItem} ${selected ? styles.stageItemSelected : ''} ${semantics.muted ? styles.stageItemMuted : ''}`} data-status={stage.status}>
      <button className={styles.stageButton} type="button" aria-expanded={selected} aria-controls={detailsId} aria-current={stage.status === 'current' ? 'step' : undefined} data-testid={stage.status === 'current' ? 'workflow-current-stage' : undefined} onClick={onSelect}>
        <span className={`${styles.stageMarker} ${styles[`status-${stage.status}`]}`} aria-hidden="true">{stage.status === 'overdue' ? <CloseLarge size={18} fill="currentColor" /> : <StageStatusIcon status={stage.status} />}</span>
        <span className={styles.stageContent}>
          <span className={styles.stageTopline}><span className={styles.stageOrder}>{stage.orderIndex}</span><strong className={titleClass}>{stage.name}</strong></span>
          <span className={styles.stageMeta}><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge><StageDeadline stage={stage} /></span>
          <span className={styles.stageFooter}><StageAssignee stage={stage} /><StageSummary stage={stage} /></span>
        </span>
      </button>
    </li>
  );
}

type WorkflowAction = { label: string; variant: 'primary' | 'secondary' };

function getStageActions(stage: UniversityWorkflowStage, canAdvance: boolean, canRollback: boolean): WorkflowAction[] {
  if (stage.status !== 'current' && stage.status !== 'overdue') return [];
  const actions: WorkflowAction[] = [];
  if (canAdvance) actions.push({ label: 'Перевести на следующий этап', variant: 'primary' });
  if (canRollback) actions.push({ label: 'Вернуть на предыдущий этап', variant: 'secondary' });
  return actions;
}

function StageActionPanel({ stage, stages, instanceId, universityId, userId, canManage, agendaAvailable, allowedTargets, rollbackTargets, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; agendaAvailable: boolean; allowedTargets?: WorkflowTransitionTarget[]; rollbackTargets?: WorkflowTransitionTarget[]; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const [transitionContext, setTransitionContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const [rollbackContext, setRollbackContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const queryClient = useQueryClient();
  const complete = useMutation({
    mutationFn: () => completeWorkflowInstance(instanceId),
    onSuccess: async (record) => {
      queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      setCompleteOpen(false);
      await invalidateWorkflowRelatedQueries(queryClient, instanceId, universityId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowAllowed(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowRollbackTargets(instanceId) }),
      ]);
      onNotify({ intent: 'success', title: 'Workflow завершён', message: 'История и материалы сохранены.' });
      onTransitionSuccess();
    },
    onError: async (cause) => {
      const error = normalizeApiError(cause);
      onNotify({ intent: 'error', title: 'Не удалось завершить Workflow', message: error.message });
      if (error.code === 'WORKFLOW_TASKS_INCOMPLETE') await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowTasks(instanceId) }),
      ]);
    },
  });
  const isFinalStage = canManage && isRealWorkflowMode() && !stages.some((item) => item.orderIndex > stage.orderIndex);
  const actions = getStageActions(stage, canManage && !isFinalStage && (allowedTargets === undefined || allowedTargets.length > 0), canManage && (rollbackTargets === undefined || rollbackTargets.length > 0));
  const transitionAction = actions.find((action) => action.label.startsWith('Перевести'));
  const rollbackAction = actions.find((action) => action.label.startsWith('Вернуть'));
  const incompleteTasks = stage.templateStageId ? Math.max(
    0,
    (stage.taskTotal ?? 0) - (stage.taskCompleted ?? 0),
    stage.tasks.filter((task) => !task.completed).length,
  ) : 0;
  const blockIncomplete = () => {
    if (!incompleteTasks) return false;
    onNotify({ intent: 'error', title: 'Нельзя завершить этап', message: incompleteWorkflowTasksMessage(incompleteTasks) });
    return true;
  };
  if (!actions.length && !isFinalStage && !agendaAvailable && !transitionContext && !rollbackContext) return null;
  return <div className={styles.stageAction} aria-label="Действия этапа"><div className={styles.stageActionButtons}>{isFinalStage ? <Button variant="primary" size="s" type="button" onClick={() => { if (!blockIncomplete()) setCompleteOpen(true); }}>Завершить Workflow</Button> : null}{actions.map((action) => {
    const openTransition = action === transitionAction;
    const openRollback = action === rollbackAction;
    return <Button key={action.label} variant={action.variant} size="s" type="button" onClick={() => { if (openTransition && blockIncomplete()) return; onTransitionOpen(); if (openTransition) setTransitionContext({ currentStage: stage, stages }); if (openRollback) setRollbackContext({ currentStage: stage, stages }); }}>{action.label}</Button>;
  })}{agendaAvailable ? <MeetingAgendaPdfAction instanceId={instanceId} stageId={stage.id} placement="workflow" /> : null}</div>{actions.length ? <span>Комментарий и подтверждение обязательны для перехода.</span> : null}{agendaAvailable ? <span>Отметьте вопросы в комментариях — они попадут в PDF.</span> : null}{completeOpen ? <Modal title="Завершить Workflow?" onClose={() => { if (!complete.isPending) setCompleteOpen(false); }}><div className={styles.confirmContent}><p>После завершения Workflow перейдёт в состояние «Завершён». История и материалы сохранятся.</p><div className={styles.stageActionButtons}><Button variant="ghost" size="s" type="button" disabled={complete.isPending} onClick={() => setCompleteOpen(false)}>Отмена</Button><Button variant="primary" size="s" type="button" loading={complete.isPending} disabled={complete.isPending} onClick={() => complete.mutate()}>Завершить Workflow</Button></div></div></Modal> : null}{transitionContext ? <WorkflowTransitionModal open instanceId={instanceId} universityId={universityId} currentStage={transitionContext.currentStage} stages={transitionContext.stages} allowedTargets={allowedTargets} userId={userId} onClose={() => { setTransitionContext(null); onTransitionClose(); }} onSuccess={() => { setTransitionContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}{rollbackContext ? <WorkflowRollbackModal open instanceId={instanceId} universityId={universityId} currentStage={rollbackContext.currentStage} stages={rollbackContext.stages} allowedTargets={rollbackTargets} userId={userId} onClose={() => { setRollbackContext(null); onTransitionClose(); }} onSuccess={() => { setRollbackContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}</div>;
}

function CompletionSummary({ stage }: { stage: UniversityWorkflowStage }) {
  if (stage.status !== 'completed' || !stage.completedAt || !stage.completion) return null;
  const onTime = stage.completion === 'on_time';
  return <div className={`${styles.completionSummary} ${onTime ? styles.completionOnTime : styles.completionLate}`}><span aria-hidden="true">{onTime ? <CheckLarge size={16} fill="currentColor" /> : <ErrorStroke size={16} fill="currentColor" />}</span><span>{onTime ? 'Выполнено вовремя' : 'Завершено после дедлайна'}</span><time dateTime={stage.completedAt}>Завершено: {formatDateTimeRu(stage.completedAt)}</time></div>;
}

type WorkflowResourceState = { loading: boolean; error: boolean; retry: () => void; hasMore?: boolean; loadingMore?: boolean; loadMore?: () => void };

const historyIcons = { transition: History, comment: Comments, attachment: Attachment, responsible_changed: History, stage_responsible_changed: History, deadline_changed: History, stage_name_changed: History, workflow_completed: CheckLarge };

function WorkflowHistorySection({ idPrefix, instanceId, events, stages, userId, userName, state }: { idPrefix: string; instanceId: string; events: WorkflowHistoryEvent[]; stages: UniversityWorkflowStage[]; userId?: string; userName?: string; state?: WorkflowResourceState }) {
  const currentStage = stages.find((stage) => stage.status === 'current' || stage.status === 'overdue');
  const groups = new Map<string, { name: string; stage?: UniversityWorkflowStage; events: WorkflowHistoryEvent[] }>();
  for (const stage of stages) groups.set(stage.id, { name: stage.name, stage, events: [] });
  for (const event of events) {
    const stage = event.stageId ? stages.find((candidate) => candidate.templateStageId === event.stageId || candidate.id === event.stageId) : undefined;
    const key = stage?.id ?? `unassigned:${event.stageName}`;
    const group = groups.get(key) ?? { name: event.stageName, events: [] };
    group.events.push(event);
    groups.set(key, group);
  }
  const orderedGroups = [...groups.entries()].filter(([, group]) => group.events.length).sort((left, right) => Number(right[1].stage?.id === currentStage?.id) - Number(left[1].stage?.id === currentStage?.id));
  return <section className={styles.detailSection} aria-labelledby={`${idPrefix}-transition-title`}><details className={styles.historyDisclosure}><summary id={`${idPrefix}-transition-title`}><History size={18} fill="currentColor" /><strong>История Workflow</strong><span>{events.length} событий</span></summary><div className={styles.historyGroups}>{state?.loading ? <ListSkeleton items={2} /> : state?.error ? <ErrorState title="Не удалось загрузить историю" headingLevel={3} onRetry={state.retry} /> : events.length ? orderedGroups.map(([key, group]) => {
    const { name, stage } = group;
    return <details className={styles.historyDisclosure} key={key}><summary><strong>{name}</strong><span>{stage?.id === currentStage?.id ? 'Текущий этап' : stage?.status === 'completed' ? 'Завершённый этап' : 'Этап'} · {group.events.length} событий</span></summary><ol className={styles.transitionList}>{group.events.map((event) => {
      const presentation = workflowHistoryPresentation[event.kind];
      const Icon = historyIcons[presentation.icon];
      const actor = event.actorName ?? (event.actorId === userId ? userName : undefined) ?? 'Участник Workflow';
      return <li className={`${styles.historyEvent} ${styles[`history${event.kind}`]}`} key={event.id}><div className={styles.historyHeading}><Icon size={18} fill="currentColor" /><span className={styles.historyMetadata}>{presentation.label} · {actor}</span><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time></div><div className={styles.historyContent}>{event.kind === 'transition' || event.kind === 'responsible_changed' || event.kind === 'stage_responsible_changed' || event.kind === 'deadline_changed' || event.kind === 'stage_name_changed' || event.kind === 'workflow_completed' ? <strong>{event.title}</strong> : null}{event.text ? <p>{event.text}</p> : null}{event.attachments.length ? <ul className={styles.historyFiles}>{event.attachments.map((record) => <AttachmentRow key={record.id} attachment={workflowAttachmentFromApi(record, null)} instanceId={instanceId} canDelete={false} compact onOpen={() => undefined} onDelete={() => undefined} />)}</ul> : null}</div></li>;
    })}</ol></details>;
  }) : <EmptyState title="Событий пока нет" description="История появится после первого действия." headingLevel={3} />}</div></details></section>;
}

function WorkflowStageDetails({ stage, stages, workflow, instanceId, universityId, userId, canManage, canRename, onRename, idPrefix, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify, tasksState, attachmentsState, historyState, historyEvents, historyActorName, allowedTargets, rollbackTargets }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; workflow: UniversityWorkflow; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; canRename: boolean; onRename: (stageId: string, name: string) => Promise<void>; idPrefix: string; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void; tasksState?: WorkflowResourceState; attachmentsState?: WorkflowResourceState; historyState?: WorkflowResourceState; historyEvents: WorkflowHistoryEvent[]; historyActorName?: string; allowedTargets?: WorkflowTransitionTarget[]; rollbackTargets?: WorkflowTransitionTarget[] }) {
  const { user } = useAuth();
  const semantics = workflowStageStatusSemantics[stage.status];
  const headingId = `${idPrefix}-stage-details-title`;
  const activeStage = workflow.currentStage?.id === stage.id && (stage.status === 'current' || stage.status === 'overdue');
  const editableStage = canManage && activeStage && isRealWorkflowMode();
  const agendaAvailable = activeStage && workflow.status === 'active' && workflow.universityId === universityId && isRealWorkflowMode() && hasPermission(user, 'workflow.read') && isMeetingAgendaStage(stage.templateStageId, stage.name);
  const hasFacts = Boolean(stage.deadline || stage.responsible || stage.startedAt || stage.completedAt);
  return (
    <section className={`${styles.detailPanel} ${styles[`detail-${stage.status}`]}`} aria-labelledby={headingId} id={idPrefix}>
      <div className={styles.detailHeader}><div className={styles.detailTitle}><h2 id={headingId} aria-label={stage.name}>{stage.name}{canRename ? <>{'\u00a0'}<StageRenameAction stage={stage} onSave={onRename} /></> : null}</h2></div><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge></div>
      <CompletionSummary stage={stage} />
      {!activeStage && stage.status !== 'completed' && stage.status !== 'skipped' ? <p className={styles.futureNotice}>Этап ещё не начат. Он станет доступен после завершения предыдущего.</p> : null}
      {hasFacts || editableStage ? <section className={styles.detailSection} aria-labelledby={`${idPrefix}-overview-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-overview-title`}><InformationStroke size={18} fill="currentColor" />Основная информация</h3></div><dl className={styles.detailFacts}>
        {stage.responsible || editableStage ? <div><dt><User size={15} fill="currentColor" aria-hidden="true" />Ответственный</dt><dd><WorkflowStageResponsibleField instanceId={instanceId} workflow={workflow} stage={stage} canManage={editableStage} onNotify={onNotify} /></dd></div> : null}
        {stage.startedAt ? <div><dt><CalendarOpen size={15} fill="currentColor" aria-hidden="true" />Начат</dt><dd><time dateTime={stage.startedAt}>{formatDateTimeRu(stage.startedAt)}</time></dd></div> : null}
        {stage.deadline || editableStage ? <div><dt><TimeStroke size={15} fill="currentColor" aria-hidden="true" />Дедлайн</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><WorkflowDeadlineField instanceId={instanceId} stage={stage} canManage={editableStage} onNotify={onNotify} /></dd></div> : null}
        {stage.completedAt ? <div><dt><CheckLarge size={15} fill="currentColor" aria-hidden="true" />Завершён</dt><dd><time dateTime={stage.completedAt}>{formatDateTimeRu(stage.completedAt)}</time></dd></div> : null}
      </dl></section> : null}
      <WorkflowStageTasks stage={stage} instanceId={instanceId} canEdit={editableStage} state={tasksState} />
      <WorkflowComments instanceId={instanceId} stageId={stage.templateStageId ?? stage.id} comments={stage.comments} meetingStage={agendaAvailable} readOnly={!canManage || !activeStage} onNotify={onNotify} />
      {attachmentsState?.loading ? <ListSkeleton items={2} /> : attachmentsState?.error ? <ErrorState title="Не удалось загрузить вложения" headingLevel={3} onRetry={attachmentsState.retry} /> : stage.attachments.length ? <><WorkflowAttachments instanceId={instanceId} stageId={stage.id} attachments={stage.attachments} uploadEnabled={false} readOnly={!canManage || !activeStage} onNotify={onNotify} />{attachmentsState?.hasMore ? <Button variant="ghost" size="s" type="button" loading={attachmentsState.loadingMore} onClick={attachmentsState.loadMore}>Загрузить ещё вложения</Button> : null}</> : null}
      <WorkflowHistorySection idPrefix={idPrefix} instanceId={instanceId} events={historyEvents} stages={stages} userId={userId ?? undefined} userName={historyActorName} state={historyState} />
      <StageActionPanel stage={stage} stages={stages} instanceId={instanceId} universityId={universityId} userId={userId} canManage={editableStage} agendaAvailable={agendaAvailable} allowedTargets={allowedTargets} rollbackTargets={rollbackTargets} onTransitionOpen={onTransitionOpen} onTransitionClose={onTransitionClose} onTransitionSuccess={onTransitionSuccess} onNotify={onNotify} />
    </section>
  );
}

function WorkflowStageResponsibleField({ instanceId, workflow, stage, canManage, onNotify }: { instanceId: string; workflow: UniversityWorkflow; stage: UniversityWorkflowStage; canManage: boolean; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(stage.responsibleOverrideId ?? '');
  const [assignAll, setAssignAll] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  const overriddenStages = workflow.stages.filter((item) => item.responsibleOverrideId).length;
  const responsiblesQuery = useQuery({
    queryKey: universityResponsiblesQueryKey(workflow.universityId),
    queryFn: () => getUniversityResponsibles(workflow.universityId),
    staleTime: 30_000,
    enabled: open,
  });
  const options = responsiblesQuery.data ?? [];
  const save = useMutation({
    mutationFn: () => assignAll
      ? updateWorkflowResponsible(instanceId, value || null, true)
      : updateWorkflowStageResponsible(instanceId, stage.id, value || null),
    onSuccess: async (record) => {
      setOpen(false);
      setConfirmReplace(false);
      queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: universityWorkflowInstancesQueryKey(workflow.universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.health(workflow.universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
      ]);
    },
    onError: (cause) => onNotify({ intent: 'error', title: 'Ответственный этапа не сохранён', message: normalizeApiError(cause).message }),
  });
  const close = () => { if (!save.isPending) { setOpen(false); setConfirmReplace(false); } };
  const unchanged = assignAll ? value === (workflow.responsibleId ?? '') && !overriddenStages : value === (stage.responsibleOverrideId ?? '');
  const editable = canManage && hasPermission(user, 'university_responsible.manage');
  return <>
    {stage.responsible ? <span className={styles.responsibleIdentity}><span className={styles.factValue}>{stage.responsible.name}</span>{editable ? <span className={styles.responsibleEdit}><Tooltip content="Редактировать ответственного этапа"><IconButton icon={<Edit size={18} fill="currentColor" />} label="Редактировать ответственного этапа" size={18} onClick={() => { setValue(stage.responsibleOverrideId ?? ''); setAssignAll(false); setConfirmReplace(false); setOpen(true); }} /></Tooltip></span> : null}</span> : editable ? <Button variant="ghost" size="s" type="button" onClick={() => { setValue(''); setAssignAll(false); setConfirmReplace(false); setOpen(true); }}>+ Ответственный</Button> : null}
    {stage.responsible ? <small className={styles.responsibleSource}>{stage.responsibleOverrideId ? 'Для этого этапа' : 'Как у всего Workflow'}</small> : null}
    {open ? <Modal title="Ответственный этого этапа" onClose={close}><div className={styles.editForm}>
      {confirmReplace ? <><p role="alert">Индивидуальные назначения {overriddenStages} этапов будут заменены выбранным ответственным.</p><div className={styles.editActions}><Button variant="ghost" size="s" type="button" onClick={() => setConfirmReplace(false)}>Назад</Button><Button variant="primary" size="s" type="button" loading={save.isPending} onClick={() => save.mutate()}>Назначить на весь Workflow</Button></div></> : <>
        <SearchableSelect label="Назначение" labelPlacement="outside" value={value} disabled={responsiblesQuery.isPending || save.isPending} onChange={setValue} options={[{ id: '', name: assignAll ? 'Не назначен' : `Как у всего Workflow — ${workflow.responsibleName ?? 'не назначен'}` }, ...options]} placeholder={assignAll ? 'Не назначен' : 'Как у всего Workflow'} />
        <label className={styles.assignAllOption}><input type="checkbox" checked={assignAll} disabled={save.isPending} onChange={(event) => { const checked = event.target.checked; setAssignAll(checked); setValue(checked ? stage.responsible?.id ?? '' : stage.responsibleOverrideId ?? ''); }} />Назначить на весь Workflow</label>
        {responsiblesQuery.isError ? <p role="alert">Не удалось загрузить ответственных вуза.</p> : null}
        <div className={styles.editActions}><Button variant="ghost" size="s" type="button" disabled={save.isPending} onClick={close}>Отмена</Button><Button variant="primary" size="s" type="button" loading={save.isPending} disabled={save.isPending || responsiblesQuery.isPending || unchanged || Boolean(value && !options.some((item) => item.id === value))} onClick={() => { if (assignAll && overriddenStages) setConfirmReplace(true); else save.mutate(); }}>Сохранить</Button></div>
      </>}
    </div></Modal> : null}
  </>;
}

function WorkflowDeadlineField({ instanceId, stage, canManage, onNotify }: { instanceId: string; stage: UniversityWorkflowStage; canManage: boolean; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(stage.deadline);
  const save = useMutation({
    mutationFn: () => updateWorkflowStageDueDate(instanceId, stage.id, value || null),
    onSuccess: async (record) => {
      setOpen(false);
      queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.healthFamily }),
      ]);
    },
    onError: (cause) => onNotify({ intent: 'error', title: 'Дедлайн не сохранён', message: normalizeApiError(cause).message }),
  });
  return <><StageDeadline stage={stage} />{canManage ? stage.deadline ? <Tooltip content="Редактировать дедлайн"><IconButton icon={<Edit size={18} fill="currentColor" />} label="Редактировать дедлайн" size={18} onClick={() => { setValue(stage.deadline); setOpen(true); }} /></Tooltip> : <Button variant="ghost" size="s" type="button" onClick={() => { setValue(''); setOpen(true); }}>+ Дедлайн</Button> : null}{open ? <Modal title="Дедлайн этапа" onClose={() => { if (!save.isPending) setOpen(false); }}><div className={styles.editForm}><label>Дата<Input type="date" value={value} disabled={save.isPending} onChange={(event) => setValue(event.target.value)} /></label><div className={styles.editActions}><Button variant="ghost" size="s" type="button" disabled={save.isPending} onClick={() => setOpen(false)}>Отмена</Button><Button variant="primary" size="s" type="button" loading={save.isPending} disabled={save.isPending || value === stage.deadline} onClick={() => save.mutate()}>Сохранить</Button></div></div></Modal> : null}</>;
}

function WorkflowHeader({ workflow, directionName, timeZone, clockLoading }: { workflow: UniversityWorkflow; directionName?: string; timeZone?: string | null; clockLoading: boolean }) {
  const progress = workflow.totalSteps ? Math.round((workflow.completedSteps / workflow.totalSteps) * 100) : 0;
  const completed = workflow.status === 'completed' || (!workflow.status && workflow.totalSteps > 0 && workflow.completedSteps === workflow.totalSteps);
  const status = completed ? { label: 'Завершён', intent: 'success' as const } : workflow.status === 'archived' ? { label: 'В архиве', intent: 'neutral' as const } : { label: 'В работе', intent: 'orange' as const };
  const programName = workflow.programId && workflow.workflowName !== 'Workflow' ? workflow.workflowName : null;
  const context = [
    directionName && directionName !== programName ? `ИТ-направление: ${directionName}` : null,
    programName ? `Программа: ${programName}` : workflow.workflowName !== 'Workflow' ? workflow.workflowName : null,
    workflow.universityCity || null,
  ].filter(Boolean).join(' · ');
  return (
    <header className={styles.pageHeader}>
      <div className={styles.headerSummaryRow}>
        <div className={styles.workflowSummary}>
          <span className={styles.universityIcon} aria-hidden="true"><Education size={28} fill="currentColor" /></span>
          <div className={styles.headerMain}>
            <span className={styles.eyebrow}>Workflow вуза</span>
            <div className={styles.summaryTitle}><h1>{workflow.universityName}</h1><StatusBadge intent={status.intent} size="md">{status.label}</StatusBadge></div>
            {context ? <p className={styles.headerContext}>{context}</p> : null}
          </div>
        </div>
        <div className={styles.headerClock}>{clockLoading ? <Skeleton height={96} width="270px" /> : timeZone ? <UniversityLocalClock city={workflow.universityCity} timeZone={timeZone} /> : <div className={styles.clockUnavailable}><UniversityLocalClock city={workflow.universityCity} timeZone={timeZone} /></div>}</div>
      </div>
      <div className={styles.overallProgress}><div className={styles.progressLabel}><span>Прогресс Workflow</span><strong>{workflow.completedSteps} из {workflow.totalSteps} этапов завершено</strong></div><div className={styles.progressTrack} role="progressbar" aria-label={`Прогресс Workflow: завершено ${workflow.completedSteps} из ${workflow.totalSteps} этапов`} aria-valuemin={0} aria-valuemax={workflow.totalSteps} aria-valuenow={workflow.completedSteps}><span style={{ width: `${progress}%` }} /></div></div>
    </header>
  );
}

function WorkflowSkeleton({ mode }: { mode: WorkflowViewMode }) {
  return <SkeletonGroup label="Загрузка Workflow">{mode === 'page' ? <><Skeleton variant="text" width="220px" /><Skeleton variant="text" width="min(72%, 520px)" height={36} /><Skeleton height={96} /></> : null}<div className={styles.skeletonLayout}><ListSkeleton items={6} withAvatar /><Skeleton height={520} /></div></SkeletonGroup>;
}

function WorkflowGlobalResources({ instanceId, tasks, attachments, readOnly }: { instanceId: string; tasks: UniversityWorkflowTask[]; attachments: UniversityWorkflowAttachment[]; readOnly: boolean }) {
  if (!tasks.length && !attachments.length) return null;
  return <section className={styles.globalResources} aria-label="Общие материалы Workflow"><details className={styles.historyDisclosure}>
    <summary><Attachment size={18} fill="currentColor" /><strong>Общие материалы Workflow</strong><span>{tasks.length + attachments.length}</span></summary><div className={styles.globalResourcesContent}>
    {tasks.length ? <><h3>Задачи без привязки к этапу</h3><ul className={styles.taskList}>{tasks.map((task) => <li key={task.id}><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></li>)}</ul></> : null}
    {attachments.length ? <WorkflowAttachments instanceId={instanceId} stageId="general" attachments={attachments} uploadEnabled={false} readOnly={readOnly} /> : null}
  </div></details></section>;
}

export function WorkflowView({ instanceId, mode, canAdvance: canAdvanceOverride }: { instanceId: string; mode: WorkflowViewMode; canAdvance?: boolean }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const realWorkflow = isRealWorkflowMode();
  const query = useQuery({ queryKey: workflowQueryKey(instanceId), queryFn: () => getUniversityWorkflow(instanceId), staleTime: 30_000 });
  const passportQuery = useQuery({ queryKey: universityPassportQueryKey(query.data?.universityId ?? ''), queryFn: () => getUniversityPassport(query.data!.universityId, queryClient), enabled: mode === 'page' && Boolean(query.data?.universityId), staleTime: 30_000 });
  const headerProgramsQuery = useQuery({ queryKey: workflowProgramsQueryKey(query.data?.universityId ?? ''), queryFn: ({ signal }) => getWorkflowSelectorPrograms(query.data!.universityId, signal), enabled: mode === 'page' && Boolean(query.data?.programId), staleTime: 30_000 });
  const renameStageMutation = useMutation({
    mutationFn: ({ stageId, name }: { stageId: string; name: string }) => updateWorkflowStageName(instanceId, stageId, name),
    onSuccess: async (record) => {
      queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await Promise.all([
        invalidateWorkflowRelatedQueries(queryClient, instanceId, record.university_id),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
      ]);
    },
  });
  const renameStage = async (stageId: string, name: string) => { await renameStageMutation.mutateAsync({ stageId, name }); };
  const tasksQuery = useInfiniteQuery({ queryKey: queryKeys.universities.workflowTasks(instanceId), queryFn: ({ pageParam }) => listWorkflowTasksPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const historyQuery = useQuery({ queryKey: queryKeys.universities.workflowHistory(instanceId), queryFn: () => loadWorkflowHistory(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const allowedQuery = useQuery({ queryKey: queryKeys.universities.workflowAllowed(instanceId), queryFn: () => getWorkflowAllowedTransitions(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const rollbackQuery = useQuery({ queryKey: queryKeys.universities.workflowRollbackTargets(instanceId), queryFn: () => getWorkflowRollbackTargets(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const canManage = realWorkflow ? hasPermission(user, 'workflow.change_status') && query.data?.status === 'active' : (canAdvanceOverride ?? (user?.role === 'admin' || user?.role === 'manager'));
  const canRename = realWorkflow && canManage;
  const allowedTargets = realWorkflow ? allowedQuery.data?.map((item) => ({ id: item.id, orderIndex: item.order_index, name: item.name })) ?? [] : undefined;
  const rollbackTargets = realWorkflow ? rollbackQuery.data?.map((item) => ({ id: item.id, orderIndex: item.order_index, name: item.name })) ?? [] : undefined;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<(WorkflowTransitionNotification & { id: number })[]>([]);
  const notify = (item: WorkflowTransitionNotification) => {
    const id = Date.now() + Math.random();
    setNotifications((current) => [...current, { ...item, id }].slice(-5));
  };
  const resourceCounts = useMemo(() => historyQuery.data ? countWorkflowStageResources(historyQuery.data) : null, [historyQuery.data]);
  const stages = useMemo(() => query.data?.stages.map((stage) => realWorkflow ? {
    ...stage,
    tasks: (tasksQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((task) => task.stage_id === stage.templateStageId).map((task) => ({ id: task.id, label: task.title, completed: task.status === 'done' })),
    attachments: (historyQuery.data?.attachments ?? []).filter((attachment) => !attachment.comment_id && attachment.stage_id === stage.templateStageId).map((attachment) => workflowAttachmentFromApi(attachment, null)),
    commentTotal: resourceCounts ? resourceCounts.get(stage.templateStageId ?? '')?.comments ?? 0 : null,
    attachmentTotal: resourceCounts ? resourceCounts.get(stage.templateStageId ?? '')?.attachments ?? 0 : null,
  } : stage).sort((left, right) => left.orderIndex - right.orderIndex) ?? [], [query.data, realWorkflow, tasksQuery.data, historyQuery.data, resourceCounts]);
  const historyEvents = useMemo(() => realWorkflow ? historyQuery.data ? buildWorkflowHistory(historyQuery.data, stages) : [] : buildMockWorkflowHistory(stages), [historyQuery.data, realWorkflow, stages]);
  const selectedStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === selectedId) ?? stages.find((stage) => stage.id === query.data?.currentStage?.id) ?? stages[0];
  }, [query.data?.currentStage, selectedId, stages]);
  const commonTasks = useMemo(() => (tasksQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((task) => !task.stage_id).map((task) => ({ id: task.id, label: task.title, completed: task.status === 'done' })), [tasksQuery.data]);
  const commonAttachments = useMemo(() => (historyQuery.data?.attachments ?? []).filter((attachment) => !attachment.stage_id && !attachment.comment_id).map((attachment) => workflowAttachmentFromApi(attachment, null)), [historyQuery.data]);
  const idPrefix = `workflow-${instanceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const detailsId = `${idPrefix}-details`;

  if (query.isPending) return <WorkflowSkeleton mode={mode} />;
  if (!query.data) return <RouteErrorState compact={mode === 'embedded'} onRetry={() => void query.refetch()} />;
  if (!stages.length || !selectedStage) return <EmptyState presentation={mode === 'page' ? 'large' : 'compact'} icon={mode === 'embedded' ? <InformationStroke size={22} fill="currentColor" /> : undefined} title="Этапы Workflow пока не добавлены" description="Настроенные этапы появятся здесь после запуска процесса." />;

  return <div className={`${styles.page} ${mode === 'embedded' ? styles.embedded : ''}`}>
    {mode === 'page' ? <WorkflowHeader workflow={query.data} directionName={headerProgramsQuery.data?.find((program) => program.id === query.data.programId)?.direction} timeZone={passportQuery.data?.timeZone} clockLoading={passportQuery.isPending} /> : null}
    {mode === 'embedded' && query.data.status === 'completed' ? <StatusBadge intent="success">Workflow завершён</StatusBadge> : null}
    <div className={styles.layout}>
      <section className={styles.stagesPanel} aria-labelledby={`${idPrefix}-stages-title`}>
        <div className={styles.panelHeading}><div><h2 id={`${idPrefix}-stages-title`}>Этапы Workflow</h2></div><span className={styles.totalLabel}>{stages.length} этапов</span></div>
        <ol className={styles.stageList}>{stages.map((stage) => <WorkflowStageItem key={stage.id} stage={stage} selected={stage.id === selectedStage.id} detailsId={detailsId} onSelect={() => setSelectedId(stage.id)} />)}</ol>
      </section>
      <WorkflowStageDetails key={selectedStage.id} stage={selectedStage} stages={stages} workflow={query.data} instanceId={instanceId} universityId={query.data.universityId} userId={user?.id} canManage={canManage} canRename={canRename} onRename={renameStage} idPrefix={detailsId} onTransitionOpen={() => setSelectedId(selectedStage.id)} onTransitionClose={() => setSelectedId(null)} onTransitionSuccess={() => setSelectedId(null)} onNotify={notify} tasksState={realWorkflow ? { loading: tasksQuery.isPending, error: tasksQuery.isError && !tasksQuery.data, retry: () => void tasksQuery.refetch(), hasMore: tasksQuery.hasNextPage, loadingMore: tasksQuery.isFetchingNextPage, loadMore: () => void tasksQuery.fetchNextPage() } : undefined} attachmentsState={realWorkflow ? { loading: historyQuery.isPending, error: historyQuery.isError && !historyQuery.data, retry: () => void historyQuery.refetch() } : undefined} historyState={realWorkflow ? { loading: historyQuery.isPending, error: historyQuery.isError && !historyQuery.data, retry: () => void historyQuery.refetch() } : undefined} historyEvents={historyEvents} historyActorName={user?.name} allowedTargets={allowedTargets} rollbackTargets={rollbackTargets} />
    </div>
    {realWorkflow ? <WorkflowGlobalResources instanceId={instanceId} tasks={commonTasks} attachments={commonAttachments} readOnly={!canManage || !query.data.currentStage || query.data.currentStage.status === 'completed'} /> : null}
    {notifications.length ? <div className={styles.toastViewport}>{notifications.map((item) => <Toast key={item.id} intent={item.intent} title={item.title} message={item.message} onClose={() => setNotifications((current) => current.filter((entry) => entry.id !== item.id))} />)}</div> : null}
  </div>;
}

export function UniversityWorkflow({ id }: { id: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const instancesQuery = useQuery({
    queryKey: universityWorkflowInstancesQueryKey(id),
    queryFn: ({ signal }) => listUniversityWorkflowInstances(id, signal),
    staleTime: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [launchProgramId, setLaunchProgramId] = useState<string | null>(null);
  const programsQuery = useQuery({ queryKey: workflowProgramsQueryKey(id), queryFn: ({ signal }) => getWorkflowSelectorPrograms(id, signal), staleTime: 30_000 });
  const instances = instancesQuery.data ?? [];
  const unstartedPrograms = (programsQuery.data ?? []).filter((program) => !instances.some((instance) => instance.program_id === program.id));
  const canCreate = isRealWorkflowMode() && hasPermission(user, 'workflow.change_status');

  if (instancesQuery.isPending || programsQuery.isPending) return <WorkflowSkeleton mode="embedded" />;
  if (!instancesQuery.data || !programsQuery.data) return <RouteErrorState compact onRetry={() => { void instancesQuery.refetch(); void programsQuery.refetch(); }} />;

  return <div className={styles.programWorkflow}>
    <PassportSectionHeader title="Workflow вуза" count={instances.length} actions={canCreate ? <Button variant="primary" size="s" type="button" onClick={() => setCreateOpen(true)}>Создать Workflow</Button> : undefined} />
    <div className={styles.passportWorkflowCards}>{instances.map((item) => <PassportWorkflowCard key={item.id} instance={item} />)}{unstartedPrograms.map((program) => <PassportWorkflowCard key={program.id} programName={program.name} onLaunch={canCreate ? () => setLaunchProgramId(program.id) : undefined} />)}{!instances.length && !unstartedPrograms.length ? <EmptyState title="Workflow ещё не созданы" description="Процессы появятся после создания первого Workflow." /> : null}</div>
    {createOpen || launchProgramId !== null ? (
      <WorkflowCreateModal
        universityId={id}
        initialProgramId={launchProgramId || undefined}
        onClose={() => { setCreateOpen(false); setLaunchProgramId(null); }}
        onCreated={(record) => {
          setCreateOpen(false);
          setLaunchProgramId(null);
          router.push(`/workflows/${record.id}`);
        }}
      />
    ) : null}
  </div>;
}

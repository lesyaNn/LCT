'use client';

import type { ComponentType } from 'react';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Attachment from '@atomaro/icons/24/action/Attachment';
import Edit from '@atomaro/icons/24/editor/Edit';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import Comments from '@atomaro/icons/24/communication/Comments';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import History from '@atomaro/icons/24/communication/History';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import SkipStroke from '@atomaro/icons/24/alert/SkipStroke';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import Task from '@atomaro/icons/24/communication/Task';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission, hasRole } from '@/shared/lib/access-control';
import type { WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { formatDateRu, formatDateTimeRu, getRelativeDueDateRu } from '@/shared/lib/formatters';
import { workflowStageStatusSemantics, type WorkflowStageIcon } from '@/shared/lib/status-semantics';
import { getApiUniversityWorkflow, getUniversityResponsibles, getUniversityWorkflow, getWorkflowAllowedTransitions, getWorkflowRollbackTargets, isRealWorkflowMode, listWorkflowTasksPage, listWorkflowAttachmentsPage, universityResponsiblesQueryKey, updateWorkflowResponsible, updateWorkflowStageDueDate, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowAttachment, type UniversityWorkflowStage, type UniversityWorkflowStageStatus, type UniversityWorkflowTask } from '@/shared/lib/universities-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { workflowAttachmentFromApi } from '@/shared/lib/workflow-attachments';
import { buildMockWorkflowHistory, buildWorkflowHistory, loadWorkflowHistory, workflowHistoryPresentation, type WorkflowHistoryEvent } from '@/shared/lib/workflow-history';
import { getWorkflowSelectorPrograms, workflowProgramsQueryKey } from '@/shared/lib/universities-repository';
import { getUniversityExternalData, universityExternalDataQueryKey } from '@/shared/lib/external-integrations-repository';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { listUniversityWorkflowInstances, universityWorkflowInstancesQueryKey } from '@/shared/lib/workflow-creation-repository';
import { Input, Select } from '@/shared/ui/rtk/form-controls';
import { FilterField } from '@/shared/ui/rtk/filter-field';
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
import { WorkflowStageTasks } from './workflow-stage-tasks';
import { AttachmentRow, WorkflowAttachments } from './workflow-attachments';
import { WorkflowCreateModal } from './workflow-create-modal';
import { WorkflowTransitionModal, type WorkflowTransitionNotification } from './workflow-transition-modal';
import { WorkflowRollbackModal } from './workflow-rollback-modal';
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
  if (!stage.deadline) return <span>Не установлен</span>;
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
  const totalTasks = stage.taskTotal ?? stage.tasks.length;
  const completedTasks = stage.taskCompleted ?? stage.tasks.filter((task) => task.completed).length;
  const items = [
    { key: 'comments', icon: Comments, label: 'Комментарии', value: String(stage.comments.length) },
    { key: 'attachments', icon: Attachment, label: 'Вложения', value: String(stage.attachments.length) },
    ...(totalTasks ? [{ key: 'tasks', icon: Task, label: 'Задачи', value: `${completedTasks}/${totalTasks}` }] : []),
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

function getStageActions(stage: UniversityWorkflowStage, canAdvance: boolean, canRollback: boolean): WorkflowAction[] {
  if (stage.status !== 'current' && stage.status !== 'overdue') return [];
  const actions: WorkflowAction[] = [];
  if (canAdvance) actions.push({ label: 'Перевести на следующий этап', variant: 'primary' });
  if (canRollback) actions.push({ label: 'Вернуть на предыдущий этап', variant: 'secondary' });
  return actions;
}

function StageActionPanel({ stage, stages, instanceId, universityId, userId, canManage, allowedTargets, rollbackTargets, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; allowedTargets?: WorkflowTransitionTarget[]; rollbackTargets?: WorkflowTransitionTarget[]; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const [transitionContext, setTransitionContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const [rollbackContext, setRollbackContext] = useState<{ currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[] } | null>(null);
  const actions = getStageActions(stage, canManage && (allowedTargets === undefined || allowedTargets.length > 0), canManage && (rollbackTargets === undefined || rollbackTargets.length > 0));
  const transitionAction = actions.find((action) => action.label.startsWith('Перевести'));
  const rollbackAction = actions.find((action) => action.label.startsWith('Вернуть'));
  if (!actions.length && !transitionContext && !rollbackContext) return null;
  return <div className={styles.stageAction} aria-label="Действия этапа"><div className={styles.stageActionButtons}>{actions.map((action) => {
    const openTransition = action === transitionAction;
    const openRollback = action === rollbackAction;
    return <Button key={action.label} variant={action.variant} size="s" type="button" onClick={() => { onTransitionOpen(); if (openTransition) setTransitionContext({ currentStage: stage, stages }); if (openRollback) setRollbackContext({ currentStage: stage, stages }); }}>{action.label}</Button>;
  })}</div><span>Комментарий и подтверждение обязательны для перехода.</span>{transitionContext ? <WorkflowTransitionModal open instanceId={instanceId} universityId={universityId} currentStage={transitionContext.currentStage} stages={transitionContext.stages} allowedTargets={allowedTargets} userId={userId} onClose={() => { setTransitionContext(null); onTransitionClose(); }} onSuccess={() => { setTransitionContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}{rollbackContext ? <WorkflowRollbackModal open instanceId={instanceId} universityId={universityId} currentStage={rollbackContext.currentStage} stages={rollbackContext.stages} allowedTargets={rollbackTargets} userId={userId} onClose={() => { setRollbackContext(null); onTransitionClose(); }} onSuccess={() => { setRollbackContext(null); onTransitionSuccess(); }} onNotify={onNotify} /> : null}</div>;
}

function CompletionSummary({ stage }: { stage: UniversityWorkflowStage }) {
  if (stage.status !== 'completed' || !stage.completedAt || !stage.completion) return null;
  const onTime = stage.completion === 'on_time';
  return <div className={`${styles.completionSummary} ${onTime ? styles.completionOnTime : styles.completionLate}`}><span aria-hidden="true">{onTime ? <CheckLarge size={16} fill="currentColor" /> : <ErrorStroke size={16} fill="currentColor" />}</span><span>{onTime ? 'Выполнено вовремя' : 'Завершено после дедлайна'}</span><time dateTime={stage.completedAt}>Завершено: {formatDateTimeRu(stage.completedAt)}</time></div>;
}

type WorkflowResourceState = { loading: boolean; error: boolean; retry: () => void; hasMore?: boolean; loadingMore?: boolean; loadMore?: () => void };

const historyIcons = { transition: History, comment: Comments, attachment: Attachment, responsible_changed: History, deadline_changed: History };

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
      const actor = event.actorName ?? (event.actorId === userId ? userName : undefined);
      return <li className={`${styles.historyEvent} ${styles[`history${event.kind}`]}`} key={event.id}><div className={styles.historyHeading}><Icon size={18} fill="currentColor" /><strong>{presentation.label}</strong><time dateTime={event.occurredAt}>{formatDateTimeRu(event.occurredAt)}</time></div><div className={styles.historyContent}>{event.kind === 'transition' || event.kind === 'responsible_changed' || event.kind === 'deadline_changed' ? <strong>{event.title}</strong> : null}{actor ? <span className={styles.historyActor}>{actor}</span> : null}{event.text ? <p>{event.text}</p> : null}{event.attachments.length ? <ul className={styles.historyFiles}>{event.attachments.map((record) => <AttachmentRow key={record.id} attachment={workflowAttachmentFromApi(record, null)} instanceId={instanceId} canDelete={false} compact onOpen={() => undefined} onDelete={() => undefined} />)}</ul> : null}</div></li>;
    })}</ol></details>;
  }) : <EmptyState title="Событий пока нет" description="История появится после первого действия." headingLevel={3} />}</div></details></section>;
}

function WorkflowStageDetails({ stage, stages, workflow, instanceId, universityId, userId, canManage, idPrefix, onTransitionOpen, onTransitionClose, onTransitionSuccess, onNotify, tasksState, attachmentsState, historyState, historyEvents, historyActorName, allowedTargets, rollbackTargets }: { stage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; workflow: UniversityWorkflow; instanceId: string; universityId?: string | null; userId?: string | null; canManage: boolean; idPrefix: string; onTransitionOpen: () => void; onTransitionClose: () => void; onTransitionSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void; tasksState?: WorkflowResourceState; attachmentsState?: WorkflowResourceState; historyState?: WorkflowResourceState; historyEvents: WorkflowHistoryEvent[]; historyActorName?: string; allowedTargets?: WorkflowTransitionTarget[]; rollbackTargets?: WorkflowTransitionTarget[] }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const headingId = `${idPrefix}-stage-details-title`;
  return (
    <section className={`${styles.detailPanel} ${styles[`detail-${stage.status}`]}`} aria-labelledby={headingId} id={idPrefix}>
      <div className={styles.detailHeader}><div><h2 id={headingId}>{stage.name}</h2></div><StatusBadge intent={semantics.intent} icon={<StageStatusIcon status={stage.status} />}>{semantics.label}</StatusBadge></div>
      <CompletionSummary stage={stage} />
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-overview-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-overview-title`}><InformationStroke size={18} fill="currentColor" />Основная информация</h3></div><dl className={styles.detailFacts}><div><dt>{stage.status === 'completed' ? 'Дедлайн был' : 'Дедлайн'}</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><WorkflowDeadlineField instanceId={instanceId} stage={stage} canManage={canManage && workflow.currentStage?.id === stage.id && isRealWorkflowMode()} onNotify={onNotify} /></dd></div>{stage.startedAt ? <div><dt>Начат</dt><dd><time dateTime={stage.startedAt}>{formatDateTimeRu(stage.startedAt)}</time></dd></div> : null}{stage.completedAt && stage.status !== 'completed' ? <div><dt>Завершён</dt><dd><time dateTime={stage.completedAt}>{formatDateTimeRu(stage.completedAt)}</time></dd></div> : null}<div><dt>Ответственный Workflow</dt><dd><WorkflowResponsibleField instanceId={instanceId} workflow={workflow} canManage={canManage && workflow.currentStage?.id === stage.id && isRealWorkflowMode()} onNotify={onNotify} /></dd></div></dl></section>
      <WorkflowStageTasks stage={stage} instanceId={instanceId} canEdit={canManage && isRealWorkflowMode()} state={tasksState} />
      <WorkflowComments instanceId={instanceId} stageId={stage.templateStageId ?? stage.id} comments={stage.comments} readOnly={stage.status !== 'current' && stage.status !== 'overdue'} onNotify={onNotify} />
      {attachmentsState?.loading ? <ListSkeleton items={2} /> : attachmentsState?.error ? <ErrorState title="Не удалось загрузить вложения" headingLevel={3} onRetry={attachmentsState.retry} /> : stage.attachments.length ? <><WorkflowAttachments instanceId={instanceId} stageId={stage.id} attachments={stage.attachments} uploadEnabled={false} readOnly={stage.status !== 'current' && stage.status !== 'overdue'} onNotify={onNotify} />{attachmentsState?.hasMore ? <Button variant="ghost" size="s" type="button" loading={attachmentsState.loadingMore} onClick={attachmentsState.loadMore}>Загрузить ещё вложения</Button> : null}</> : null}
      <WorkflowHistorySection idPrefix={idPrefix} instanceId={instanceId} events={historyEvents} stages={stages} userId={userId ?? undefined} userName={historyActorName} state={historyState} />
      <StageActionPanel stage={stage} stages={stages} instanceId={instanceId} universityId={universityId} userId={userId} canManage={canManage} allowedTargets={allowedTargets} rollbackTargets={rollbackTargets} onTransitionOpen={onTransitionOpen} onTransitionClose={onTransitionClose} onTransitionSuccess={onTransitionSuccess} onNotify={onNotify} />
    </section>
  );
}

function WorkflowResponsibleField({ instanceId, workflow, canManage, onNotify }: { instanceId: string; workflow: UniversityWorkflow; canManage: boolean; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const responsiblesQuery = useQuery({
    queryKey: universityResponsiblesQueryKey(workflow.universityId),
    queryFn: () => getUniversityResponsibles(workflow.universityId),
    staleTime: 30_000,
    enabled: open,
  });
  const options = useMemo(() => responsiblesQuery.data ?? [], [responsiblesQuery.data]);
  const [value, setValue] = useState(workflow.responsibleId ?? '');
  const save = useMutation({
    mutationFn: () => updateWorkflowResponsible(instanceId, value || null),
    onSuccess: async (record) => {
      setOpen(false);
      queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: universityWorkflowInstancesQueryKey(workflow.universityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
      ]);
    },
    onError: (cause) => onNotify({ intent: 'error', title: 'Ответственный не сохранён', message: normalizeApiError(cause).message }),
  });
  return (
    <><span className={styles.factValue}>{workflow.responsibleName ?? 'Не назначен'}</span>{canManage ? <Tooltip content={workflow.responsibleId ? 'Редактировать ответственного' : 'Назначить ответственного'}><IconButton icon={<Edit size={18} fill="currentColor" />} label={workflow.responsibleId ? 'Редактировать ответственного' : 'Назначить ответственного'} size={18} onClick={() => { setValue(workflow.responsibleId ?? ''); setOpen(true); }} /></Tooltip> : null}{open ? <Modal title="Ответственный Workflow" onClose={() => { if (!save.isPending) setOpen(false); }}><div className={styles.editForm}><label>Ответственный<Select value={value} disabled={responsiblesQuery.isPending || save.isPending} onChange={(event) => setValue(event.target.value)}><option value="">Не назначен</option>{options.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>{responsiblesQuery.isError ? <p role="alert">Не удалось загрузить ответственных вуза.</p> : null}{value ? <p className={styles.externalHint}>{[options.find((item) => item.id === value)?.email, options.find((item) => item.id === value)?.phone].filter(Boolean).join(' · ')}</p> : null}<div className={styles.editActions}><Button variant="ghost" size="s" type="button" disabled={save.isPending} onClick={() => setOpen(false)}>Отмена</Button><Button variant="primary" size="s" type="button" loading={save.isPending} disabled={save.isPending || responsiblesQuery.isPending || value === (workflow.responsibleId ?? '') || Boolean(value && !options.some((item) => item.id === value))} onClick={() => save.mutate()}>Сохранить</Button></div></div></Modal> : null}</>
  );
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
      ]);
    },
    onError: (cause) => onNotify({ intent: 'error', title: 'Дедлайн не сохранён', message: normalizeApiError(cause).message }),
  });
  return <><StageDeadline stage={stage} />{canManage ? <Tooltip content={stage.deadline ? 'Редактировать дедлайн' : 'Установить дедлайн'}><IconButton icon={<Edit size={18} fill="currentColor" />} label={stage.deadline ? 'Редактировать дедлайн' : 'Установить дедлайн'} size={18} onClick={() => { setValue(stage.deadline); setOpen(true); }} /></Tooltip> : null}{open ? <Modal title="Дедлайн этапа" onClose={() => { if (!save.isPending) setOpen(false); }}><div className={styles.editForm}><label>Дата<Input type="date" value={value} disabled={save.isPending} onChange={(event) => setValue(event.target.value)} /></label><div className={styles.editActions}><Button variant="ghost" size="s" type="button" disabled={save.isPending} onClick={() => setOpen(false)}>Отмена</Button><Button variant="primary" size="s" type="button" loading={save.isPending} disabled={save.isPending || value === stage.deadline} onClick={() => save.mutate()}>Сохранить</Button></div></div></Modal> : null}</>;
}

function WorkflowHeader({ workflow }: { workflow: UniversityWorkflow }) {
  const progress = workflow.totalSteps ? Math.round((workflow.completedSteps / workflow.totalSteps) * 100) : 0;
  return (
    <header className={styles.pageHeader}>
      <div className={styles.headerMain}><h1>Взаимодействие с вузом</h1><p className={styles.headerContext}>{[workflow.universityName, workflow.universityCity, workflow.workflowName].filter((part, index, parts) => part && parts.findIndex((other) => other.toLocaleLowerCase('ru-RU') === part.toLocaleLowerCase('ru-RU')) === index).join(' · ')}</p></div>
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
    {tasks.length ? <><h3>Задачи без привязки к этапу</h3><ul className={styles.taskList}>{tasks.map((task) => <li key={task.id}><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></li>)}</ul></> : null}
    {attachments.length ? <WorkflowAttachments instanceId={instanceId} stageId="general" attachments={attachments} uploadEnabled={false} readOnly={readOnly} /> : null}
  </section>;
}

export function WorkflowView({ instanceId, mode, canAdvance: canAdvanceOverride }: { instanceId: string; mode: WorkflowViewMode; canAdvance?: boolean }) {
  const { user } = useAuth();
  const realWorkflow = isRealWorkflowMode();
  const query = useQuery({ queryKey: workflowQueryKey(instanceId), queryFn: () => getUniversityWorkflow(instanceId), staleTime: 30_000 });
  const tasksQuery = useInfiniteQuery({ queryKey: queryKeys.universities.workflowTasks(instanceId), queryFn: ({ pageParam }) => listWorkflowTasksPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const attachmentsQuery = useInfiniteQuery({ queryKey: queryKeys.universities.workflowAttachments(instanceId), queryFn: ({ pageParam }) => listWorkflowAttachmentsPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const historyQuery = useQuery({ queryKey: queryKeys.universities.workflowHistory(instanceId), queryFn: () => loadWorkflowHistory(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const allowedQuery = useQuery({ queryKey: queryKeys.universities.workflowAllowed(instanceId), queryFn: () => getWorkflowAllowedTransitions(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const rollbackQuery = useQuery({ queryKey: queryKeys.universities.workflowRollbackTargets(instanceId), queryFn: () => getWorkflowRollbackTargets(instanceId), enabled: realWorkflow && Boolean(query.data), staleTime: 30_000 });
  const canManage = realWorkflow ? hasPermission(user, 'workflow.change_status') : (canAdvanceOverride ?? (user?.role === 'admin' || user?.role === 'manager'));
  const allowedTargets = realWorkflow ? allowedQuery.data?.map((item) => ({ id: item.id, orderIndex: item.order_index, name: item.name })) ?? [] : undefined;
  const rollbackTargets = realWorkflow ? rollbackQuery.data?.map((item) => ({ id: item.id, orderIndex: item.order_index, name: item.name })) ?? [] : undefined;
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
    attachments: (attachmentsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((attachment) => !attachment.comment_id && attachment.stage_id === stage.templateStageId).map((attachment) => workflowAttachmentFromApi(attachment, null)),
  } : stage).sort((left, right) => left.orderIndex - right.orderIndex) ?? [], [query.data, realWorkflow, tasksQuery.data, attachmentsQuery.data]);
  const historyEvents = useMemo(() => realWorkflow ? historyQuery.data ? buildWorkflowHistory(historyQuery.data, stages) : [] : buildMockWorkflowHistory(stages), [historyQuery.data, realWorkflow, stages]);
  const selectedStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === selectedId) ?? stages.find((stage) => stage.id === query.data?.currentStage?.id) ?? stages[0];
  }, [query.data?.currentStage, selectedId, stages]);
  const commonTasks = useMemo(() => (tasksQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((task) => !task.stage_id).map((task) => ({ id: task.id, label: task.title, completed: task.status === 'done' })), [tasksQuery.data]);
  const commonAttachments = useMemo(() => (attachmentsQuery.data?.pages.flatMap((page) => page.items) ?? []).filter((attachment) => !attachment.stage_id && !attachment.comment_id).map((attachment) => workflowAttachmentFromApi(attachment, null)), [attachmentsQuery.data]);
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
      <WorkflowStageDetails key={selectedStage.id} stage={selectedStage} stages={stages} workflow={query.data} instanceId={instanceId} universityId={query.data.universityId} userId={user?.id} canManage={canManage} idPrefix={detailsId} onTransitionOpen={() => setSelectedId(selectedStage.id)} onTransitionClose={() => setSelectedId(null)} onTransitionSuccess={() => setSelectedId(null)} onNotify={setNotification} tasksState={realWorkflow ? { loading: tasksQuery.isPending, error: tasksQuery.isError && !tasksQuery.data, retry: () => void tasksQuery.refetch(), hasMore: tasksQuery.hasNextPage, loadingMore: tasksQuery.isFetchingNextPage, loadMore: () => void tasksQuery.fetchNextPage() } : undefined} attachmentsState={realWorkflow ? { loading: attachmentsQuery.isPending, error: attachmentsQuery.isError && !attachmentsQuery.data, retry: () => void attachmentsQuery.refetch(), hasMore: attachmentsQuery.hasNextPage, loadingMore: attachmentsQuery.isFetchingNextPage, loadMore: () => void attachmentsQuery.fetchNextPage() } : undefined} historyState={realWorkflow ? { loading: historyQuery.isPending, error: historyQuery.isError && !historyQuery.data, retry: () => void historyQuery.refetch() } : undefined} historyEvents={historyEvents} historyActorName={user?.name} allowedTargets={allowedTargets} rollbackTargets={rollbackTargets} />
    </div>
    {realWorkflow ? <WorkflowGlobalResources instanceId={instanceId} tasks={commonTasks} attachments={commonAttachments} readOnly={!canManage || !query.data.currentStage || query.data.currentStage.status === 'completed'} /> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}

function instanceStatusLabel(status: string): string {
  if (status === 'completed') return 'Завершён';
  if (status === 'active') return 'В работе';
  return status || '—';
}

function MockUniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const programsQuery = useQuery({ queryKey: workflowProgramsQueryKey(id), queryFn: ({ signal }) => getWorkflowSelectorPrograms(id, signal), staleTime: 30_000 });
  const externalQuery = useQuery({ queryKey: universityExternalDataQueryKey(id, 'website'), queryFn: () => getUniversityExternalData(id, 'website'), staleTime: 30_000 });
  const programs = useMemo(() => {
    const base = programsQuery.data ?? [];
    const applications = externalQuery.data?.applications ?? [];
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
  }, [programsQuery.data, externalQuery.data]);
  const requestedProgram = searchParams.get('program');
  const selected = programs.find((program) => program.key === requestedProgram || (requestedProgram && program.externalIds.includes(requestedProgram))) ?? programs[0];
  const mockInstanceId = selected && requestedProgram && (selected.key === requestedProgram || selected.externalIds.includes(requestedProgram)) ? searchParams.get('workflow') ?? selected.instanceId : selected?.instanceId;
  const selectProgram = (key: string) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set('program', key);
    next.delete('workflow');
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  if (programsQuery.isPending || externalQuery.isPending) return <WorkflowSkeleton mode="embedded" />;
  if (!programsQuery.data) return <RouteErrorState compact onRetry={() => void programsQuery.refetch()} />;
  return <div className={styles.programWorkflow}>
    {programs.length > 1 ? <FilterField className={styles.programSelector} label="Программа"><Select value={selected?.key ?? ''} onChange={(event) => selectProgram(event.target.value)}>{programs.map((program) => <option key={program.key} value={program.key}>{program.name}</option>)}</Select></FilterField> : selected ? <p className={styles.programName}>Программа: <strong>{selected.name}</strong></p> : null}
    {mockInstanceId ? <WorkflowView key={mockInstanceId} instanceId={mockInstanceId} mode="embedded" canAdvance={canAdvance} /> : <EmptyState title="Workflow ещё не создан" description="Демонстрационные данные Workflow для выбранной программы отсутствуют." />}
    {externalQuery.isError ? <p className={styles.externalHint}>Связь с заявками сайта сейчас недоступна; показаны программы ВУЗа.</p> : null}
  </div>;
}

function RealUniversityWorkflow({ id }: { id: string; canAdvance: boolean }) {
  const { user } = useAuth();
  const router = useRouter();
  const instancesQuery = useQuery({
    queryKey: universityWorkflowInstancesQueryKey(id),
    queryFn: ({ signal }) => listUniversityWorkflowInstances(id, signal),
    staleTime: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const instances = instancesQuery.data ?? [];
  const canCreate = hasPermission(user, 'workflow.change_status') && hasRole(user, 'admin');

  if (instancesQuery.isPending) return <WorkflowSkeleton mode="embedded" />;
  if (!instancesQuery.data) return <RouteErrorState compact onRetry={() => void instancesQuery.refetch()} />;

  return <div className={styles.programWorkflow}>
    <div className={styles.instancesHeader}>
      <div>
        <h2>Workflow вуза</h2>
        <p>{instances.length ? `Всего: ${instances.length}` : 'Процессы появятся после создания первого Workflow.'}</p>
      </div>
      {canCreate ? <Button variant="primary" size="s" type="button" onClick={() => setCreateOpen(true)}>Создать Workflow</Button> : null}
    </div>
    {instances.length ? (
      <ol className={styles.instanceList}>
        {instances.map((item) => (
          <li key={item.id} className={styles.instanceItem}>
            <Link className={styles.instanceButton} href={`/workflows/${item.id}`} onKeyDown={(event) => { if (event.key === ' ') { event.preventDefault(); event.currentTarget.click(); } }}>
              <strong>{item.program_name || 'Без программы'}</strong>
              {(() => {
                const current = item.stages.find((stage) => stage.id === item.current_instance_stage_id || stage.template_stage_id === item.current_stage_id) ?? item.stages.find((stage) => stage.status === 'current');
                const completed = item.stages.filter((stage) => stage.status === 'completed').length;
                return <><span className={styles.instanceStage}>{current ? <>Текущий этап: <b>{current.name}</b></> : 'Этап завершён'}</span><span className={styles.instanceMeta}><span>{completed} из {item.stages.length} этапов</span><StatusBadge intent={item.is_overdue ? 'danger' : item.status === 'completed' ? 'success' : 'brand'}>{item.is_overdue ? 'Просрочен' : instanceStatusLabel(item.status)}</StatusBadge></span><span className={styles.instanceProgress} role="progressbar" aria-label="Прогресс Workflow" aria-valuemin={0} aria-valuemax={item.stages.length} aria-valuenow={completed}><span style={{ width: `${item.stages.length ? completed / item.stages.length * 100 : 0}%` }} /></span>{item.responsible_name || item.due_date ? <span className={styles.instanceFacts}>{item.responsible_name}{item.responsible_name && item.due_date ? ' · ' : null}{item.due_date ? `Дедлайн: ${formatDateRu(item.due_date)}` : null}</span> : null}</>;
              })()}
            </Link>
          </li>
        ))}
      </ol>
    ) : (
      <EmptyState
        title="Workflow ещё не созданы"
        description="Создайте первый Workflow: выберите направление, программу обучения и продукт."
      />
    )}
    {createOpen ? (
      <WorkflowCreateModal
        universityId={id}
        onClose={() => setCreateOpen(false)}
        onCreated={(record) => {
          setCreateOpen(false);
          router.push(`/workflows/${record.id}`);
        }}
      />
    ) : null}
  </div>;
}

export function UniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  if (isRealWorkflowMode()) return <RealUniversityWorkflow id={id} canAdvance={canAdvance} />;
  return <MockUniversityWorkflow id={id} canAdvance={canAdvance} />;
}

'use client';

import Link from 'next/link';
import type { ComponentType } from 'react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Attachment from '@atomaro/icons/24/action/Attachment';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import Comments from '@atomaro/icons/24/communication/Comments';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import History from '@atomaro/icons/24/communication/History';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import SkipStroke from '@atomaro/icons/24/alert/SkipStroke';
import Task from '@atomaro/icons/24/communication/Task';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { useAuth } from '@/shared/auth/AuthProvider';
import { formatDateRu, formatDateTimeRu, formatDaysUntilRu } from '@/shared/lib/formatters';
import { workflowStageStatusSemantics, type WorkflowStageIcon } from '@/shared/lib/status-semantics';
import { getUniversityWorkflow, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowStage, type UniversityWorkflowStageStatus } from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
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

function StageStatusIcon({ status }: { status: UniversityWorkflowStageStatus }) {
  const Icon = statusIcons[workflowStageStatusSemantics[status].icon];
  return <Icon size={18} fill="currentColor" />;
}

function StageDeadline({ stage }: { stage: UniversityWorkflowStage }) {
  const showRelative = stage.status === 'current' || stage.status === 'overdue';
  return <span className={`${styles.stageDeadline} ${stage.status === 'overdue' ? styles.overdue : ''}`}><span><TimeStroke size={14} fill="currentColor" /><time dateTime={stage.deadline}>{formatDateRu(stage.deadline)}</time></span>{showRelative ? <small>{formatDaysUntilRu(stage.deadline)}</small> : null}</span>;
}

function StageResponsible({ stage }: { stage: UniversityWorkflowStage }) {
  return stage.responsible
    ? <span className={styles.stageResponsible}><Avatar initials={getInitials(stage.responsible.name)} size="s" /><span>{stage.responsible.name}</span></span>
    : <span className={styles.stageResponsible}>Ответственный не назначен</span>;
}

function WorkflowStageItem({ stage, selected, onSelect }: { stage: UniversityWorkflowStage; selected: boolean; onSelect: () => void }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  return (
    <li className={`${styles.stageItem} ${selected ? styles.stageItemSelected : ''}`}>
      <button className={styles.stageButton} type="button" aria-current={selected ? 'step' : undefined} onClick={onSelect}>
        <span className={`${styles.stageMarker} ${styles[`status-${stage.status}`]}`} aria-hidden="true"><StageStatusIcon status={stage.status} /></span>
        <span className={styles.stageContent}>
          <span className={styles.stageTopline}><span className={styles.stageOrder}>{stage.orderIndex}</span><strong className={stage.status === 'completed' ? styles.stageTitleCompleted : stage.status === 'skipped' ? styles.stageTitleSkipped : undefined}>{stage.name}</strong></span>
          <span className={styles.stageMeta}><StatusBadge intent={semantics.intent}>{semantics.label}</StatusBadge><StageDeadline stage={stage} /></span>
          <StageResponsible stage={stage} />
        </span>
      </button>
    </li>
  );
}

function CommentsBlock({ stage, idPrefix }: { stage: UniversityWorkflowStage; idPrefix: string }) {
  const [showAll, setShowAll] = useState(false);
  const comments = showAll ? stage.comments : stage.comments.slice(0, 3);
  const headingId = `${idPrefix}-comments-title`;
  return (
    <section className={styles.detailSection} aria-labelledby={headingId}>
      <div className={styles.detailSectionHeading}><h3 id={headingId}><Comments size={18} fill="currentColor" />Комментарии</h3>{stage.comments.length > 3 ? <Button variant="ghost" size="s" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : 'Показать все'}</Button> : null}</div>
      <ul className={styles.commentList}>{comments.map((comment) => <li key={comment.id}><div className={styles.commentMeta}><strong>{comment.author}</strong><time dateTime={comment.occurredAt}>{formatDateTimeRu(comment.occurredAt)}</time></div><p>{comment.text}</p></li>)}</ul>
      <form className={styles.commentForm} onSubmit={(event) => event.preventDefault()}>
        <label htmlFor={`${idPrefix}-comment-input`}>Добавить комментарий</label>
        <textarea id={`${idPrefix}-comment-input`} rows={3} placeholder="Введите комментарий" disabled />
        <div className={styles.commentFormFooter}><Button variant="secondary" size="s" type="submit" disabled title="Добавление комментариев подключится после появления API">Добавить</Button><span>Форма станет доступна после подключения API.</span></div>
      </form>
    </section>
  );
}

function WorkflowStageDetails({ stage, canAdvance, idPrefix }: { stage: UniversityWorkflowStage; canAdvance: boolean; idPrefix: string }) {
  const semantics = workflowStageStatusSemantics[stage.status];
  const completedTasks = stage.tasks.filter((task) => task.completed).length;
  const taskProgress = stage.tasks.length ? Math.round((completedTasks / stage.tasks.length) * 100) : 0;
  const headingId = `${idPrefix}-stage-details-title`;
  return (
    <section className={styles.detailPanel} aria-labelledby={headingId}>
      <div className={styles.detailHeader}><div><span className={styles.eyebrow}>Детали этапа {stage.orderIndex} из 14</span><h2 id={headingId}>{stage.name}</h2></div><StatusBadge intent={semantics.intent}>{semantics.label}</StatusBadge></div>
      <dl className={styles.detailFacts}><div><dt>Дедлайн</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><StageDeadline stage={stage} /></dd></div><div><dt>Ответственный</dt><dd>{stage.responsible ? <><Avatar initials={getInitials(stage.responsible.name)} size="s" />{stage.responsible.name}</> : 'Не назначен'}</dd></div></dl>
      <CommentsBlock stage={stage} idPrefix={idPrefix} />
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-attachments-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-attachments-title`}><Attachment size={18} fill="currentColor" />Вложения</h3></div>{stage.attachments.length ? <ul className={styles.attachmentList}>{stage.attachments.map((attachment) => <li key={attachment.id}><DocumentText size={18} fill="currentColor" /><span><strong>{attachment.fileName}</strong><small>{attachment.fileType} · {attachment.fileSize}</small></span></li>)}</ul> : <p className={styles.muted}>Вложений пока нет</p>}</section>
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-tasks-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-tasks-title`}><Task size={18} fill="currentColor" />Задачи этапа</h3><span className={styles.taskCount}>Выполнено {completedTasks} из {stage.tasks.length}</span></div><div className={styles.taskProgress} role="progressbar" aria-label={`Задачи этапа: выполнено ${completedTasks} из ${stage.tasks.length}`} aria-valuemin={0} aria-valuemax={stage.tasks.length} aria-valuenow={completedTasks}><span style={{ width: `${taskProgress}%` }} /></div><ul className={styles.taskList}>{stage.tasks.map((task) => <li key={task.id}><label><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></label></li>)}</ul></section>
      <section className={styles.detailSection} aria-labelledby={`${idPrefix}-transition-title`}><div className={styles.detailSectionHeading}><h3 id={`${idPrefix}-transition-title`}><History size={18} fill="currentColor" />История переходов</h3></div>{stage.transitions.length ? <ol className={styles.transitionList}>{stage.transitions.map((transition) => <li key={transition.id}><div><strong>{transition.actor}</strong><time dateTime={transition.occurredAt}>{formatDateTimeRu(transition.occurredAt)}</time></div><p>{workflowStageStatusSemantics[transition.fromStatus].label} → {workflowStageStatusSemantics[transition.toStatus].label}. {transition.comment}</p></li>)}</ol> : <p className={styles.muted}>Переходов пока нет</p>}</section>
      {stage.status === 'current' && canAdvance ? <div className={styles.stageAction}><Button variant="primary" size="s" type="button" disabled title="Переход подключится после появления API">Перевести на следующий этап</Button><span>Действие станет доступно после подключения API.</span></div> : null}
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
      <div className={styles.headerMain}><div><p className={styles.eyebrow}>WORKFLOW</p><h1>Взаимодействие с вузом</h1><p className={styles.headerContext}>{workflow.universityName} · {workflow.universityCity} · {workflow.workflowName}</p></div>{currentStage && currentSemantics ? <div className={styles.headerCurrent}><span>Текущий этап</span><strong>{currentStage.name}</strong><StatusBadge intent={currentSemantics.intent}>{currentSemantics.label}</StatusBadge></div> : null}</div>
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
  const canAdvance = canAdvanceOverride ?? (user?.role === 'admin' || user?.role === 'manager');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const stages = useMemo(() => query.data?.stages.slice().sort((left, right) => left.orderIndex - right.orderIndex) ?? [], [query.data]);
  const selectedStage = useMemo(() => {
    if (!stages.length) return null;
    return stages.find((stage) => stage.id === selectedId) ?? stages.find((stage) => stage.status === 'current') ?? query.data?.currentStage ?? stages[0];
  }, [query.data?.currentStage, selectedId, stages]);
  const idPrefix = `workflow-${instanceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

  if (query.isPending) return <WorkflowSkeleton mode={mode} />;
  if (query.isError || !query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;
  if (!stages.length || !selectedStage) return <WorkflowEmptyState />;

  return <div className={`${styles.page} ${mode === 'embedded' ? styles.embedded : ''}`}>{mode === 'page' ? <WorkflowHeader workflow={query.data} /> : null}<div className={styles.layout}><section className={styles.stagesPanel} aria-labelledby={`${idPrefix}-stages-title`}><div className={styles.panelHeading}><div><span className={styles.eyebrow}>Жизненный цикл проекта</span><h2 id={`${idPrefix}-stages-title`}>Этапы Workflow</h2></div><span className={styles.totalLabel}>{stages.length} этапов</span></div><ol className={styles.stageList}>{stages.map((stage) => <WorkflowStageItem key={stage.id} stage={stage} selected={stage.id === selectedStage.id} onSelect={() => setSelectedId(stage.id)} />)}</ol></section><WorkflowStageDetails stage={selectedStage} canAdvance={canAdvance} idPrefix={idPrefix} /></div></div>;
}

export function UniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  return <WorkflowView instanceId={id} mode="embedded" canAdvance={canAdvance} />;
}

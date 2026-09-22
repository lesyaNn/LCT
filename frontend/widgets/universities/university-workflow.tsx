'use client';

import Attachment from '@atomaro/icons/24/action/Attachment';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import Comments from '@atomaro/icons/24/communication/Comments';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import History from '@atomaro/icons/24/communication/History';
import InformationStroke from '@atomaro/icons/24/alert/InformationStroke';
import SkipStroke from '@atomaro/icons/24/alert/SkipStroke';
import Task from '@atomaro/icons/24/communication/Task';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { workflowStageStatusIntent, workflowStageStatusLabels } from '@/shared/lib/status-semantics';
import { getUniversityWorkflow, type UniversityWorkflowStage, type UniversityWorkflowStageStatus } from '@/shared/lib/universities-repository';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import styles from './university-workflow.module.css';

function StageStatusIcon({ status }: { status: UniversityWorkflowStageStatus }) {
  if (status === 'completed') return <CheckLarge size={18} fill="currentColor" />;
  if (status === 'current') return <InformationStroke size={18} fill="currentColor" />;
  if (status === 'overdue') return <ErrorStroke size={18} fill="currentColor" />;
  if (status === 'skipped') return <SkipStroke size={18} fill="currentColor" />;
  return <TimeStroke size={18} fill="currentColor" />;
}

function WorkflowStageItem({ stage, selected, onSelect }: { stage: UniversityWorkflowStage; selected: boolean; onSelect: () => void }) {
  return (
    <li className={`${styles.stageItem} ${selected ? styles.stageItemSelected : ''}`}>
      <button className={styles.stageButton} type="button" aria-current={selected ? 'step' : undefined} onClick={onSelect}>
        <span className={`${styles.stageMarker} ${styles[`status-${stage.status}`]}`} aria-hidden="true"><StageStatusIcon status={stage.status} /></span>
        <span className={styles.stageContent}>
          <span className={styles.stageTopline}><span className={styles.stageOrder}>{stage.orderIndex}</span><strong>{stage.name}</strong></span>
          <span className={styles.stageMeta}><StatusBadge intent={workflowStageStatusIntent[stage.status]}>{workflowStageStatusLabels[stage.status]}</StatusBadge><span className={stage.status === 'overdue' ? styles.overdue : undefined}><TimeStroke size={14} fill="currentColor" />{formatDateRu(stage.deadline)}</span></span>
        </span>
      </button>
    </li>
  );
}

function CommentsBlock({ stage }: { stage: UniversityWorkflowStage }) {
  const [showAll, setShowAll] = useState(false);
  const comments = showAll ? stage.comments : stage.comments.slice(0, 3);
  return (
    <section className={styles.detailSection} aria-labelledby="workflow-comments-title">
      <div className={styles.detailSectionHeading}><h3 id="workflow-comments-title"><Comments size={18} fill="currentColor" />Комментарии</h3>{stage.comments.length > 3 ? <Button variant="ghost" size="s" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : 'Показать все'}</Button> : null}</div>
      <ul className={styles.commentList}>{comments.map((comment) => <li key={comment.id}><div className={styles.commentMeta}><strong>{comment.author}</strong><time dateTime={comment.occurredAt}>{formatDateTimeRu(comment.occurredAt)}</time></div><p>{comment.text}</p></li>)}</ul>
    </section>
  );
}

function WorkflowStageDetails({ stage, canAdvance }: { stage: UniversityWorkflowStage; canAdvance: boolean }) {
  return (
    <section className={styles.detailPanel} aria-labelledby="workflow-stage-details-title">
      <div className={styles.detailHeader}><div><span className={styles.eyebrow}>Детали этапа {stage.orderIndex} из 14</span><h2 id="workflow-stage-details-title">{stage.name}</h2></div><StatusBadge intent={workflowStageStatusIntent[stage.status]}>{workflowStageStatusLabels[stage.status]}</StatusBadge></div>
      <dl className={styles.detailFacts}><div><dt>Дедлайн</dt><dd className={stage.status === 'overdue' ? styles.overdue : undefined}><TimeStroke size={16} fill="currentColor" />{formatDateRu(stage.deadline)}</dd></div><div><dt>Ответственный</dt><dd>{stage.responsible ? <><Avatar initials={stage.responsible.name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2)} size="s" />{stage.responsible.name}</> : 'Не назначен'}</dd></div></dl>
      <CommentsBlock stage={stage} />
      <section className={styles.detailSection} aria-labelledby="workflow-attachments-title"><div className={styles.detailSectionHeading}><h3 id="workflow-attachments-title"><Attachment size={18} fill="currentColor" />Вложения</h3></div>{stage.attachments.length ? <ul className={styles.attachmentList}>{stage.attachments.map((attachment) => <li key={attachment.id}><Attachment size={18} fill="currentColor" /><span><strong>{attachment.fileName}</strong><small>{attachment.fileType} · {attachment.fileSize}</small></span></li>)}</ul> : <p className={styles.muted}>Вложений пока нет</p>}</section>
      <section className={styles.detailSection} aria-labelledby="workflow-tasks-title"><div className={styles.detailSectionHeading}><h3 id="workflow-tasks-title"><Task size={18} fill="currentColor" />Задачи этапа</h3></div><ul className={styles.taskList}>{stage.tasks.map((task) => <li key={task.id}><label><input type="checkbox" checked={task.completed} disabled readOnly /><span className={task.completed ? styles.taskCompleted : undefined}>{task.label}</span></label></li>)}</ul></section>
      <section className={styles.detailSection} aria-labelledby="workflow-transition-title"><div className={styles.detailSectionHeading}><h3 id="workflow-transition-title"><History size={18} fill="currentColor" />История переходов</h3></div>{stage.transitions.length ? <ol className={styles.transitionList}>{stage.transitions.map((transition) => <li key={transition.id}><div><strong>{transition.actor}</strong><time dateTime={transition.occurredAt}>{formatDateTimeRu(transition.occurredAt)}</time></div><p>{workflowStageStatusLabels[transition.fromStatus]} → {workflowStageStatusLabels[transition.toStatus]}. {transition.comment}</p></li>)}</ol> : <p className={styles.muted}>Переходов пока нет</p>}</section>
      {stage.status === 'current' && canAdvance ? <div className={styles.stageAction}><Button variant="primary" size="s" type="button" disabled title="Переход подключится после появления API">Перевести на следующий этап</Button><span>Действие станет доступно после подключения API.</span></div> : null}
    </section>
  );
}

function WorkflowSkeleton() {
  return <div className={styles.skeleton} aria-live="polite" aria-busy="true"><div className={styles.skeletonStages}>{Array.from({ length: 7 }, (_, index) => <span key={index} />)}</div><div className={styles.skeletonDetails}><span /><span /><span /><span /></div></div>;
}

export function UniversityWorkflow({ id, canAdvance }: { id: string; canAdvance: boolean }) {
  const query = useQuery({ queryKey: ['university-workflow', id], queryFn: () => getUniversityWorkflow(id), staleTime: 30_000 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedStage = useMemo(() => {
    if (!query.data?.stages.length) return null;
    return query.data.stages.find((stage) => stage.id === selectedId) ?? query.data.stages.find((stage) => stage.status === 'current') ?? query.data.stages[0];
  }, [query.data, selectedId]);

  if (query.isPending) return <WorkflowSkeleton />;
  if (query.isError || !query.data || !selectedStage) return <RouteErrorState onRetry={() => void query.refetch()} />;

  return <div className={styles.page}><div className={styles.layout}><section className={styles.stagesPanel} aria-labelledby="workflow-stages-title"><div className={styles.panelHeading}><div><span className={styles.eyebrow}>Жизненный цикл проекта</span><h2 id="workflow-stages-title">Этапы Workflow</h2></div><span className={styles.totalLabel}>14 этапов</span></div><ol className={styles.stageList}>{query.data.stages.map((stage) => <WorkflowStageItem key={stage.id} stage={stage} selected={stage.id === selectedStage.id} onSelect={() => setSelectedId(stage.id)} />)}</ol></section><WorkflowStageDetails stage={selectedStage} canAdvance={canAdvance} /></div></div>;
}

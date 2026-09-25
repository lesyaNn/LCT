'use client';

import { useMemo, useState } from 'react';
import { DndContext, DragOverlay, KeyboardSensor, MouseSensor, TouchSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import DragVerticalDots from '@atomaro/icons/24/editor/DragVerticalDots';
import { useAuth } from '@/shared/auth/AuthProvider';
import { getAvailableWorkflowTransitionTargets } from '@/shared/lib/workflow-transition';
import { isRealWorkflowMode } from '@/shared/lib/universities-repository';
import { workflowStageKey, type WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { Toast } from '@/shared/ui/rtk/toast';
import { WorkflowTransitionModal, type WorkflowTransitionNotification } from '@/widgets/universities/workflow-transition-modal';
import { WorkflowCard } from './workflow-card';
import styles from './workflow-overview.module.css';

type Column = { key: string; name: string; order: number; items: WorkflowOverviewItem[] };
type PendingDrop = { item: WorkflowOverviewItem; targetStageId: string };

function transitionTargets(item: WorkflowOverviewItem): Map<string, string> {
  if (item.status === 'completed') return new Map();
  return new Map(getAvailableWorkflowTransitionTargets(item.workflow.stages, item.stage)
    .map((target) => {
      const stage = item.workflow.stages.find((candidate) => candidate.id === target.id);
      return stage ? [workflowStageKey(item.workflow, stage), stage.id] as const : null;
    })
    .filter((entry): entry is readonly [string, string] => entry !== null));
}

function DraggableWorkflowCard({ item, enabled }: { item: WorkflowOverviewItem; enabled: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: item.instanceId, disabled: !enabled });
  return <div ref={setNodeRef} className={isDragging ? styles.dragSource : undefined}>
    <WorkflowCard item={item} dragHandle={enabled ? <button className={styles.dragHandle} type="button" aria-label={`Переместить: ${item.universityName}`} title="Переместить" {...attributes} {...listeners}><DragVerticalDots size={16} fill="currentColor" /></button> : undefined} />
  </div>;
}

function WorkflowBoardColumn({ column, valid, active }: { column: Column; valid: boolean; active: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.key, disabled: !valid });
  return <section ref={setNodeRef} className={[styles.column, valid ? styles.validColumn : '', isOver ? styles.overColumn : ''].join(' ')} data-testid={valid ? 'workflow-valid-drop-target' : undefined} aria-label={`${column.name}, процессов: ${column.items.length}`}>
    <header><h2>{column.name}</h2><span>{column.items.length}</span></header>
    <div className={styles.columnCards}>{column.items.map((item) => <DraggableWorkflowCard item={item} enabled={active && item.status !== 'completed' && transitionTargets(item).size > 0} key={item.instanceId} />)}
      {isOver ? <div className={styles.dropPlaceholder}>Перевести сюда</div> : null}
    </div>
  </section>;
}

export function WorkflowBoard({ items }: { items: WorkflowOverviewItem[] }) {
  const { user } = useAuth();
  const canManage = !isRealWorkflowMode() && (user?.role === 'admin' || user?.role === 'manager');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingDrop | null>(null);
  const [notification, setNotification] = useState<WorkflowTransitionNotification | null>(null);
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );
  const columns = useMemo(() => {
    const map = new Map<string, Column>();
    for (const item of items) {
      for (const stage of item.workflow.stages) {
        const key = workflowStageKey(item.workflow, stage);
        if (!map.has(key)) map.set(key, { key, name: stage.name, order: stage.orderIndex, items: [] });
      }
      map.get(item.stageKey)?.items.push(item);
    }
    return [...map.values()].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name, 'ru'));
  }, [items]);
  const draggingItem = items.find((item) => item.instanceId === draggingId);
  const validTargets = draggingItem && canManage ? transitionTargets(draggingItem) : new Map<string, string>();
  const finishDrag = ({ active, over }: DragEndEvent) => {
    const item = items.find((candidate) => candidate.instanceId === String(active.id));
    const targetStageId = over && item && canManage ? transitionTargets(item).get(String(over.id)) : undefined;
    setDraggingId(null);
    if (item && targetStageId) setPending({ item, targetStageId });
  };

  return <>
    <DndContext sensors={sensors} onDragStart={(event) => setDraggingId(String(event.active.id))} onDragEnd={finishDrag} onDragCancel={() => setDraggingId(null)}>
      <div className={styles.boardScroll} aria-label="Доска Workflow"><div className={styles.board}>{columns.map((column) => <WorkflowBoardColumn column={column} valid={validTargets.has(column.key)} active={canManage} key={column.key} />)}</div></div>
      <DragOverlay>{draggingItem ? <div className={styles.dragOverlay}>{draggingItem.universityName}<small>{draggingItem.programName ?? draggingItem.stage.name}</small></div> : null}</DragOverlay>
    </DndContext>
    {pending ? <WorkflowTransitionModal open instanceId={pending.item.instanceId} universityId={pending.item.universityId} currentStage={pending.item.stage} stages={pending.item.workflow.stages} initialTargetStageId={pending.targetStageId} userId={user?.id} onClose={() => setPending(null)} onSuccess={() => setPending(null)} onNotify={setNotification} /> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </>;
}

'use client';

import { useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { DndContext, DragOverlay, KeyboardSensor, MouseSensor, TouchSensor, pointerWithin, rectIntersection, useDraggable, useDroppable, useSensor, useSensors, type CollisionDetection, type DragEndEvent } from '@dnd-kit/core';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import { getAvailableWorkflowTransitionTargets, type WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { getWorkflowAllowedTransitions, isRealWorkflowMode } from '@/shared/lib/universities-repository';
import { workflowStageKey, type WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { Toast } from '@/shared/ui/rtk/toast';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { WorkflowTransitionModal, type WorkflowTransitionNotification } from '@/widgets/universities/workflow-transition-modal';
import { WorkflowCard } from './workflow-card';
import styles from './workflow-overview.module.css';

type Column = { key: string; name: string; order: number; items: WorkflowOverviewItem[] };
type PendingDrop = { item: WorkflowOverviewItem; targetStageId: string; allowedTargets?: WorkflowTransitionTarget[] };

const columnCollisionDetection: CollisionDetection = (args) => args.pointerCoordinates
  ? pointerWithin(args)
  : rectIntersection(args);

function transitionTargets(item: WorkflowOverviewItem, allowedTargets?: WorkflowTransitionTarget[]): Map<string, string> {
  if (item.status === 'completed') return new Map();
  return new Map((allowedTargets ?? getAvailableWorkflowTransitionTargets(item.workflow.stages, item.stage))
    .map((target) => {
      const stage = item.workflow.stages.find((candidate) => candidate.id === target.id);
      return stage ? [workflowStageKey(item.workflow, stage), stage.id] as const : null;
    })
    .filter((entry): entry is readonly [string, string] => entry !== null));
}

function DraggableWorkflowCard({ item, enabled }: { item: WorkflowOverviewItem; enabled: boolean }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({ id: item.instanceId, disabled: !enabled });
  return <div ref={setNodeRef} className={isDragging ? styles.dragSource : undefined}>
    <WorkflowCard item={item} dragListeners={enabled ? { onMouseDown: (event) => listeners?.onMouseDown?.(event), onTouchStart: (event) => listeners?.onTouchStart?.(event) } : undefined} keyboardDragControl={enabled ? <button ref={setActivatorNodeRef} className={styles.keyboardDragHandle} type="button" aria-label={`Переместить: ${item.universityName}`} {...attributes} onKeyDown={(event) => listeners?.onKeyDown?.(event)}>Переместить</button> : undefined} />
  </div>;
}

function WorkflowBoardColumn({ column, valid, active }: { column: Column; valid: boolean; active: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.key });
  const validDrop = isOver && valid;
  return <section ref={setNodeRef} className={[styles.column, valid ? styles.validColumn : '', validDrop ? styles.overColumn : ''].join(' ')} data-testid={valid ? 'workflow-valid-drop-target' : undefined} aria-label={`${column.name}, процессов: ${column.items.length}`}>
    <header><h2>{column.name}</h2><StatusBadge intent="neutral" showIndicator={false}>{column.items.length}</StatusBadge></header>
    <div className={styles.columnCards}>{column.items.map((item) => <DraggableWorkflowCard item={item} enabled={active && item.status !== 'completed' && transitionTargets(item).size > 0} key={item.instanceId} />)}
      {validDrop ? <div className={styles.dropPlaceholder}>Перевести сюда</div> : null}
    </div>
  </section>;
}

export function WorkflowBoard({ items }: { items: WorkflowOverviewItem[] }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const realWorkflow = isRealWorkflowMode();
  const canManage = hasPermission(user, 'workflow.change_status');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingDrop | null>(null);
  const [resolvingDrop, setResolvingDrop] = useState(false);
  const dropInFlight = useRef(false);
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
  const canDrag = canManage && !resolvingDrop && !pending;
  const validTargets = draggingItem && canDrag ? transitionTargets(draggingItem) : new Map<string, string>();
  const finishDrag = async ({ active, over }: DragEndEvent) => {
    const item = items.find((candidate) => candidate.instanceId === String(active.id));
    setDraggingId(null);
    if (!item || !over || !canDrag || String(over.id) === item.stageKey || dropInFlight.current) return;
    dropInFlight.current = true;
    setResolvingDrop(true);
    const targetKey = String(over.id);
    const wasLocallyAllowed = transitionTargets(item).has(targetKey);
    try {
      const allowedTargets = realWorkflow ? (await queryClient.fetchQuery({
        queryKey: queryKeys.universities.workflowAllowed(item.instanceId),
        queryFn: () => getWorkflowAllowedTransitions(item.instanceId),
        staleTime: 30_000,
      })).map((target) => ({ id: target.id, orderIndex: target.order_index, name: target.name })) : undefined;
      const targetStageId = transitionTargets(item, allowedTargets).get(targetKey);
      if (targetStageId) setPending({ item, targetStageId, allowedTargets });
      else {
        setNotification({ intent: 'error', title: 'Переход недоступен', message: wasLocallyAllowed ? 'Доступные переходы изменились. Обновите данные и попробуйте снова.' : 'На выбранный этап нельзя перейти из текущего. Выберите доступную колонку.' });
        if (wasLocallyAllowed) await queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview });
      }
    } catch (cause) {
      setNotification({ intent: 'error', title: 'Не удалось проверить переход', message: normalizeApiError(cause).message });
    } finally {
      dropInFlight.current = false;
      setResolvingDrop(false);
    }
  };

  return <>
    <DndContext sensors={sensors} collisionDetection={columnCollisionDetection} onDragStart={(event) => setDraggingId(String(event.active.id))} onDragEnd={(event) => { void finishDrag(event); }} onDragCancel={() => setDraggingId(null)}>
      <div className={styles.boardScroll} aria-label="Доска Workflow"><div className={styles.board}>{columns.map((column) => <WorkflowBoardColumn column={column} valid={validTargets.has(column.key)} active={canDrag} key={column.key} />)}</div></div>
      <DragOverlay>{draggingItem ? <div className={styles.dragOverlay} aria-hidden="true" inert><WorkflowCard item={draggingItem} /></div> : null}</DragOverlay>
    </DndContext>
    {pending ? <WorkflowTransitionModal open instanceId={pending.item.instanceId} universityId={pending.item.universityId} currentStage={pending.item.stage} stages={pending.item.workflow.stages} allowedTargets={pending.allowedTargets} initialTargetStageId={pending.targetStageId} userId={user?.id} onClose={() => setPending(null)} onSuccess={() => setPending(null)} onNotify={setNotification} /> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </>;
}

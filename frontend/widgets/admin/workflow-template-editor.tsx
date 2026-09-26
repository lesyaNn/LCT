'use client';

import { visibleWorkflowDescription } from '@/shared/lib/visible-workflow-description';

import { useEffect, useRef, useState } from 'react';
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from '@dnd-kit/core';
import { SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable';
import AddLarge from '@atomaro/icons/24/action/AddLarge';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { moveWorkflowStage } from '@/shared/lib/workflow-template-cache';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { useAddWorkflowStage, useSaveWorkflowStageOrder, useUpdateWorkflowStage } from '@/shared/lib/workflow-template-mutations';
import { getWorkflowTemplate, workflowTemplateDetailQueryKey, type CreateWorkflowStageInput, type UpdateWorkflowStageInput, type WorkflowTemplate, type WorkflowTemplateStage } from '@/shared/lib/workflow-templates-repository';
import { Button } from '@/shared/ui/rtk/button';
import { EmptyState } from '@/shared/ui/empty-state';
import { RouteErrorState } from '@/shared/ui/route-error-state';
import { Skeleton, SkeletonGroup } from '@/shared/ui/skeleton';
import { Toast, type ToastIntent } from '@/shared/ui/rtk/toast';
import { AddStageModal, StageConfirmationModal } from './workflow-template-modals';
import { WorkflowStageRow } from './workflow-stage-row';
import styles from './workflow-template-editor.module.css';

interface Notification { intent: ToastIntent; title: string; message?: string }
interface Confirmation { stage: WorkflowTemplateStage; mode: 'delete' }

function EditorSkeleton() {
  return <SkeletonGroup label="Загрузка редактора Workflow"><Skeleton variant="text" width="280px" /><Skeleton variant="text" width="min(60%, 460px)" height={36} /><Skeleton height={400} /></SkeletonGroup>;
}

function EditorHeader({ template, dirty, savingOrder, onAdd, onSaveOrder, onCancelOrder }: { template: WorkflowTemplate; dirty: boolean; savingOrder: boolean; onAdd: () => void; onSaveOrder: () => void; onCancelOrder: () => void }) {
  return <header className={styles.editorHeader}><div><h1>{template.name}</h1>{visibleWorkflowDescription(template.description) ? <p className={styles.description}>{template.description}</p> : null}</div><div className={styles.headerActions}>{dirty ? <><span className={styles.dirtyStatus} role="status">Порядок изменён</span><Button type="button" variant="ghost" size="m" disabled={savingOrder} onClick={onCancelOrder}>Отменить</Button><Button type="button" variant="primary" size="m" loading={savingOrder} disabled={savingOrder} onClick={onSaveOrder}><CheckLarge size={18} fill="currentColor" />Сохранить порядок</Button></> : <Button type="button" variant="primary" size="m" onClick={onAdd}><AddLarge size={18} fill="currentColor" />Добавить этап</Button>}</div></header>;
}

export function WorkflowTemplateEditor({ templateId }: { templateId: string }) {
  const queryClient = useQueryClient();
  const detailKey = workflowTemplateDetailQueryKey(templateId);
  const query = useQuery({ queryKey: detailKey, queryFn: ({ signal }) => getWorkflowTemplate(templateId, signal), staleTime: 30_000 });
  const updateStage = useUpdateWorkflowStage(templateId);
  const addStage = useAddWorkflowStage(templateId);
  const saveOrder = useSaveWorkflowStageOrder(templateId);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const savedStagesRef = useRef<WorkflowTemplateStage[]>([]);
  const [orderDirty, setOrderDirty] = useState(false);
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirmationError, setConfirmationError] = useState<string | null>(null);
  const [notification, setNotification] = useState<Notification | null>(null);
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    if (!orderDirty && query.data) savedStagesRef.current = query.data.stages.map((stage) => ({ ...stage }));
  }, [orderDirty, query.data]);

  if (query.isPending) return <EditorSkeleton />;
  if (!query.data) return <RouteErrorState onRetry={() => void query.refetch()} />;

  const template = query.data;
  const stages = template.stages;
  const activeStage = stages.find((stage) => stage.id === activeStageId) ?? null;

  const setStages = (nextStages: WorkflowTemplateStage[]) => {
    queryClient.setQueryData<WorkflowTemplate>(detailKey, (current) => current ? { ...current, stages: nextStages } : current);
  };

  const reorderStages = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex || toIndex < 0 || toIndex >= stages.length) return;
    if (!orderDirty) savedStagesRef.current = stages.map((stage) => ({ ...stage }));
    const next = moveWorkflowStage(stages, fromIndex, toIndex);
    setStages(next);
    setOrderDirty(true);
    setAnnouncement(`Этап «${stages[fromIndex].name}» перемещён на позицию ${toIndex + 1}.`);
  };

  const handleDragStart = ({ active }: DragStartEvent) => setActiveStageId(String(active.id));
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    setActiveStageId(null);
    if (!over || active.id === over.id) return;
    reorderStages(stages.findIndex((stage) => stage.id === active.id), stages.findIndex((stage) => stage.id === over.id));
  };

  const cancelOrder = () => {
    setStages(savedStagesRef.current.map((stage) => ({ ...stage })));
    setOrderDirty(false);
    setAnnouncement('Изменения порядка отменены.');
  };

  const persistOrder = async () => {
    const targetStages = stages.map((stage) => ({ ...stage }));
    const previousStages = savedStagesRef.current.map((stage) => ({ ...stage }));
    try {
      await saveOrder.mutateAsync({ previousStages, targetStages });
      savedStagesRef.current = targetStages;
      setOrderDirty(false);
      setNotification({ intent: 'success', title: 'Порядок сохранён' });
    } catch (cause) {
      setOrderDirty(false);
      setNotification({ intent: 'error', title: 'Не удалось сохранить порядок', message: normalizeApiError(cause).message });
    }
  };

  const update = async (stageId: string, patch: UpdateWorkflowStageInput, successTitle?: string) => {
    try {
      await updateStage.mutateAsync({ stageId, patch });
      if (successTitle) setNotification({ intent: 'success', title: successTitle });
    } catch (cause) {
      if (patch.name === undefined) setNotification({ intent: 'error', title: 'Изменение не сохранено', message: normalizeApiError(cause).message });
      throw cause;
    }
  };

  const createStage = async (input: CreateWorkflowStageInput) => {
    await addStage.mutateAsync(input);
    setAddOpen(false);
    setNotification({ intent: 'success', title: 'Этап добавлен' });
  };

  const confirmRetire = async () => {
    if (!confirmation) return;
    setConfirmationError(null);
    try {
      await update(confirmation.stage.id, { isActive: false });
      setConfirmation(null);
      setNotification({ intent: 'success', title: 'Этап удалён из активного шаблона' });
    } catch (cause) {
      setConfirmationError(normalizeApiError(cause).message);
    }
  };

  const savingStageId = updateStage.isPending ? updateStage.variables?.stageId : undefined;

  return <div className={styles.page}>
    <EditorHeader template={template} dirty={orderDirty} savingOrder={saveOrder.isPending} onAdd={() => setAddOpen(true)} onSaveOrder={() => void persistOrder()} onCancelOrder={cancelOrder} />
    <span className={styles.srOnly} aria-live="polite">{announcement}</span>
    <section className={styles.stageSurface} aria-labelledby="workflow-stages-heading">
      <div className={styles.surfaceHeader}><div><h2 id="workflow-stages-heading">Этапы</h2><p>{stages.length} {stages.length === 1 ? 'этап' : 'этапов'} в шаблоне</p></div>{!orderDirty ? <Button type="button" variant="secondary" size="s" onClick={() => setAddOpen(true)}><AddLarge size={16} fill="currentColor" />Добавить этап</Button> : null}</div>
      {stages.length ? <><div className={styles.columnHeader} aria-hidden="true"><span /><span>№</span><span>Название</span><span>Обяз.</span><span>Активен</span><span>Оценка дней</span><span>Действия</span></div><DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragCancel={() => setActiveStageId(null)} onDragEnd={handleDragEnd}><SortableContext items={stages.map((stage) => stage.id)} strategy={verticalListSortingStrategy}><ol className={styles.stageList}>{stages.map((stage, index) => <WorkflowStageRow key={stage.id} stage={stage} index={index} count={stages.length} saving={savingStageId === stage.id || saveOrder.isPending} orderDirty={orderDirty} readOnly={false} onMove={reorderStages} onUpdate={update} onDelete={(item) => { setConfirmationError(null); setConfirmation({ stage: item, mode: 'delete' }); }} />)}</ol></SortableContext><DragOverlay>{activeStage ? <div className={styles.dragOverlay}>{activeStage.orderIndex}. {activeStage.name}</div> : null}</DragOverlay></DndContext></> : <EmptyState title="В шаблоне пока нет этапов" description="Добавьте первый этап, чтобы начать настройку маршрута." headingLevel={3} primaryAction={{ label: 'Добавить этап', onClick: () => setAddOpen(true) }} />}
    </section>
    {addOpen ? <AddStageModal stages={stages.filter((stage) => !stage.id.startsWith('temp:stage:'))} pending={addStage.isPending} onClose={() => { if (!addStage.isPending) setAddOpen(false); }} onSubmit={createStage} onError={(error) => setNotification({ intent: 'error', title: 'Этап не добавлен', message: error.message })} /> : null}
    {confirmation ? <StageConfirmationModal stage={confirmation.stage} mode={confirmation.mode} pending={updateStage.isPending} error={confirmationError} onClose={() => { if (!updateStage.isPending) setConfirmation(null); }} onConfirm={() => void confirmRetire()} /> : null}
    {notification ? <div className={styles.toastViewport}><Toast intent={notification.intent} title={notification.title} message={notification.message} onClose={() => setNotification(null)} /></div> : null}
  </div>;
}

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { applyServerErrorsToForm, normalizeApiError } from '@/shared/lib/api-errors';
import { applyOptimisticWorkflowTransition, getAvailableWorkflowTransitionTargets, getLocalTodayIso, isWorkflowTransitionDraft, workflowTransitionDraftKey, type WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { invalidateWorkflowRelatedQueries } from '@/shared/lib/workflow-cache';
import { getApiUniversityWorkflow, isWorkflowApiInstanceId, transitionWorkflowInstance, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowStage, type WorkflowInstanceApiRecord } from '@/shared/lib/universities-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Input, Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import type { ToastIntent } from '@/shared/ui/rtk/toast';
import styles from './workflow-transition-modal.module.css';

const COMMENT_MIN_LENGTH = 10;
const COMMENT_MAX_LENGTH = 5000;
const transitionFields = ['targetStageId', 'comment', 'dueDate'] as const;

type TransitionValues = { targetStageId: string; comment: string; dueDate: string };

function createTransitionSchema(today: string, targets: WorkflowTransitionTarget[]) {
  const targetIds = new Set(targets.map((target) => target.id));
  return z.object({
    targetStageId: z.string().refine((value) => targetIds.has(value), 'Выберите доступный целевой этап.'),
    comment: z.string().max(COMMENT_MAX_LENGTH, `Максимум ${COMMENT_MAX_LENGTH} символов.`).refine((value) => value.trim().length >= COMMENT_MIN_LENGTH, `Минимум ${COMMENT_MIN_LENGTH} символов.`),
    dueDate: z.string().refine((value) => !value || value >= today, 'Дедлайн не может быть в прошлом.'),
  });
}

export interface WorkflowTransitionNotification {
  intent: ToastIntent;
  title: string;
  message: string;
}

type TransitionMutationContext = { previousWorkflow?: UniversityWorkflow };

export function WorkflowTransitionModal({ open, instanceId, universityId, currentStage, stages, allowedTargets, initialTargetStageId, userId, onClose, onSuccess, onNotify }: { open: boolean; instanceId: string; universityId?: string | null; currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; allowedTargets?: WorkflowTransitionTarget[]; initialTargetStageId?: string; userId?: string | null; onClose: () => void; onSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const queryClient = useQueryClient();
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const [showDiscard, setShowDiscard] = useState(false);
  const [serverFormError, setServerFormError] = useState<string | null>(null);
  const realWorkflow = !isMockDataSourceFor('workflow');
  const targets = useMemo(() => realWorkflow ? allowedTargets ?? [] : getAvailableWorkflowTransitionTargets(stages, currentStage), [allowedTargets, currentStage, realWorkflow, stages]);
  const defaultTargetId = targets.find((target) => target.id === initialTargetStageId)?.id ?? targets[0]?.id ?? '';
  const targetKey = targets.map((target) => target.id).join('|');
  const targetIds = useMemo(() => new Set(targets.map((target) => target.id)), [targets]);
  const apiAvailable = isWorkflowApiInstanceId(instanceId) && targets.length > 0 && targets.every((target) => isWorkflowApiInstanceId(target.id));
  const today = getLocalTodayIso();
  const schema = useMemo(() => createTransitionSchema(today, targets), [targets, today]);
  const storageKey = workflowTransitionDraftKey(instanceId, currentStage.id, userId);
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, submitCount } } = useForm<TransitionValues>({
    resolver: zodResolver(schema),
    mode: 'onBlur',
    reValidateMode: 'onChange',
    defaultValues: { targetStageId: defaultTargetId, comment: '', dueDate: '' },
  });
  const values = useWatch({ control });
  const targetStageId = values.targetStageId ?? defaultTargetId;
  const comment = values.comment ?? '';
  const dueDate = values.dueDate ?? '';
  const hasDraft = comment.length > 0 || dueDate.length > 0 || targetStageId !== defaultTargetId;

  useEffect(() => {
    if (!open) return;
    let restored: TransitionValues | null = null;
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (isWorkflowTransitionDraft(parsed, targetIds)) {
        restored = { targetStageId: parsed.targetStageId, comment: parsed.comment, dueDate: parsed.dueDate >= today ? parsed.dueDate : '' };
      } else if (raw) window.localStorage.removeItem(storageKey);
    } catch {
      try { window.localStorage.removeItem(storageKey); } catch { /* Storage can be unavailable in privacy mode. */ }
    }
    reset(restored ? { ...restored, targetStageId: initialTargetStageId ?? restored.targetStageId } : { targetStageId: defaultTargetId, comment: '', dueDate: '' });
  }, [defaultTargetId, initialTargetStageId, open, reset, storageKey, targetIds, targetKey, today]);

  useEffect(() => {
    if (!open) return undefined;
    const timer = window.setTimeout(() => {
      try {
        if (!hasDraft) { window.localStorage.removeItem(storageKey); return; }
        window.localStorage.setItem(storageKey, JSON.stringify({ version: 1, targetStageId, comment, dueDate, updatedAt: new Date().toISOString() }));
      } catch { /* Draft persistence is a convenience and must not block editing. */ }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [comment, dueDate, hasDraft, open, storageKey, targetStageId]);

  const clearDraft = () => { try { window.localStorage.removeItem(storageKey); } catch { /* Ignore unavailable storage. */ } };
  const transition = useMutation<WorkflowInstanceApiRecord, unknown, TransitionValues, TransitionMutationContext>({
    mutationFn: (input) => transitionWorkflowInstance(instanceId, input.targetStageId, input.comment.trim(), input.dueDate || undefined),
    onMutate: async (input) => {
      if (realWorkflow) return {};
      await queryClient.cancelQueries({ queryKey: workflowQueryKey(instanceId) });
      const previousWorkflow = queryClient.getQueryData<UniversityWorkflow>(workflowQueryKey(instanceId));
      if (previousWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), applyOptimisticWorkflowTransition(previousWorkflow, input.targetStageId));
      return { previousWorkflow };
    },
    onSuccess: async (record) => {
      clearDraft();
      if (realWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await invalidateWorkflowRelatedQueries(queryClient, instanceId, universityId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowAllowed(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
      ]);
      onNotify({ intent: 'success', title: 'Этап успешно переведён', message: 'Workflow синхронизирован с сервером.' });
      onSuccess();
    },
    onError: async (cause, _variables, context) => {
      if (context?.previousWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), context.previousWorkflow);
      const normalized = normalizeApiError(cause, { defaultCode: 'WORKFLOW_INVALID_TRANSITION' });
      if (normalized.status === 409 || normalized.status === 400 || normalized.code === 'WORKFLOW_INVALID_TRANSITION') await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowAllowed(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
      ]);
    },
  });

  const submit = handleSubmit(async (input) => {
    if (transition.isPending) return;
    setServerFormError(null);
    try {
      await transition.mutateAsync(input);
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'WORKFLOW_INVALID_TRANSITION' });
      const mapped = applyServerErrorsToForm(normalized, { fields: transitionFields, fieldMap: { target_instance_stage_id: 'targetStageId', due_date: 'dueDate' }, setError, setFocus });
      if (normalized.kind === 'validation') {
        setServerFormError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : 'Исправьте ошибки в форме.');
        return;
      }
      onNotify({ intent: 'error', title: normalized.kind === 'permission' ? 'Нет прав' : 'Переход не выполнен', message: normalized.message });
    }
  });

  const target = targets.find((item) => item.id === targetStageId) ?? targets[0];
  const modalClose = showDiscard ? () => setShowDiscard(false) : () => {
    if (transition.isPending) return;
    if (hasDraft) setShowDiscard(true);
    else { clearDraft(); onClose(); }
  };
  if (!open) return null;

  const targetId = 'workflow-transition-target';
  const targetErrorId = `${targetId}-error`;
  const commentId = 'workflow-transition-comment';
  const commentErrorId = `${commentId}-error`;
  const commentHintId = `${commentId}-hint`;
  const commentCountId = `${commentId}-count`;
  const dueDateId = 'workflow-transition-due-date';
  const dueDateErrorId = `${dueDateId}-error`;
  const dueDateHintId = `${dueDateId}-hint`;
  const commentRegistration = register('comment');
  const showBanner = Boolean(serverFormError || (submitCount > 0 && Object.keys(errors).length));

  return <Modal title="Перевести на следующий этап" onClose={modalClose} initialFocusRef={commentRef}><div className={styles.context}><span>Текущий: {currentStage.orderIndex}. {currentStage.name}</span><ArrowRight size={16} fill="currentColor" aria-hidden="true" /><span>Следующий: {target ? `${target.orderIndex}. ${target.name}` : 'нет доступного этапа'}</span></div>{showDiscard ? <div className={styles.discard} role="alertdialog" aria-labelledby="workflow-transition-discard-title" aria-describedby="workflow-transition-discard-description"><h3 id="workflow-transition-discard-title">Есть несохранённые изменения. Закрыть окно?</h3><p id="workflow-transition-discard-description">Черновик будет удалён, а введённые данные потеряны.</p><div className={styles.actions}><Button variant="ghost" size="s" type="button" autoFocus onClick={() => setShowDiscard(false)}>Продолжить редактирование</Button><Button variant="secondary" size="s" type="button" onClick={() => { clearDraft(); setShowDiscard(false); onClose(); }}>Закрыть без сохранения</Button></div></div> : <form className={styles.form} onSubmit={submit} noValidate>{showBanner ? <FormErrorBanner>{serverFormError ?? undefined}</FormErrorBanner> : null}<FormField label="Целевой этап" htmlFor={targetId} error={errors.targetStageId?.message} errorId={targetErrorId}><Select id={targetId} disabled={transition.isPending || targets.length <= 1} aria-invalid={Boolean(errors.targetStageId)} aria-describedby={errors.targetStageId ? targetErrorId : undefined} {...register('targetStageId')}>{targets.map((item) => <option value={item.id} key={item.id}>{item.orderIndex}. {item.name}</option>)}</Select></FormField><FormField label="Комментарий" htmlFor={commentId} required error={errors.comment?.message} errorId={commentErrorId} hint={`Минимум ${COMMENT_MIN_LENGTH} символов`} hintId={commentHintId}><TextArea id={commentId} ref={(element) => { commentRegistration.ref(element); commentRef.current = element; }} name={commentRegistration.name} onBlur={commentRegistration.onBlur} onChange={commentRegistration.onChange} maxLength={COMMENT_MAX_LENGTH} minLength={COMMENT_MIN_LENGTH} rows={5} placeholder="Опишите, что сделано, почему переводите..." required aria-required="true" aria-invalid={Boolean(errors.comment)} aria-describedby={`${errors.comment ? commentErrorId : commentHintId} ${commentCountId}`} /><span id={commentCountId} className={styles.counter}>{comment.length} / {COMMENT_MAX_LENGTH}</span></FormField>{!realWorkflow ? <FormField label="Дедлайн для следующего этапа (необязательно)" htmlFor={dueDateId} error={errors.dueDate?.message} errorId={dueDateErrorId} hint="Если не указать, будет рассчитан автоматически" hintId={dueDateHintId}><span className={styles.dateControl}><TimeStroke size={16} fill="currentColor" aria-hidden="true" /><Input id={dueDateId} type="date" min={today} aria-invalid={Boolean(errors.dueDate)} aria-describedby={errors.dueDate ? dueDateErrorId : dueDateHintId} {...register('dueDate')} /></span></FormField> : null}{!apiAvailable ? <p className={styles.integrationHint}>Нет доступного перехода. Обновите Workflow.</p> : null}<div className={styles.actions}><Button variant="ghost" size="s" type="button" disabled={transition.isPending} onClick={modalClose}>Отмена</Button><Button variant="primary" size="s" type="submit" loading={transition.isPending} disabled={!apiAvailable || transition.isPending}>Перевести</Button></div></form>}</Modal>;
}

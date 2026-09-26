'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import { applyServerErrorsToForm, normalizeApiError } from '@/shared/lib/api-errors';
import { applyOptimisticWorkflowRollback, getAvailableWorkflowRollbackTargets, type WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { invalidateWorkflowRelatedQueries } from '@/shared/lib/workflow-cache';
import { getApiUniversityWorkflow, isWorkflowApiInstanceId, rollbackWorkflowInstance, workflowQueryKey, type UniversityWorkflow, type UniversityWorkflowStage, type WorkflowInstanceApiRecord } from '@/shared/lib/universities-repository';
import { queryKeys } from '@/shared/lib/query-keys';
import { Button } from '@/shared/ui/rtk/button';
import { FormErrorBanner, FormField } from '@/shared/ui/rtk/form-field';
import { Select, TextArea } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import type { WorkflowTransitionNotification } from './workflow-transition-modal';
import styles from './workflow-transition-modal.module.css';

const COMMENT_MIN_LENGTH = 10;
const COMMENT_MAX_LENGTH = 5000;
const rollbackFields = ['targetStageId', 'comment'] as const;

type RollbackValues = { targetStageId: string; comment: string };

function createRollbackSchema(targets: WorkflowTransitionTarget[]) {
  const targetIds = new Set(targets.map((target) => target.id));
  return z.object({
    targetStageId: z.string().refine((value) => targetIds.has(value), 'Выберите этап для возврата.'),
    comment: z.string().max(COMMENT_MAX_LENGTH, `Максимум ${COMMENT_MAX_LENGTH} символов.`).refine((value) => value.trim().length >= COMMENT_MIN_LENGTH, `Минимум ${COMMENT_MIN_LENGTH} символов.`),
  });
}

type RollbackMutationContext = { previousWorkflow?: UniversityWorkflow };

function workflowRollbackDraftKey(instanceId: string, currentStageId: string, userId?: string | null): string {
  const owner = userId || 'anonymous';
  return `workflow.rollback.draft.v1:${instanceId}:${currentStageId}:${owner}`;
}

export function WorkflowRollbackModal({ open, instanceId, universityId, currentStage, stages, allowedTargets, userId, onClose, onSuccess, onNotify }: { open: boolean; instanceId: string; universityId?: string | null; currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; allowedTargets?: WorkflowTransitionTarget[]; userId?: string | null; onClose: () => void; onSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const queryClient = useQueryClient();
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const [showDiscard, setShowDiscard] = useState(false);
  const [serverFormError, setServerFormError] = useState<string | null>(null);
  const realWorkflow = !isMockDataSourceFor('workflow');
  const targets = useMemo(() => realWorkflow ? allowedTargets ?? [] : getAvailableWorkflowRollbackTargets(stages, currentStage), [allowedTargets, currentStage, realWorkflow, stages]);
  const defaultTargetId = targets[0]?.id ?? '';
  const targetKey = targets.map((target) => target.id).join('|');
  const targetIds = useMemo(() => new Set(targets.map((target) => target.id)), [targets]);
  const apiAvailable = isWorkflowApiInstanceId(instanceId) && targets.length > 0 && targets.every((target) => isWorkflowApiInstanceId(target.id));
  const schema = useMemo(() => createRollbackSchema(targets), [targets]);
  const storageKey = workflowRollbackDraftKey(instanceId, currentStage.id, userId);
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, submitCount } } = useForm<RollbackValues>({
    resolver: zodResolver(schema),
    mode: 'onBlur',
    reValidateMode: 'onChange',
    defaultValues: { targetStageId: defaultTargetId, comment: '' },
  });
  const values = useWatch({ control });
  const targetStageId = values.targetStageId ?? defaultTargetId;
  const comment = values.comment ?? '';
  const hasDraft = comment.length > 0 || targetStageId !== defaultTargetId;

  useEffect(() => {
    if (!open) return;
    let restored: RollbackValues | null = null;
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (parsed && typeof parsed === 'object'
        && (parsed as { version?: unknown }).version === 1
        && typeof (parsed as { comment?: unknown }).comment === 'string'
        && typeof (parsed as { targetStageId?: unknown }).targetStageId === 'string'
        && targetIds.has((parsed as { targetStageId: string }).targetStageId)) {
        restored = { targetStageId: (parsed as { targetStageId: string }).targetStageId, comment: (parsed as { comment: string }).comment.slice(0, COMMENT_MAX_LENGTH) };
      } else if (raw) window.localStorage.removeItem(storageKey);
    } catch {
      try { window.localStorage.removeItem(storageKey); } catch { /* Storage can be unavailable in privacy mode. */ }
    }
    reset(restored ?? { targetStageId: defaultTargetId, comment: '' });
  }, [defaultTargetId, open, reset, storageKey, targetIds, targetKey]);

  useEffect(() => {
    if (!open) return undefined;
    const timer = window.setTimeout(() => {
      try {
        if (!hasDraft) { window.localStorage.removeItem(storageKey); return; }
        window.localStorage.setItem(storageKey, JSON.stringify({ version: 1, targetStageId, comment, updatedAt: new Date().toISOString() }));
      } catch { /* Draft persistence is a convenience and must not block editing. */ }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [comment, hasDraft, open, storageKey, targetStageId]);

  const clearDraft = () => { try { window.localStorage.removeItem(storageKey); } catch { /* Ignore unavailable storage. */ } };
  const rollback = useMutation<WorkflowInstanceApiRecord, unknown, RollbackValues, RollbackMutationContext>({
    mutationFn: (input) => rollbackWorkflowInstance(instanceId, input.targetStageId, input.comment.trim()),
    onMutate: async (input) => {
      if (realWorkflow) return {};
      await queryClient.cancelQueries({ queryKey: workflowQueryKey(instanceId) });
      const previousWorkflow = queryClient.getQueryData<UniversityWorkflow>(workflowQueryKey(instanceId));
      if (previousWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), applyOptimisticWorkflowRollback(previousWorkflow, input.targetStageId));
      return { previousWorkflow };
    },
    onSuccess: async (record) => {
      clearDraft();
      if (realWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), getApiUniversityWorkflow(record));
      await invalidateWorkflowRelatedQueries(queryClient, instanceId, universityId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowAllowed(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowRollbackTargets(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
      ]);
      onNotify({ intent: 'success', title: 'Этап возвращён', message: 'Workflow синхронизирован с сервером.' });
      onSuccess();
    },
    onError: async (cause, _variables, context) => {
      if (context?.previousWorkflow) queryClient.setQueryData(workflowQueryKey(instanceId), context.previousWorkflow);
      const normalized = normalizeApiError(cause, { defaultCode: 'WORKFLOW_INVALID_TRANSITION' });
      if (normalized.status === 409 || normalized.status === 400 || normalized.code === 'WORKFLOW_INVALID_TRANSITION') await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowAllowed(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowRollbackTargets(instanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowOverview }),
      ]);
    },
  });

  const submit = handleSubmit(async (input) => {
    if (rollback.isPending) return;
    setServerFormError(null);
    try {
      await rollback.mutateAsync(input);
    } catch (cause) {
      const normalized = normalizeApiError(cause, { defaultCode: 'WORKFLOW_INVALID_TRANSITION' });
      const mapped = applyServerErrorsToForm(normalized, { fields: rollbackFields, fieldMap: { target_instance_stage_id: 'targetStageId' }, setError, setFocus });
      if (normalized.kind === 'validation') {
        setServerFormError(mapped.hasUnknownFields || !mapped.applied ? normalized.message : 'Исправьте ошибки в форме.');
        return;
      }
      onNotify({ intent: 'error', title: normalized.kind === 'permission' ? 'Нет прав' : 'Откат не выполнен', message: normalized.message });
    }
  });

  const target = targets.find((item) => item.id === targetStageId) ?? targets[0];
  const modalClose = showDiscard ? () => setShowDiscard(false) : () => {
    if (rollback.isPending) return;
    if (hasDraft) setShowDiscard(true);
    else { clearDraft(); onClose(); }
  };
  if (!open) return null;

  const targetId = 'workflow-rollback-target';
  const targetErrorId = `${targetId}-error`;
  const commentId = 'workflow-rollback-comment';
  const commentErrorId = `${commentId}-error`;
  const commentHintId = `${commentId}-hint`;
  const commentCountId = `${commentId}-count`;
  const commentRegistration = register('comment');
  const showBanner = Boolean(serverFormError || (submitCount > 0 && Object.keys(errors).length));

  return <Modal title="Вернуть на предыдущий этап" onClose={modalClose} initialFocusRef={commentRef}><div className={styles.context}><span>Текущий: {currentStage.orderIndex}. {currentStage.name}</span><ArrowRight size={16} fill="currentColor" aria-hidden="true" /><span>Вернуть: {target ? `${target.orderIndex}. ${target.name}` : 'нет пройденных этапов'}</span></div>{showDiscard ? <div className={styles.discard} role="alertdialog" aria-labelledby="workflow-rollback-discard-title" aria-describedby="workflow-rollback-discard-description"><h3 id="workflow-rollback-discard-title">Есть несохранённые изменения. Закрыть окно?</h3><p id="workflow-rollback-discard-description">Черновик будет удалён, а введённые данные потеряны.</p><div className={styles.actions}><Button variant="ghost" size="s" type="button" autoFocus onClick={() => setShowDiscard(false)}>Продолжить редактирование</Button><Button variant="secondary" size="s" type="button" onClick={() => { clearDraft(); setShowDiscard(false); onClose(); }}>Закрыть без сохранения</Button></div></div> : <form className={styles.form} onSubmit={submit} noValidate>{showBanner ? <FormErrorBanner>{serverFormError ?? undefined}</FormErrorBanner> : null}<FormField label="Этап для возврата" htmlFor={targetId} error={errors.targetStageId?.message} errorId={targetErrorId}><Select id={targetId} disabled={rollback.isPending || targets.length <= 1} aria-invalid={Boolean(errors.targetStageId)} aria-describedby={errors.targetStageId ? targetErrorId : undefined} {...register('targetStageId')}>{targets.map((item) => <option value={item.id} key={item.id}>{item.orderIndex}. {item.name}</option>)}</Select></FormField><FormField label="Комментарий" htmlFor={commentId} required error={errors.comment?.message} errorId={commentErrorId} hint={`Минимум ${COMMENT_MIN_LENGTH} символов. Укажите причину возврата.`} hintId={commentHintId}><TextArea id={commentId} ref={(element) => { commentRegistration.ref(element); commentRef.current = element; }} name={commentRegistration.name} onBlur={commentRegistration.onBlur} onChange={commentRegistration.onChange} maxLength={COMMENT_MAX_LENGTH} minLength={COMMENT_MIN_LENGTH} rows={5} placeholder="Опишите, почему возвращаете этап..." required aria-required="true" aria-invalid={Boolean(errors.comment)} aria-describedby={`${errors.comment ? commentErrorId : commentHintId} ${commentCountId}`} /><span id={commentCountId} className={styles.counter}>{comment.length} / {COMMENT_MAX_LENGTH}</span></FormField><p className={styles.integrationHint}>Возврат переоткроет этап и все этапы между ним и текущим — работу по ним нужно будет выполнить заново.</p>{!apiAvailable ? <p className={styles.integrationHint}>Нет пройденных этапов для возврата. Обновите Workflow.</p> : null}<div className={styles.actions}><Button variant="ghost" size="s" type="button" disabled={rollback.isPending} onClick={modalClose}>Отмена</Button><Button variant="primary" size="s" type="submit" loading={rollback.isPending} disabled={!apiAvailable || rollback.isPending}>Вернуть</Button></div></form>}</Modal>;
}

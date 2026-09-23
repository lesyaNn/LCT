'use client';

import { useEffect, useMemo, useReducer, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import ArrowRight from '@atomaro/icons/24/navigation/ArrowRight';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import { getAvailableWorkflowTransitionTargets, getLocalTodayIso, isWorkflowTransitionDraft, workflowTransitionDraftKey, type WorkflowTransitionTarget } from '@/shared/lib/workflow-transition';
import { isWorkflowApiInstanceId, transitionWorkflowInstance, WorkflowApiError, workflowQueryKey, type UniversityWorkflowStage } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import type { ToastIntent } from '@/shared/ui/rtk/toast';
import styles from './workflow-transition-modal.module.css';

const COMMENT_MIN_LENGTH = 10;
const COMMENT_MAX_LENGTH = 5000;

type FormState = { targetStageId: string; comment: string; dueDate: string; ready: boolean; submitAttempted: boolean; commentTouched: boolean };
type FormAction = { type: 'reset'; targetStageId: string } | { type: 'restore'; state: FormState } | { type: 'ready' } | { type: 'comment'; value: string } | { type: 'target'; value: string } | { type: 'dueDate'; value: string } | { type: 'submitAttempted'; value: boolean } | { type: 'commentTouched'; value: boolean };

function formReducer(state: FormState, action: FormAction): FormState {
  if (action.type === 'reset') return { targetStageId: action.targetStageId, comment: '', dueDate: '', ready: false, submitAttempted: false, commentTouched: false };
  if (action.type === 'restore') return action.state;
  if (action.type === 'ready') return { ...state, ready: true };
  if (action.type === 'comment') return { ...state, comment: action.value };
  if (action.type === 'target') return { ...state, targetStageId: action.value };
  if (action.type === 'dueDate') return { ...state, dueDate: action.value };
  if (action.type === 'submitAttempted') return { ...state, submitAttempted: action.value };
  return { ...state, commentTouched: action.value };
}

function getTransitionError(cause: unknown): { title: string; message: string } {
  if (cause instanceof WorkflowApiError && cause.status === 403) return { title: 'Нет прав', message: 'У вас нет прав на перевод Workflow.' };
  if (cause instanceof WorkflowApiError && cause.status === 400) return { title: 'Переход недоступен', message: 'Проверьте целевой этап и обязательные условия перехода.' };
  return { title: 'Не удалось перевести этап', message: 'Проверьте соединение и попробуйте ещё раз.' };
}

function isValidTargetId(targetId: string, targets: WorkflowTransitionTarget[]): boolean {
  return targets.some((target) => target.id === targetId);
}

function useTransitionForm({ open, instanceId, currentStageId, userId, targets, apiAvailable }: { open: boolean; instanceId: string; currentStageId: string; userId?: string | null; targets: WorkflowTransitionTarget[]; apiAvailable: boolean }) {
  const defaultTargetId = targets[0]?.id ?? '';
  const targetIds = useMemo(() => new Set(targets.map((target) => target.id)), [targets]);
  const targetKey = targets.map((target) => target.id).join('|');
  const storageKey = workflowTransitionDraftKey(instanceId, currentStageId, userId);
  const today = getLocalTodayIso();
  const [state, dispatch] = useReducer(formReducer, { targetStageId: defaultTargetId, comment: '', dueDate: '', ready: false, submitAttempted: false, commentTouched: false });

  useEffect(() => {
    if (!open) {
      return;
    }
    dispatch({ type: 'reset', targetStageId: defaultTargetId });
    let restored: FormState | null = null;
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (isWorkflowTransitionDraft(parsed, targetIds)) {
        restored = {
          targetStageId: parsed.targetStageId,
          comment: parsed.comment,
          dueDate: parsed.dueDate >= today ? parsed.dueDate : '',
          ready: true,
          submitAttempted: false,
          commentTouched: false,
        };
      } else if (raw) {
        window.localStorage.removeItem(storageKey);
      }
    } catch {
      try { window.localStorage.removeItem(storageKey); } catch { /* Storage can be unavailable in privacy mode. */ }
    }
    dispatch(restored ? { type: 'restore', state: restored as FormState } : { type: 'ready' });
  }, [defaultTargetId, open, storageKey, targetIds, targetKey, today]);

  useEffect(() => {
    if (!open || !state.ready) return undefined;
    const hasDraft = state.comment.length > 0 || state.dueDate.length > 0 || state.targetStageId !== defaultTargetId;
    const timer = window.setTimeout(() => {
      try {
        if (!hasDraft) {
          window.localStorage.removeItem(storageKey);
          return;
        }
        const draft = { version: 1 as const, comment: state.comment, dueDate: state.dueDate, targetStageId: state.targetStageId, updatedAt: new Date().toISOString() };
        window.localStorage.setItem(storageKey, JSON.stringify(draft));
      } catch { /* Draft persistence is a convenience and must not block editing. */ }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [defaultTargetId, open, state, storageKey]);

  const trimmedComment = state.comment.trim();
  const commentError = trimmedComment.length === 0 ? 'Комментарий обязателен' : trimmedComment.length < COMMENT_MIN_LENGTH ? `Минимум ${COMMENT_MIN_LENGTH} символов` : state.comment.length > COMMENT_MAX_LENGTH ? `Максимум ${COMMENT_MAX_LENGTH} символов` : null;
  const dueDateError = state.dueDate && state.dueDate < today ? 'Дедлайн не может быть в прошлом' : state.dueDate ? 'Ручной дедлайн пока не поддерживается transition API' : null;
  const targetError = !isValidTargetId(state.targetStageId, targets) ? 'Выберите доступный целевой этап' : null;
  const clearDraft = () => { try { window.localStorage.removeItem(storageKey); } catch { /* Ignore unavailable storage. */ } };
  return {
    state,
    dispatch,
    today,
    hydrated: state.ready,
    submitAttempted: state.submitAttempted,
    commentTouched: state.commentTouched,
    trimmedComment,
    commentError: state.submitAttempted || state.commentTouched ? commentError : null,
    dueDateError,
    targetError,
    isDirty: state.comment.length > 0 || state.dueDate.length > 0 || state.targetStageId !== defaultTargetId,
    canSubmit: Boolean(apiAvailable && state.ready && !commentError && !dueDateError && !targetError && targets.length),
    clearDraft,
  };
}

export interface WorkflowTransitionNotification {
  intent: ToastIntent;
  title: string;
  message: string;
}

export function WorkflowTransitionModal({ open, instanceId, currentStage, stages, userId, onClose, onSuccess, onNotify }: { open: boolean; instanceId: string; currentStage: UniversityWorkflowStage; stages: UniversityWorkflowStage[]; userId?: string | null; onClose: () => void; onSuccess: () => void; onNotify: (notification: WorkflowTransitionNotification) => void }) {
  const queryClient = useQueryClient();
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const [showDiscard, setShowDiscard] = useState(false);
  const targets = useMemo(() => getAvailableWorkflowTransitionTargets(stages, currentStage), [currentStage, stages]);
  const apiAvailable = isWorkflowApiInstanceId(instanceId) && targets.every((target) => isWorkflowApiInstanceId(target.id));
  const form = useTransitionForm({ open, instanceId, currentStageId: currentStage.id, userId, targets, apiAvailable });
  const transition = useMutation({
    mutationFn: () => transitionWorkflowInstance(instanceId, form.state.targetStageId, form.trimmedComment),
    onSuccess: async () => {
      form.clearDraft();
      await queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) });
      onNotify({ intent: 'success', title: 'Этап переведён', message: 'Workflow обновлён.' });
      onSuccess();
    },
    onError: async (cause: unknown) => {
      const error = getTransitionError(cause);
      if (cause instanceof WorkflowApiError && cause.status === 400) await queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) });
      onNotify({ intent: 'error', title: error.title, message: error.message });
    },
  });

  const target = targets.find((item) => item.id === form.state.targetStageId) ?? targets[0];
  const modalClose = showDiscard ? () => setShowDiscard(false) : () => {
    if (transition.isPending) return;
    if (form.isDirty) setShowDiscard(true);
    else { form.clearDraft(); onClose(); }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    form.dispatch({ type: 'submitAttempted', value: true });
    if (!form.canSubmit) return;
    transition.mutate();
  };

  if (!open) return null;
  return <Modal title="Перевести на следующий этап" onClose={modalClose} initialFocusRef={commentRef}><div className={styles.context}><span>Текущий: {currentStage.orderIndex}. {currentStage.name}</span><ArrowRight size={16} fill="currentColor" aria-hidden="true" /><span>Следующий: {target ? `${target.orderIndex}. ${target.name}` : 'нет доступного этапа'}</span></div>{showDiscard ? <div className={styles.discard} role="alertdialog" aria-labelledby="workflow-transition-discard-title" aria-describedby="workflow-transition-discard-description"><h3 id="workflow-transition-discard-title">Есть несохранённые изменения. Закрыть окно?</h3><p id="workflow-transition-discard-description">Черновик будет удалён, а введённые данные потеряны.</p><div className={styles.actions}><Button variant="ghost" size="s" type="button" autoFocus onClick={() => setShowDiscard(false)}>Продолжить редактирование</Button><Button variant="secondary" size="s" type="button" onClick={() => { form.clearDraft(); setShowDiscard(false); onClose(); }}>Закрыть без сохранения</Button></div></div> : <form className={styles.form} onSubmit={submit} noValidate>{targets.length > 1 ? <label className={styles.field}><span>Целевой этап</span><select value={form.state.targetStageId} onChange={(event) => form.dispatch({ type: 'target', value: event.target.value })} aria-invalid={Boolean(form.targetError)}>{targets.map((item) => <option value={item.id} key={item.id}>{item.orderIndex}. {item.name}</option>)}</select>{form.targetError ? <small className={styles.error} role="alert">{form.targetError}</small> : null}</label> : <div className={styles.nextStage}><span>Следующий этап:</span><strong>{target ? `${target.orderIndex}. ${target.name}` : 'Нет доступного этапа'}</strong></div>}<label className={styles.field}><span>Комментарий <sup aria-hidden="true">*</sup></span><textarea ref={commentRef} value={form.state.comment} maxLength={COMMENT_MAX_LENGTH} minLength={COMMENT_MIN_LENGTH} rows={5} placeholder="Опишите, что сделано, почему переводите..." required aria-required="true" aria-invalid={Boolean(form.commentError)} aria-describedby="workflow-transition-comment-hint workflow-transition-comment-error" onChange={(event) => form.dispatch({ type: 'comment', value: event.target.value })} onBlur={() => { if (form.state.comment.length > 0) form.dispatch({ type: 'commentTouched', value: true }); }} />{form.commentError ? <small id="workflow-transition-comment-error" className={styles.error} role="alert">{form.commentError}</small> : <small id="workflow-transition-comment-hint" className={styles.hint}>Минимум {COMMENT_MIN_LENGTH} символов</small>}<span className={styles.counter}>{form.state.comment.length} / {COMMENT_MAX_LENGTH}</span></label><label className={styles.field}><span>Дедлайн для следующего этапа <em>(необязательно)</em></span><span className={styles.dateControl}><TimeStroke size={16} fill="currentColor" aria-hidden="true" /><input type="date" min={form.today} value={form.state.dueDate} onChange={(event) => form.dispatch({ type: 'dueDate', value: event.target.value })} aria-invalid={Boolean(form.dueDateError)} /></span>{form.dueDateError ? <small className={styles.error} role="alert">{form.dueDateError}</small> : <small className={styles.hint}>Если не указать, будет рассчитан автоматически</small>}</label>{!apiAvailable ? <p className={styles.integrationHint}>Переход станет доступен после подключения API к этому Workflow.</p> : null}<div className={styles.actions}><Button variant="ghost" size="s" type="button" disabled={transition.isPending} onClick={modalClose}>Отмена</Button><Button variant="primary" size="s" type="submit" disabled={!form.canSubmit || transition.isPending}>{transition.isPending ? 'Перевод…' : 'Перевести'}</Button></div></form>}</Modal>;
}

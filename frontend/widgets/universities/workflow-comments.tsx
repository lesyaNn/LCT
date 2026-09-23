'use client';

import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Edit from '@atomaro/icons/24/editor/Edit';
import Comments from '@atomaro/icons/24/communication/Comments';
import { useAuth } from '@/shared/auth/AuthProvider';
import { canEditWorkflowComment } from '@/shared/lib/workflow-comment-permissions';
import { createWorkflowComment, editWorkflowComment, isWorkflowApiInstanceId, listWorkflowComments, workflowCommentsQueryKey, workflowQueryKey, type UniversityWorkflowComment, type WorkflowCommentApiRecord } from '@/shared/lib/universities-repository';
import { formatRelativeDateRu } from '@/shared/lib/formatters';
import { applyServerErrorsToForm, normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { FormField } from '@/shared/ui/rtk/form-field';
import { TextArea } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './workflow-comments.module.css';
import type { WorkflowTransitionNotification } from './workflow-transition-modal';

const COMMENT_MAX_LENGTH = 5000;
const commentSchema = z.object({ content: z.string().max(COMMENT_MAX_LENGTH, `Максимум ${COMMENT_MAX_LENGTH} символов.`).refine((value) => value.trim().length > 0, 'Введите комментарий.') });
type CommentValues = z.infer<typeof commentSchema>;
const commentFields = ['content'] as const;

function getInitials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('ru-RU') || '—';
}

function useWorkflowMutationInvalidation(instanceId: string) {
  const queryClient = useQueryClient();
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
    queryClient.invalidateQueries({ queryKey: workflowCommentsQueryKey(instanceId) }),
  ]);
}

function rollbackComments(current: WorkflowCommentApiRecord[] | undefined, previous: WorkflowCommentApiRecord[] | undefined, tempId: string): WorkflowCommentApiRecord[] | undefined {
  if (!previous) return current?.filter((comment) => comment.id !== tempId);
  const previousIds = new Set(previous.map((comment) => comment.id));
  const concurrent = current?.filter((comment) => comment.id !== tempId && (!previousIds.has(comment.id) || comment.is_optimistic)) ?? [];
  return [...previous, ...concurrent];
}

function CommentEditor({ initialValue, disabled, submitLabel, onSubmit, onCancel, onGlobalError }: { initialValue: string; disabled: boolean; submitLabel: string; onSubmit: (content: string) => Promise<void>; onCancel?: () => void; onGlobalError?: (error: NormalizedApiError) => void }) {
  const composing = useRef(false);
  const inputId = `workflow-comment-editor-${useId()}`;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, isSubmitting } } = useForm<CommentValues>({ resolver: zodResolver(commentSchema), mode: 'onBlur', reValidateMode: 'onChange', defaultValues: { content: initialValue } });
  const value = useWatch({ control, name: 'content', defaultValue: initialValue });
  const submit = handleSubmit(async ({ content }) => {
    try {
      await onSubmit(content.trim());
      if (submitLabel === 'Отправить') reset({ content: '' });
    } catch (cause) {
      const normalized = normalizeApiError(cause);
      const mapped = applyServerErrorsToForm(normalized, { fields: commentFields, fieldMap: { comment: 'content' }, setError, setFocus });
      if (normalized.kind === 'validation') {
        if (!mapped.applied) { setError('content', { type: 'server', message: normalized.message }); setFocus('content'); }
      } else onGlobalError?.(normalized);
    }
  });
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape' && onCancel) { event.preventDefault(); onCancel(); return; }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current) { event.preventDefault(); void submit(); }
  };
  return <form className={styles.editor} onSubmit={submit} noValidate><FormField label={submitLabel === 'Отправить' ? 'Добавить комментарий' : 'Редактировать комментарий'} htmlFor={inputId} error={errors.content?.message} errorId={errorId}><TextArea id={inputId} maxLength={COMMENT_MAX_LENGTH} minLength={1} rows={3} placeholder="Напишите комментарий..." disabled={disabled || isSubmitting} aria-invalid={Boolean(errors.content)} aria-describedby={`${errors.content ? errorId : hintId}`} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={handleKeyDown} {...register('content')} /></FormField><div className={styles.editorFooter}><span id={hintId} className={styles.counter}>{value.length} / {COMMENT_MAX_LENGTH}</span><div className={styles.editorActions}>{onCancel ? <Button variant="ghost" size="s" type="button" disabled={isSubmitting} onClick={onCancel}>Отмена</Button> : null}<Button variant={submitLabel === 'Отправить' ? 'primary' : 'secondary'} size="s" type="submit" disabled={disabled || isSubmitting} title={disabled ? 'Действие подключится после появления API' : undefined}>{isSubmitting ? 'Сохранение…' : submitLabel}</Button></div></div>{disabled ? <p className={styles.integrationHint}>Действие станет доступно после подключения API.</p> : null}</form>;
}

function CommentItem({ comment, instanceId, onNotify }: { comment: UniversityWorkflowComment; instanceId: string; onNotify?: (notification: WorkflowTransitionNotification) => void }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const invalidate = useWorkflowMutationInvalidation(instanceId);
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const canEdit = canEditWorkflowComment(comment, user);
  const updated = comment.updatedAt && comment.updatedAt !== comment.occurredAt ? comment.updatedAt : null;
  const save = useMutation({ mutationFn: (content: string) => editWorkflowComment(comment.id, content), onSuccess: async () => { setEditing(false); await invalidate(); } });

  if (editing) return <li className={styles.commentItem}><CommentEditor initialValue={comment.text} disabled={!apiAvailable || save.isPending} submitLabel="Сохранить" onCancel={() => setEditing(false)} onSubmit={async (content) => { await save.mutateAsync(content); }} onGlobalError={(error) => onNotify?.({ intent: 'error', title: 'Комментарий не сохранён', message: error.message })} /></li>;
  return <li className={styles.commentItem}><div className={styles.commentHeader}><Avatar initials={getInitials(comment.author)} size="s" /><div className={styles.authorBlock}><div className={styles.authorLine}><strong>{comment.author}</strong>{comment.isSystem ? <StatusBadge intent="neutral" size="sm">Системное</StatusBadge> : null}</div><div className={styles.commentMeta}><span>{comment.authorRole ?? 'Участник Workflow'}</span>{comment.isOptimistic ? <span className={styles.pending} role="status">Отправляется…</span> : <><time dateTime={comment.occurredAt}>{formatRelativeDateRu(comment.occurredAt)}</time>{updated ? <span>Отредактировано {formatRelativeDateRu(updated)}</span> : null}</>}</div></div>{canEdit ? <Button variant="ghost" size="s" type="button" disabled={!apiAvailable} title={!apiAvailable ? 'Редактирование подключится после появления API' : 'Редактировать комментарий'} aria-label={`Редактировать комментарий ${comment.author}`} onClick={() => setEditing(true)}><Edit size={14} fill="currentColor" />Редактировать</Button> : null}</div><p className={styles.commentText}>{comment.text}</p></li>;
}

type CommentMutationContext = { previousComments?: WorkflowCommentApiRecord[]; tempId: string };

export function WorkflowComments({ instanceId, stageId, comments, onNotify }: { instanceId: string; stageId: string; comments: UniversityWorkflowComment[]; onNotify?: (notification: WorkflowTransitionNotification) => void }) {
  const [showAll, setShowAll] = useState(false);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const create = useMutation<WorkflowCommentApiRecord, unknown, string, CommentMutationContext>({
    mutationFn: (content: string) => createWorkflowComment(instanceId, content, stageId),
    onMutate: async (content) => {
      const queryKey = workflowCommentsQueryKey(instanceId);
      await queryClient.cancelQueries({ queryKey });
      const previousComments = queryClient.getQueryData<WorkflowCommentApiRecord[]>(queryKey);
      const randomPart = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const tempId = `temp:${randomPart}`;
      const now = new Date().toISOString();
      const optimisticComment: WorkflowCommentApiRecord = { id: tempId, instance_id: instanceId, stage_id: stageId || null, author_keycloak_sub: user?.id ?? 'current-user', content, is_internal: true, created_at: now, updated_at: now, is_optimistic: true };
      queryClient.setQueryData<WorkflowCommentApiRecord[]>(queryKey, (current) => [...(current ?? []), optimisticComment]);
      return { previousComments, tempId };
    },
    onSuccess: async (serverComment, _content, context) => {
      const queryKey = workflowCommentsQueryKey(instanceId);
      queryClient.setQueryData<WorkflowCommentApiRecord[]>(queryKey, (current) => (current ?? []).map((comment) => comment.id === context.tempId ? serverComment : comment));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey, refetchType: 'none' }),
      ]);
    },
    onError: async (cause: unknown, _content, context) => {
      queryClient.setQueryData(workflowCommentsQueryKey(instanceId), (current: WorkflowCommentApiRecord[] | undefined) => rollbackComments(current, context?.previousComments, context?.tempId ?? ''));
    },
  });
  const apiCommentsQuery = useQuery({ queryKey: workflowCommentsQueryKey(instanceId), queryFn: () => listWorkflowComments(instanceId), enabled: apiAvailable, staleTime: 30_000 });
  const apiComments = useMemo<UniversityWorkflowComment[] | null>(() => apiCommentsQuery.data?.filter((comment) => comment.stage_id === null || comment.stage_id === stageId).map((comment) => ({ id: comment.id, author: comment.is_optimistic && user ? user.name : comment.author_keycloak_sub, authorId: comment.author_keycloak_sub, authorRole: comment.is_optimistic && user ? user.roleLabel : 'Участник Workflow', isSystem: false, occurredAt: comment.created_at, updatedAt: comment.updated_at, text: comment.content, isOptimistic: comment.is_optimistic })) ?? null, [apiCommentsQuery.data, stageId, user]);
  const renderedComments = apiComments ?? comments;
  // The existing Workflow showed newest comments first; keep that order for both sources.
  const orderedComments = useMemo(() => renderedComments.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)), [renderedComments]);
  const visibleComments = showAll ? orderedComments : orderedComments.slice(0, 3);
  const addComment = async (content: string) => { await create.mutateAsync(content); };
  const queryError = apiCommentsQuery.isError ? normalizeApiError(apiCommentsQuery.error).message : '';
  return <section className={styles.section} aria-labelledby={`${stageId}-comments-title`}><div className={styles.heading}><h3 id={`${stageId}-comments-title`}><Comments size={18} fill="currentColor" />Комментарии <span className={styles.count}>{renderedComments.length}</span></h3>{renderedComments.length > 3 ? <Button variant="ghost" size="s" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : 'Показать все'}</Button> : null}</div>{apiAvailable && apiCommentsQuery.isPending ? <div className={styles.skeleton} aria-label="Загрузка комментариев"><span /><span /><span /></div> : apiAvailable && apiCommentsQuery.isError ? <div className={styles.queryError} role="alert"><p>{queryError}</p><Button variant="ghost" size="s" type="button" onClick={() => void apiCommentsQuery.refetch()}>Повторить</Button></div> : orderedComments.length ? <ul className={styles.commentList}>{visibleComments.map((comment) => <CommentItem key={comment.id} comment={comment} instanceId={instanceId} onNotify={onNotify} />)}</ul> : <p className={styles.empty}>Комментариев пока нет</p>}<CommentEditor initialValue="" disabled={!apiAvailable || !user || create.isPending} submitLabel="Отправить" onSubmit={addComment} onGlobalError={(error) => onNotify?.({ intent: 'error', title: 'Комментарий не сохранён', message: error.message })} /></section>;
}

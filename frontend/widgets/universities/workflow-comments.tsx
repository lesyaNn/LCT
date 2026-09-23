'use client';

import { useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Edit from '@atomaro/icons/24/editor/Edit';
import Comments from '@atomaro/icons/24/communication/Comments';
import { useAuth } from '@/shared/auth/AuthProvider';
import { canEditWorkflowComment } from '@/shared/lib/workflow-comment-permissions';
import { createWorkflowComment, editWorkflowComment, isWorkflowApiInstanceId, listWorkflowComments, WorkflowApiError, workflowCommentsQueryKey, workflowQueryKey, type UniversityWorkflowComment, type WorkflowCommentApiRecord } from '@/shared/lib/universities-repository';
import { formatRelativeDateRu } from '@/shared/lib/formatters';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './workflow-comments.module.css';
import type { WorkflowTransitionNotification } from './workflow-transition-modal';

const COMMENT_MAX_LENGTH = 5000;

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

function getCommentError(cause: unknown): string {
  if (cause instanceof WorkflowApiError && cause.status === 403) return 'Нет прав на изменение комментариев.';
  if (cause instanceof WorkflowApiError && cause.status === 400) return 'Комментарий не принят. Проверьте текст и попробуйте ещё раз.';
  return 'Не удалось сохранить комментарий. Попробуйте ещё раз.';
}

function rollbackComments(current: WorkflowCommentApiRecord[] | undefined, previous: WorkflowCommentApiRecord[] | undefined, tempId: string): WorkflowCommentApiRecord[] | undefined {
  if (!previous) return current?.filter((comment) => comment.id !== tempId);
  const previousIds = new Set(previous.map((comment) => comment.id));
  const concurrent = current?.filter((comment) => comment.id !== tempId && (!previousIds.has(comment.id) || comment.is_optimistic)) ?? [];
  return [...previous, ...concurrent];
}

function CommentEditor({ initialValue, disabled, submitLabel, onSubmit, onCancel }: { initialValue: string; disabled: boolean; submitLabel: string; onSubmit: (content: string) => Promise<void>; onCancel?: () => void }) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const composing = useRef(false);
  const inputId = `workflow-comment-editor-${useId()}`;

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = value.trim();
    if (!content) { setError('Введите комментарий.'); return; }
    if (value.length > COMMENT_MAX_LENGTH) { setError(`Комментарий не может быть длиннее ${COMMENT_MAX_LENGTH} символов.`); return; }
    setError(null);
    setIsPending(true);
    try { await onSubmit(content); if (submitLabel === 'Отправить') setValue(''); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось сохранить комментарий.'); } finally { setIsPending(false); }
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape' && onCancel) { event.preventDefault(); onCancel(); return; }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current) { event.preventDefault(); void submit(); }
  };
  return <form className={styles.editor} onSubmit={submit}><label htmlFor={inputId}>{submitLabel === 'Отправить' ? 'Добавить комментарий' : 'Редактировать комментарий'}</label><textarea id={inputId} value={value} maxLength={COMMENT_MAX_LENGTH} minLength={1} rows={3} placeholder="Напишите комментарий..." disabled={disabled || isPending} onChange={(event) => setValue(event.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={handleKeyDown} aria-describedby={`${inputId}-hint`} /><div className={styles.editorFooter}><span id={`${inputId}-hint`} className={styles.counter}>{value.length} / {COMMENT_MAX_LENGTH}</span><div className={styles.editorActions}>{onCancel ? <Button variant="ghost" size="s" type="button" disabled={isPending} onClick={onCancel}>Отмена</Button> : null}<Button variant={submitLabel === 'Отправить' ? 'primary' : 'secondary'} size="s" type="submit" disabled={disabled || isPending} title={disabled ? 'Действие подключится после появления API' : undefined}>{isPending ? 'Сохранение…' : submitLabel}</Button></div></div>{disabled ? <p className={styles.integrationHint}>Действие станет доступно после подключения API.</p> : null}{error ? <p className={styles.validationError} role="alert">{error}</p> : null}</form>;
}

function CommentItem({ comment, instanceId }: { comment: UniversityWorkflowComment; instanceId: string }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const invalidate = useWorkflowMutationInvalidation(instanceId);
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const canEdit = canEditWorkflowComment(comment, user);
  const updated = comment.updatedAt && comment.updatedAt !== comment.occurredAt ? comment.updatedAt : null;
  const save = useMutation({ mutationFn: (content: string) => editWorkflowComment(comment.id, content), onSuccess: async () => { setEditing(false); await invalidate(); } });

  if (editing) return <li className={styles.commentItem}><CommentEditor initialValue={comment.text} disabled={!apiAvailable || save.isPending} submitLabel="Сохранить" onCancel={() => setEditing(false)} onSubmit={async (content) => { await save.mutateAsync(content); }} /></li>;
  return <li className={styles.commentItem}><div className={styles.commentHeader}><Avatar initials={getInitials(comment.author)} size="s" /><div className={styles.authorBlock}><div className={styles.authorLine}><strong>{comment.author}</strong>{comment.isSystem ? <StatusBadge intent="neutral" size="sm">Системное</StatusBadge> : null}</div><div className={styles.commentMeta}><span>{comment.authorRole ?? 'Участник Workflow'}</span>{comment.isOptimistic ? <span className={styles.pending} role="status">Отправляется…</span> : <><time dateTime={comment.occurredAt}>{formatRelativeDateRu(comment.occurredAt)}</time>{updated ? <span>Отредактировано {formatRelativeDateRu(updated)}</span> : null}</>}</div></div>{canEdit ? <Button variant="ghost" size="s" type="button" disabled={!apiAvailable} title={!apiAvailable ? 'Редактирование подключится после появления API' : 'Редактировать комментарий'} aria-label={`Редактировать комментарий ${comment.author}`} onClick={() => setEditing(true)}><Edit size={14} fill="currentColor" />Редактировать</Button> : null}</div><p className={styles.commentText}>{comment.text}</p></li>;
}

type CommentMutationContext = { previousComments?: WorkflowCommentApiRecord[]; tempId: string };

export function WorkflowComments({ instanceId, stageId, comments, onNotify }: { instanceId: string; stageId: string; comments: UniversityWorkflowComment[]; onNotify?: (notification: WorkflowTransitionNotification) => void }) {
  const [showAll, setShowAll] = useState(false);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const [formError, setFormError] = useState<string | null>(null);
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
      onNotify?.({ intent: 'error', title: 'Не удалось отправить комментарий', message: getCommentError(cause) });
    },
  });
  const apiCommentsQuery = useQuery({ queryKey: workflowCommentsQueryKey(instanceId), queryFn: () => listWorkflowComments(instanceId), enabled: apiAvailable, staleTime: 30_000 });
  const apiComments = useMemo<UniversityWorkflowComment[] | null>(() => apiCommentsQuery.data?.filter((comment) => comment.stage_id === null || comment.stage_id === stageId).map((comment) => ({ id: comment.id, author: comment.is_optimistic && user ? user.name : comment.author_keycloak_sub, authorId: comment.author_keycloak_sub, authorRole: comment.is_optimistic && user ? user.roleLabel : 'Участник Workflow', isSystem: false, occurredAt: comment.created_at, updatedAt: comment.updated_at, text: comment.content, isOptimistic: comment.is_optimistic })) ?? null, [apiCommentsQuery.data, stageId, user]);
  const renderedComments = apiComments ?? comments;
  // The existing Workflow showed newest comments first; keep that order for both sources.
  const orderedComments = useMemo(() => renderedComments.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)), [renderedComments]);
  const visibleComments = showAll ? orderedComments : orderedComments.slice(0, 3);
  const addComment = async (content: string) => { setFormError(null); try { await create.mutateAsync(content); } catch (cause) { const message = getCommentError(cause); setFormError(message); throw new Error(message); } };
  const queryError = apiCommentsQuery.error instanceof Error ? apiCommentsQuery.error.message : 'Не удалось загрузить комментарии.';
  return <section className={styles.section} aria-labelledby={`${stageId}-comments-title`}><div className={styles.heading}><h3 id={`${stageId}-comments-title`}><Comments size={18} fill="currentColor" />Комментарии <span className={styles.count}>{renderedComments.length}</span></h3>{renderedComments.length > 3 ? <Button variant="ghost" size="s" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : 'Показать все'}</Button> : null}</div>{apiAvailable && apiCommentsQuery.isPending ? <div className={styles.skeleton} aria-label="Загрузка комментариев"><span /><span /><span /></div> : apiAvailable && apiCommentsQuery.isError ? <div className={styles.queryError} role="alert"><p>{queryError}</p><Button variant="ghost" size="s" type="button" onClick={() => void apiCommentsQuery.refetch()}>Повторить</Button></div> : orderedComments.length ? <ul className={styles.commentList}>{visibleComments.map((comment) => <CommentItem key={comment.id} comment={comment} instanceId={instanceId} />)}</ul> : <p className={styles.empty}>Комментариев пока нет</p>}<CommentEditor initialValue="" disabled={!apiAvailable || !user || create.isPending} submitLabel="Отправить" onSubmit={addComment} />{formError ? <p className={styles.validationError} role="alert">{formError}</p> : null}</section>;
}

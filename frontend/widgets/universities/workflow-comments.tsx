'use client';

import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Edit from '@atomaro/icons/24/editor/Edit';
import Trash from '@atomaro/icons/24/action/Trash';
import Comments from '@atomaro/icons/24/communication/Comments';
import Attachment from '@atomaro/icons/24/action/Attachment';
import { useAuth } from '@/shared/auth/AuthProvider';
import { queryKeys } from '@/shared/lib/query-keys';
import { hasPermission } from '@/shared/lib/access-control';
import { canDeleteWorkflowComment, canEditWorkflowComment } from '@/shared/lib/workflow-comment-permissions';
import { createWorkflowComment, deleteWorkflowComment, editWorkflowComment, isRealWorkflowMode, isWorkflowApiInstanceId, listWorkflowComments, listWorkflowCommentsPage, workflowCommentsQueryKey, workflowQueryKey, type UniversityWorkflowComment, type WorkflowCommentApiRecord } from '@/shared/lib/universities-repository';
import { formatRelativeDateRu, formatFileSize } from '@/shared/lib/formatters';
import { isUuidLike } from '@/shared/lib/audit-human';
import { validateWorkflowUploadFile, workflowAttachmentFromApi } from '@/shared/lib/workflow-attachments';
import { applyServerErrorsToForm, normalizeApiError, type NormalizedApiError } from '@/shared/lib/api-errors';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { EmptyState } from '@/shared/ui/empty-state';
import { ErrorState } from '@/shared/ui/error-state';
import { FormField } from '@/shared/ui/rtk/form-field';
import { TextArea } from '@/shared/ui/rtk/form-controls';
import { ListSkeleton } from '@/shared/ui/skeleton';
import { Modal } from '@/shared/ui/rtk/modal';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './workflow-comments.module.css';
import type { WorkflowTransitionNotification } from './workflow-transition-modal';
import { AttachmentDropZone, AttachmentRow } from './workflow-attachments';

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
    queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) }),
  ]);
}

function rollbackComments(current: WorkflowCommentApiRecord[] | undefined, previous: WorkflowCommentApiRecord[] | undefined, tempId: string): WorkflowCommentApiRecord[] | undefined {
  if (!previous) return current?.filter((comment) => comment.id !== tempId);
  const previousIds = new Set(previous.map((comment) => comment.id));
  const concurrent = current?.filter((comment) => comment.id !== tempId && (!previousIds.has(comment.id) || comment.is_optimistic)) ?? [];
  return [...previous, ...concurrent];
}

function CommentEditor({ initialValue, disabled, submitLabel, onSubmit, onCancel, onGlobalError, allowFiles = false }: { initialValue: string; disabled: boolean; submitLabel: string; onSubmit: (content: string, files: File[]) => Promise<void>; onCancel?: () => void; onGlobalError?: (error: NormalizedApiError) => void; allowFiles?: boolean }) {
  const composing = useRef(false);
  const [submissionPending, setSubmissionPending] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState('');
  const inputId = `workflow-comment-editor-${useId()}`;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const { register, control, handleSubmit, reset, setError, setFocus, formState: { errors, isSubmitting } } = useForm<CommentValues>({ resolver: zodResolver(commentSchema), mode: 'onBlur', reValidateMode: 'onChange', defaultValues: { content: initialValue } });
  const value = useWatch({ control, name: 'content', defaultValue: initialValue });
  const submit = handleSubmit(async ({ content }) => {
    if (submissionPending) return;
    setSubmissionPending(true);
    try {
      await onSubmit(content.trim(), files);
      if (submitLabel === 'Отправить') { reset({ content: '' }); setFiles([]); setFileError(''); }
    } catch (cause) {
      const normalized = normalizeApiError(cause);
      const mapped = applyServerErrorsToForm(normalized, { fields: commentFields, fieldMap: { comment: 'content' }, setError, setFocus });
      if (normalized.kind === 'validation') {
        if (!mapped.applied) { setError('content', { type: 'server', message: normalized.message }); setFocus('content'); }
      } else onGlobalError?.(normalized);
    } finally { setSubmissionPending(false); }
  });
  const addFiles = (selected: File[]) => {
    const next = [...files];
    for (const file of selected) {
      const validation = validateWorkflowUploadFile(file);
      if (!validation.valid) { setFileError(validation.message); continue; }
      if (next.length >= 10) { setFileError('Можно прикрепить не более 10 файлов.'); break; }
      next.push(file);
      setFileError('');
    }
    setFiles(next);
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape' && onCancel) { event.preventDefault(); onCancel(); return; }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current) { event.preventDefault(); void submit(); }
  };
  return <form className={styles.editor} onSubmit={submit} noValidate><FormField label={submitLabel === 'Отправить' ? 'Добавить комментарий' : 'Редактировать комментарий'} htmlFor={inputId} error={errors.content?.message} errorId={errorId}><TextArea id={inputId} maxLength={COMMENT_MAX_LENGTH} minLength={1} rows={3} placeholder="Напишите комментарий..." disabled={disabled || isSubmitting || submissionPending} aria-invalid={Boolean(errors.content)} aria-describedby={`${errors.content ? errorId : hintId}`} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={handleKeyDown} {...register('content')} /></FormField>{allowFiles ? <><AttachmentDropZone compact onFiles={addFiles} disabled={disabled || isSubmitting || submissionPending} />{files.length ? <ul className={styles.selectedFiles}>{files.map((file, index) => <li key={`${file.name}-${index}`}><Attachment size={16} fill="currentColor" /><span>{file.name} · {formatFileSize(file.size)}</span><Button variant="ghost" size="s" type="button" disabled={isSubmitting || submissionPending} aria-label={`Убрать ${file.name}`} onClick={() => setFiles((current) => current.filter((_, position) => position !== index))}><Trash size={14} fill="currentColor" />Убрать</Button></li>)}</ul> : null}{fileError ? <p className={styles.validationError} role="alert">{fileError}</p> : null}</> : null}<div className={styles.editorFooter}><span id={hintId} className={styles.counter}>{value.length} / {COMMENT_MAX_LENGTH}</span><div className={styles.editorActions}>{onCancel ? <Button variant="ghost" size="s" type="button" disabled={isSubmitting || submissionPending} onClick={onCancel}>Отмена</Button> : null}<Button variant={submitLabel === 'Отправить' ? 'primary' : 'secondary'} size="s" type="submit" loading={isSubmitting || submissionPending} disabled={disabled || isSubmitting || submissionPending} title={disabled ? 'Действие пока недоступно' : undefined}>{(isSubmitting || submissionPending) && files.length ? 'Загрузка файлов…' : submitLabel}</Button></div></div>{disabled ? <p className={styles.integrationHint}>Действие пока недоступно.</p> : null}</form>;
}

function CommentItem({ comment, instanceId, onNotify }: { comment: UniversityWorkflowComment; instanceId: string; onNotify?: (notification: WorkflowTransitionNotification) => void }) {
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const invalidate = useWorkflowMutationInvalidation(instanceId);
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const canEdit = canEditWorkflowComment(comment, user);
  const canDelete = isRealWorkflowMode() && canDeleteWorkflowComment(comment, user);
  const updated = comment.updatedAt && comment.updatedAt !== comment.occurredAt ? comment.updatedAt : null;
  const save = useMutation({ mutationFn: (content: string) => editWorkflowComment(comment.id, content), onSuccess: async () => { setEditing(false); await invalidate(); } });
  const remove = useMutation({ mutationFn: () => deleteWorkflowComment(comment.id), onSuccess: async () => { setConfirmDelete(false); await invalidate(); }, onError: (cause) => onNotify?.({ intent: 'error', title: 'Комментарий не удалён', message: normalizeApiError(cause).message }) });

  if (editing) return <li className={styles.commentItem}><CommentEditor initialValue={comment.text} disabled={!apiAvailable || save.isPending} submitLabel="Сохранить" onCancel={() => setEditing(false)} onSubmit={async (content) => { await save.mutateAsync(content); }} onGlobalError={(error) => onNotify?.({ intent: 'error', title: 'Комментарий не сохранён', message: error.message })} /></li>;
  return <li className={styles.commentItem}><div className={styles.commentHeader}><Avatar initials={getInitials(comment.author)} size="s" /><div className={styles.authorBlock}><div className={styles.authorLine}><strong>{comment.author}</strong>{comment.isSystem ? <StatusBadge intent="neutral" size="sm">Системное</StatusBadge> : null}</div><div className={styles.commentMeta}><span>{comment.authorRole ?? 'Участник Workflow'}</span>{comment.isOptimistic ? <span className={styles.pending} role="status">Отправляется…</span> : <><time dateTime={comment.occurredAt}>{formatRelativeDateRu(comment.occurredAt)}</time>{updated ? <span>Отредактировано {formatRelativeDateRu(updated)}</span> : null}</>}</div></div>{canEdit ? <Tooltip content="Редактировать"><IconButton icon={<Edit size={18} fill="currentColor" />} label={`Редактировать комментарий ${comment.author}`} size={18} disabled={!apiAvailable} onClick={() => setEditing(true)} /></Tooltip> : null}{canDelete ? <Tooltip content="Удалить"><IconButton icon={<Trash size={18} fill="currentColor" />} label={`Удалить комментарий ${comment.author}`} size={18} intent="danger" onClick={() => setConfirmDelete(true)} /></Tooltip> : null}</div><p className={styles.commentText}>{comment.text}</p>{comment.attachments?.length ? <ul className={styles.commentFiles}>{comment.attachments.map((attachment) => <AttachmentRow key={attachment.id} attachment={attachment} instanceId={instanceId} canDelete={false} compact onOpen={() => undefined} onDelete={() => undefined} />)}</ul> : null}{confirmDelete ? <Modal title="Удалить комментарий?" onClose={() => { if (!remove.isPending) setConfirmDelete(false); }}><p>Комментарий будет удалён. Это действие нельзя отменить.</p><div className={styles.editorActions}><Button variant="ghost" size="s" type="button" disabled={remove.isPending} onClick={() => setConfirmDelete(false)}>Отмена</Button><Button variant="danger" size="s" type="button" loading={remove.isPending} disabled={remove.isPending} onClick={() => remove.mutate()}>Удалить</Button></div></Modal> : null}</li>;
}

type CommentMutationContext = { previousComments?: WorkflowCommentApiRecord[]; tempId: string };

export function WorkflowComments({ instanceId, stageId, comments, readOnly = false, onNotify }: { instanceId: string; stageId: string; comments: UniversityWorkflowComment[]; readOnly?: boolean; onNotify?: (notification: WorkflowTransitionNotification) => void }) {
  const [showAll, setShowAll] = useState(false);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const apiAvailable = isWorkflowApiInstanceId(instanceId);
  const realWorkflow = isRealWorkflowMode();
  const commentsQueryKey = realWorkflow ? workflowCommentsQueryKey(instanceId) : [...workflowCommentsQueryKey(instanceId), 'mock'];
  const create = useMutation<WorkflowCommentApiRecord, unknown, { content: string; files: File[] }, CommentMutationContext>({
    mutationFn: ({ content, files }) => createWorkflowComment(instanceId, content, stageId, files),
    onMutate: async ({ content }) => {
      if (realWorkflow) return { tempId: '' };
      const queryKey = commentsQueryKey;
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
      const queryKey = commentsQueryKey;
      if (realWorkflow) {
        await Promise.all([queryClient.invalidateQueries({ queryKey }), queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(instanceId) })]);
        return;
      }
      queryClient.setQueryData<WorkflowCommentApiRecord[]>(queryKey, (current) => (current ?? []).map((comment) => comment.id === context.tempId ? serverComment : comment));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
        queryClient.invalidateQueries({ queryKey, refetchType: 'none' }),
      ]);
    },
    onError: async (cause: unknown, _content, context) => {
      if (realWorkflow) return;
      queryClient.setQueryData(commentsQueryKey, (current: WorkflowCommentApiRecord[] | undefined) => rollbackComments(current, context?.previousComments, context?.tempId ?? ''));
    },
  });
  const apiCommentsQuery = useQuery({ queryKey: commentsQueryKey, queryFn: () => listWorkflowComments(instanceId), enabled: apiAvailable && !realWorkflow, staleTime: 30_000 });
  const realCommentsQuery = useInfiniteQuery({ queryKey: workflowCommentsQueryKey(instanceId), queryFn: ({ pageParam }) => listWorkflowCommentsPage(instanceId, pageParam), initialPageParam: 1, getNextPageParam: (last) => last.page * last.page_size < last.total ? last.page + 1 : undefined, enabled: apiAvailable && realWorkflow, staleTime: 30_000 });
  const records = useMemo(() => realWorkflow ? realCommentsQuery.data?.pages.flatMap((page) => page.items) : apiCommentsQuery.data, [realWorkflow, realCommentsQuery.data, apiCommentsQuery.data]);
  const apiComments = useMemo<UniversityWorkflowComment[] | null>(() => records?.filter((comment) => comment.stage_id === null || comment.stage_id === stageId).map((comment) => ({ id: comment.id, author: user?.id === comment.author_keycloak_sub ? user.name : isUuidLike(comment.author_keycloak_sub) ? 'Участник Workflow' : comment.author_keycloak_sub, authorId: comment.author_keycloak_sub, authorRole: user?.id === comment.author_keycloak_sub ? user.roleLabel : 'Участник Workflow', isSystem: false, occurredAt: comment.created_at, updatedAt: comment.updated_at, text: comment.content, isOptimistic: comment.is_optimistic, canDelete: true, attachments: comment.attachments?.map((attachment) => workflowAttachmentFromApi(attachment, user)) })) ?? null, [records, stageId, user]);
  const renderedComments = useMemo(() => apiComments ? [...apiComments, ...comments.filter((comment) => !apiComments.some((record) => record.id === comment.id))] : comments, [apiComments, comments]);
  // The existing Workflow showed newest comments first; keep that order for both sources.
  const orderedComments = useMemo(() => renderedComments.slice().sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)), [renderedComments]);
  const visibleComments = showAll ? orderedComments : orderedComments.slice(0, 3);
  const addComment = async (content: string, files: File[]) => { await create.mutateAsync({ content, files }); };
  const queryError = normalizeApiError(realWorkflow ? realCommentsQuery.error : apiCommentsQuery.error).message;
  const loading = realWorkflow ? realCommentsQuery.isPending : apiCommentsQuery.isPending;
  const failed = realWorkflow ? realCommentsQuery.isError : apiCommentsQuery.isError;
  const retry = () => realWorkflow ? void realCommentsQuery.refetch() : void apiCommentsQuery.refetch();
  return <section className={styles.section} aria-labelledby={`${stageId}-comments-title`}><div className={styles.heading}><h3 id={`${stageId}-comments-title`}><Comments size={18} fill="currentColor" />Комментарии <span className={styles.count}>{renderedComments.length}</span></h3>{renderedComments.length > 3 ? <Button variant="ghost" size="s" type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : 'Показать все'}</Button> : null}</div>{apiAvailable && loading ? <ListSkeleton items={3} /> : apiAvailable && failed ? <ErrorState title="Не удалось загрузить комментарии" description={queryError} headingLevel={3} onRetry={retry} /> : orderedComments.length ? <ul className={styles.commentList}>{visibleComments.map((comment) => <CommentItem key={comment.id} comment={comment} instanceId={instanceId} onNotify={onNotify} />)}</ul> : <EmptyState icon={<Comments size={18} fill="currentColor" />} title="Комментариев пока нет" description={readOnly ? 'На этом этапе комментариев не было.' : 'Первый комментарий можно добавить ниже.'} headingLevel={3} />}{realWorkflow && realCommentsQuery.hasNextPage ? <Button variant="ghost" size="s" type="button" loading={realCommentsQuery.isFetchingNextPage} onClick={() => void realCommentsQuery.fetchNextPage()}>Загрузить ещё комментарии</Button> : null}{!readOnly && user && (!realWorkflow || hasPermission(user, 'workflow.change_status')) ? <CommentEditor initialValue="" disabled={!apiAvailable || create.isPending} submitLabel="Отправить" onSubmit={addComment} allowFiles={realWorkflow} onGlobalError={(error) => onNotify?.({ intent: 'error', title: 'Комментарий не сохранён', message: error.message })} /> : null}</section>;
}

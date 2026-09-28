'use client';

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import Task from '@atomaro/icons/24/communication/Task';
import Edit from '@atomaro/icons/24/editor/Edit';
import Trash from '@atomaro/icons/24/action/Trash';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { queryKeys } from '@/shared/lib/query-keys';
import { createWorkflowTask, deleteWorkflowTask, updateWorkflowTask, workflowQueryKey, type UniversityWorkflowStage } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import { Input } from '@/shared/ui/rtk/form-controls';
import { Modal } from '@/shared/ui/rtk/modal';
import { ErrorState } from '@/shared/ui/error-state';
import { ListSkeleton } from '@/shared/ui/skeleton';
import styles from './university-workflow.module.css';

type TaskState = { loading: boolean; error: boolean; retry: () => void; hasMore?: boolean; loadingMore?: boolean; loadMore?: () => void };

export function WorkflowStageTasks({ stage, instanceId, canEdit, state }: { stage: UniversityWorkflowStage; instanceId: string; canEdit: boolean; state?: TaskState }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowTasks(instanceId) }),
      queryClient.invalidateQueries({ queryKey: workflowQueryKey(instanceId) }),
    ]);
  };
  const mutation = useMutation({
    mutationFn: async (action: { kind: 'create'; title: string } | { kind: 'edit'; id: string; title: string } | { kind: 'toggle'; id: string; completed: boolean } | { kind: 'delete'; id: string }) => {
      if (action.kind === 'create') return createWorkflowTask(instanceId, stage.templateStageId!, action.title);
      if (action.kind === 'edit') return updateWorkflowTask(instanceId, action.id, { title: action.title });
      if (action.kind === 'toggle') return updateWorkflowTask(instanceId, action.id, { status: action.completed ? 'open' : 'done' });
      return deleteWorkflowTask(instanceId, action.id);
    },
    onSuccess: async () => { setError(null); setTitle(''); setAdding(false); setEditing(null); setDeleting(null); await refresh(); },
    onError: (cause) => setError(normalizeApiError(cause).message),
  });
  const editable = canEdit && Boolean(stage.templateStageId) && (stage.status === 'current' || stage.status === 'overdue');
  const completed = stage.taskCompleted ?? stage.tasks.filter((task) => task.completed).length;
  const total = stage.taskTotal ?? stage.tasks.length;
  return <section className={styles.detailSection} aria-label="Задачи этапа">
    <div className={styles.detailSectionHeading}><h3><Task size={18} fill="currentColor" />Задачи этапа</h3>{total ? <span className={styles.taskCount}>{completed} из {total} выполнено</span> : null}</div>
    {state?.loading ? <ListSkeleton items={2} /> : state?.error ? <ErrorState title="Не удалось загрузить задачи" headingLevel={3} onRetry={state.retry} /> : <>
      {stage.tasks.length ? <ul className={styles.taskList}>{stage.tasks.map((task) => <li key={task.id} className={styles.taskRow}>
        <input type="checkbox" aria-label={`Выполнено: ${task.label}`} checked={task.completed} disabled={!editable || mutation.isPending} onChange={() => mutation.mutate({ kind: 'toggle', id: task.id, completed: task.completed })} />
        {editing?.id === task.id ? <><Input aria-label="Название задачи" value={editing.title} maxLength={512} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /><Button type="button" variant="primary" size="s" disabled={!editing.title.trim() || mutation.isPending} onClick={() => mutation.mutate({ kind: 'edit', id: task.id, title: editing.title.trim() })}>Сохранить</Button><Button type="button" variant="ghost" size="s" onClick={() => setEditing(null)}>Отмена</Button></> : <><span className={`${styles.taskLabel} ${task.completed ? styles.taskCompleted : ''}`}>{task.label}</span>{editable ? <><Tooltip content="Редактировать"><IconButton icon={<Edit size={18} fill="currentColor" />} label={`Редактировать задачу «${task.label}»`} size={18} disabled={mutation.isPending} onClick={() => setEditing({ id: task.id, title: task.label })} /></Tooltip><Tooltip content="Удалить"><IconButton icon={<Trash size={18} fill="currentColor" />} label={`Удалить задачу «${task.label}»`} size={18} intent="danger" disabled={mutation.isPending} onClick={() => setDeleting({ id: task.id, title: task.label })} /></Tooltip></> : null}</>}
      </li>)}</ul> : <p className={styles.taskEmpty}>Задач пока нет.</p>}
      {state?.hasMore ? <Button variant="ghost" size="s" type="button" loading={state.loadingMore} onClick={state.loadMore}>Загрузить ещё</Button> : null}
      {editable ? adding ? <form className={styles.taskAdd} onSubmit={(event) => { event.preventDefault(); if (title.trim()) mutation.mutate({ kind: 'create', title: title.trim() }); }}><Input aria-label="Новая задача" value={title} maxLength={512} autoFocus onChange={(event) => setTitle(event.target.value)} /><Button type="submit" variant="primary" size="s" disabled={!title.trim() || mutation.isPending}>Добавить</Button><Button type="button" variant="ghost" size="s" onClick={() => setAdding(false)}>Отмена</Button></form> : <Button type="button" variant="orange" size="s" onClick={() => setAdding(true)}>+ Добавить задачу</Button> : null}
    </>}
    {error ? <p role="alert" className={styles.taskError}>{error}</p> : null}
    {deleting ? <Modal title="Удалить задачу?" onClose={() => { if (!mutation.isPending) setDeleting(null); }}><p>«{deleting.title}» будет удалена.</p>{error ? <p role="alert" className={styles.taskError}>{error}</p> : null}<div className={styles.editActions}><Button type="button" variant="ghost" size="s" disabled={mutation.isPending} onClick={() => setDeleting(null)}>Отмена</Button><Button type="button" variant="danger" size="s" loading={mutation.isPending} onClick={() => mutation.mutate({ kind: 'delete', id: deleting.id })}>Удалить</Button></div></Modal> : null}
  </section>;
}

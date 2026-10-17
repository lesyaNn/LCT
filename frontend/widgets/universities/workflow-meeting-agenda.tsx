'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission, hasRole } from '@/shared/lib/access-control';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { downloadBlob } from '@/shared/lib/download-blob';
import { formatDateRu, formatDateTimeRu } from '@/shared/lib/formatters';
import { queryKeys } from '@/shared/lib/query-keys';
import { createWorkflowComment, downloadMeetingAgenda, getMeetingAgenda, isRealWorkflowMode, listWorkflowCommentsPage, meetingAgendaQueryKey, updateWorkflowQuestionStatus, workflowCommentsQueryKey, type WorkflowCommentApiRecord } from '@/shared/lib/universities-repository';
import { listUniversityWorkflowInstances, universityWorkflowInstancesQueryKey } from '@/shared/lib/workflow-creation-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Select } from '@/shared/ui/rtk/form-controls';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { ErrorState } from '@/shared/ui/error-state';
import { ListSkeleton } from '@/shared/ui/skeleton';
import { CommentEditor } from './workflow-comments';
import styles from './university-passport-sections.module.css';

export function WorkflowMeetingAgenda({ universityId }: { universityId: string }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [showResolved, setShowResolved] = useState(false);
  const [actionError, setActionError] = useState('');
  const allowed = isRealWorkflowMode() && hasPermission(user, 'workflow.read');
  const instancesQuery = useQuery({
    queryKey: universityWorkflowInstancesQueryKey(universityId),
    queryFn: ({ signal }) => listUniversityWorkflowInstances(universityId, signal),
    enabled: allowed,
    staleTime: 30_000,
  });
  const instances = instancesQuery.data ?? [];
  const meetingStages = instances.flatMap((instance) => {
    const stage = instance.stages.find((item) => item.id === instance.current_instance_stage_id);
    return instance.status === 'active' && stage?.order_index === 3 ? [{ instance, stage }] : [];
  });
  const selected = meetingStages.find(({ instance }) => instance.id === selectedId) ?? meetingStages[0];
  const agenda = useQuery({
    queryKey: meetingAgendaQueryKey(selected?.instance.id ?? ''),
    queryFn: ({ signal }) => getMeetingAgenda(selected!.instance.id, signal),
    enabled: allowed && Boolean(selected),
    staleTime: 30_000,
  });
  const resolvedQueryKey = ['meeting-agenda-resolved', universityId] as const;
  const resolved = useQuery({
    queryKey: [...resolvedQueryKey, instances.map((instance) => instance.id)],
    queryFn: async () => {
      const pages = await Promise.all(instances.filter((instance) => instance.status !== 'archived').map(async (instance) => {
        const comments: WorkflowCommentApiRecord[] = [];
        let page = 1;
        let hasMore = true;
        while (hasMore) {
          const result = await listWorkflowCommentsPage(instance.id, page);
          comments.push(...result.items);
          hasMore = page * result.page_size < result.total;
          page += 1;
        }
        return comments;
      }));
      return pages.flat().filter((comment) => comment.question_status === 'resolved').sort((left, right) => right.updated_at.localeCompare(left.updated_at));
    },
    enabled: allowed && Boolean(selected) && showResolved,
    staleTime: 30_000,
  });
  const download = useMutation({
    mutationFn: () => downloadMeetingAgenda(selected!.instance.id),
    onSuccess: (blob) => downloadBlob(blob, `meeting-agenda-${selected!.instance.id}.pdf`),
  });
  const createQuestion = useMutation({
    mutationFn: (content: string) => createWorkflowComment(selected!.instance.id, content, selected?.stage.template_stage_id ?? undefined, [], true),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: meetingAgendaQueryKey(selected!.instance.id) }),
        queryClient.invalidateQueries({ queryKey: workflowCommentsQueryKey(selected!.instance.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(selected!.instance.id) }),
      ]);
      setAddingQuestion(false);
      setActionError('');
    },
  });
  const changeQuestionStatus = useMutation({
    mutationFn: ({ commentId, status }: { commentId: string; originInstanceId: string; status: 'open' | 'resolved' }) => updateWorkflowQuestionStatus(commentId, status),
    onSuccess: async (_, { originInstanceId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: meetingAgendaQueryKey(selected!.instance.id) }),
        queryClient.invalidateQueries({ queryKey: resolvedQueryKey }),
        queryClient.invalidateQueries({ queryKey: workflowCommentsQueryKey(originInstanceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.universities.workflowHistory(originInstanceId) }),
      ]);
      setActionError('');
    },
    onError: (cause) => setActionError(normalizeApiError(cause).message),
  });

  if (!allowed) return null;
  if (instancesQuery.isPending) return <div className={styles.agenda}><ListSkeleton items={2} /></div>;
  if (instancesQuery.isError) return <div className={styles.agenda}><ErrorState title="Не удалось загрузить подготовку к встрече" description={normalizeApiError(instancesQuery.error).message} headingLevel={3} onRetry={() => void instancesQuery.refetch()} /></div>;
  if (!selected) return null;

  const data = agenda.data;
  const canCreateQuestion = hasPermission(user, 'workflow.change_status');
  const canUpdateQuestion = hasPermission(user, 'workflow.comment.update');
  const canManageQuestions = hasRole(user, 'admin') || hasRole(user, 'manager');
  return <section className={styles.agenda} aria-labelledby="meeting-agenda-title">
    <div className={styles.agendaHeader}>
      <div>
        <h2 id="meeting-agenda-title">Повестка для встречи</h2>
        <p>Сводка по вузу для этапа «{selected.stage.name}». Она не привязана к записи конкретной встречи.</p>
      </div>
      <Button variant="secondary" size="s" type="button" loading={download.isPending} disabled={!data || download.isPending} onClick={() => download.mutate()}>Скачать PDF</Button>
    </div>
    {meetingStages.length > 1 ? <label className={styles.agendaSelector}>Workflow для повестки и нового вопроса
      <Select value={selected.instance.id} disabled={download.isPending || createQuestion.isPending || changeQuestionStatus.isPending} onChange={(event) => { setSelectedId(event.target.value); setAddingQuestion(false); setActionError(''); }}>
        {meetingStages.map(({ instance }) => <option value={instance.id} key={instance.id}>{instance.program_name || instance.product_name || 'Без программы'}</option>)}
      </Select>
    </label> : null}
    {agenda.isPending ? <ListSkeleton items={3} /> : agenda.isError ? <ErrorState title="Не удалось загрузить повестку" description={normalizeApiError(agenda.error).message} headingLevel={3} onRetry={() => void agenda.refetch()} /> : data ? <>
      <p className={styles.agendaDate}>Данные на {formatDateRu(data.as_of)} · Workflow: {selected.instance.program_name || selected.instance.product_name || 'Без программы'}</p>
      <div className={styles.agendaGroup}>
        <h3>Пункты для обсуждения</h3>
        <div className={styles.agendaTopics}>
          <div><h4>Программы <span>{data.programs.total}</span></h4>{data.programs.items.length ? <ul>{data.programs.items.map((program) => <li key={program.program_id}>{program.name} · {program.status === 'active' ? 'активна' : 'запущена'}{program.launch_date ? ` · запуск ${formatDateRu(program.launch_date)}` : ''}</li>)}</ul> : <p>Активных программ нет.</p>}{data.programs.omitted ? <small>Ещё {data.programs.omitted} в полной выборке.</small> : null}</div>
          <div><h4>Лицензии до {formatDateRu(data.expires_through)} <span>{data.expiring_licenses.total}</span></h4>{data.expiring_licenses.items.length ? <ul>{data.expiring_licenses.items.map((license) => <li key={license.license_id}>{license.product} · № {license.license_number} · до {formatDateRu(license.expires_at)}</li>)}</ul> : <p>Лицензий с истекающим сроком нет.</p>}{data.expiring_licenses.omitted ? <small>Ещё {data.expiring_licenses.omitted} в полной выборке.</small> : null}</div>
        </div>
      </div>
      <div className={styles.agendaGroup}>
        <div className={styles.agendaQuestionHeading}><div><h3>Вопросы для обсуждения <span>{data.open_questions.total}</span></h3><p>Открытый вопрос требует решения. После отметки решённым он остаётся в комментариях исходного Workflow.</p></div>{canCreateQuestion ? <Button variant="secondary" size="s" type="button" onClick={() => { setAddingQuestion((current) => !current); setActionError(''); }}>{addingQuestion ? 'Отмена' : 'Добавить вопрос'}</Button> : null}</div>
        {data.open_questions.items.length ? <ul className={styles.agendaQuestions}>{data.open_questions.items.map((question) => {
          const source = instances.find((instance) => instance.id === question.instance_id);
          const sourceStage = source?.stages.find((stage) => stage.template_stage_id === question.stage_id);
          const canResolve = canUpdateQuestion && (canManageQuestions || question.author_keycloak_sub === user?.id);
          return <li key={question.comment_id}><div className={styles.agendaQuestionText}><p>{question.content}</p><small>{formatDateTimeRu(question.created_at)}{source?.program_name ? ` · ${source.program_name}` : ''}{sourceStage ? ` · ${sourceStage.name}` : ''}</small></div><div className={styles.agendaQuestionActions}><StatusBadge intent="warning">Открыт</StatusBadge>{canResolve ? <Button variant="ghost" size="s" type="button" loading={changeQuestionStatus.isPending && changeQuestionStatus.variables?.commentId === question.comment_id} disabled={changeQuestionStatus.isPending} onClick={() => changeQuestionStatus.mutate({ commentId: question.comment_id, originInstanceId: question.instance_id, status: 'resolved' })}>Отметить решённым</Button> : null}</div></li>;
        })}</ul> : <p className={styles.agendaEmpty}>Открытых вопросов нет.</p>}
        {data.open_questions.omitted ? <small className={styles.agendaMore}>Ещё {data.open_questions.omitted} в полной выборке.</small> : null}
        <Button className={styles.agendaToggle} variant="ghost" size="s" type="button" onClick={() => setShowResolved((current) => !current)}>{showResolved ? 'Скрыть решённые' : 'Показать решённые'}</Button>
        {showResolved ? resolved.isPending ? <ListSkeleton items={2} /> : resolved.isError ? <ErrorState title="Не удалось загрузить решённые вопросы" description={normalizeApiError(resolved.error).message} headingLevel={3} onRetry={() => void resolved.refetch()} /> : resolved.data?.length ? <ul className={styles.agendaQuestions}>{resolved.data.map((question) => {
          const source = instances.find((instance) => instance.id === question.instance_id);
          const sourceStage = source?.stages.find((stage) => stage.template_stage_id === question.stage_id);
          const canReopen = canUpdateQuestion && (canManageQuestions || question.author_keycloak_sub === user?.id);
          return <li key={question.id}><div className={styles.agendaQuestionText}><p>{question.content}</p><small>{formatDateTimeRu(question.created_at)}{source?.program_name ? ` · ${source.program_name}` : ''}{sourceStage ? ` · ${sourceStage.name}` : ''}</small></div><div className={styles.agendaQuestionActions}><StatusBadge intent="success">Решён</StatusBadge>{canReopen ? <Button variant="ghost" size="s" type="button" loading={changeQuestionStatus.isPending && changeQuestionStatus.variables?.commentId === question.id} disabled={changeQuestionStatus.isPending} onClick={() => changeQuestionStatus.mutate({ commentId: question.id, originInstanceId: question.instance_id, status: 'open' })}>Вернуть к обсуждению</Button> : null}</div></li>;
        })}</ul> : <p className={styles.agendaEmpty}>Решённых вопросов нет.</p> : null}
        {addingQuestion ? <div className={styles.agendaEditor}><CommentEditor initialValue="" disabled={createQuestion.isPending} submitLabel="Добавить вопрос" questionMode onSubmit={async (content) => { await createQuestion.mutateAsync(content); }} onGlobalError={(error) => setActionError(error.message)} /></div> : null}
      </div>
    </> : null}
    {actionError ? <p className={styles.agendaError} role="alert">{actionError}</p> : null}
    {download.isError ? <p className={styles.agendaError} role="alert">{normalizeApiError(download.error).message}</p> : null}
  </section>;
}

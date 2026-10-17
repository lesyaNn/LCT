'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { downloadMeetingAgenda, getMeetingAgenda, meetingAgendaQueryKey } from '@/shared/lib/universities-repository';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { downloadBlob } from '@/shared/lib/download-blob';
import { formatDateRu } from '@/shared/lib/formatters';
import { Button } from '@/shared/ui/rtk/button';
import { ErrorState } from '@/shared/ui/error-state';
import { ListSkeleton } from '@/shared/ui/skeleton';
import styles from './university-workflow.module.css';

export function WorkflowMeetingAgenda({ instanceId }: { instanceId: string }) {
  const agenda = useQuery({ queryKey: meetingAgendaQueryKey(instanceId), queryFn: ({ signal }) => getMeetingAgenda(instanceId, signal), staleTime: 30_000 });
  const download = useMutation({
    mutationFn: () => downloadMeetingAgenda(instanceId),
    onSuccess: (blob) => downloadBlob(blob, `meeting-agenda-${instanceId}.pdf`),
  });
  const data = agenda.data;
  return <section className={styles.detailSection} aria-labelledby={`${instanceId}-agenda-title`}>
    <div className={styles.agendaHeading}><div className={styles.detailSectionHeading}><h3 id={`${instanceId}-agenda-title`}>Повестка встречи</h3></div><Button variant="secondary" size="s" type="button" loading={download.isPending} disabled={!data || download.isPending} onClick={() => download.mutate()}>Скачать PDF</Button></div>
    {agenda.isPending ? <ListSkeleton items={3} /> : agenda.isError ? <ErrorState title="Не удалось загрузить повестку" description={normalizeApiError(agenda.error).message} headingLevel={3} onRetry={() => void agenda.refetch()} /> : data ? <><p className={styles.agendaAsOf}>Данные на {formatDateRu(data.as_of)}</p><div className={styles.agendaSections}>
      <div><h4>Активные и запущенные программы <span>{data.programs.total}</span></h4>{data.programs.items.length ? <ul>{data.programs.items.map((program) => <li key={program.program_id}>{program.name} · {program.status === 'active' ? 'активна' : 'запущена'}{program.launch_date ? ` · запуск ${formatDateRu(program.launch_date)}` : ''}</li>)}</ul> : <p>Нет программ для повестки.</p>}{data.programs.omitted ? <small>Ещё {data.programs.omitted} в полной выборке.</small> : null}</div>
      <div><h4>Лицензии до {formatDateRu(data.expires_through)} <span>{data.expiring_licenses.total}</span></h4>{data.expiring_licenses.items.length ? <ul>{data.expiring_licenses.items.map((license) => <li key={license.license_id}>{license.product} · № {license.license_number} · до {formatDateRu(license.expires_at)}</li>)}</ul> : <p>Нет лицензий с истекающим сроком.</p>}{data.expiring_licenses.omitted ? <small>Ещё {data.expiring_licenses.omitted} в полной выборке.</small> : null}</div>
      <div><h4>Открытые вопросы <span>{data.open_questions.total}</span></h4>{data.open_questions.items.length ? <ul>{data.open_questions.items.map((question) => <li key={question.comment_id}>{question.content}</li>)}</ul> : <p>Открытых вопросов нет.</p>}{data.open_questions.omitted ? <small>Ещё {data.open_questions.omitted} в полной выборке.</small> : null}</div>
    </div></> : null}
    {download.isError ? <p className={styles.agendaError} role="alert">{normalizeApiError(download.error).message}</p> : null}
  </section>;
}

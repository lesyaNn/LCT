'use client';

import { useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { downloadBlob } from '@/shared/lib/download-blob';
import { downloadMeetingAgenda } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import styles from './university-passport-sections.module.css';

type AgendaTarget = { instanceId: string; stageId: string };

export function MeetingAgendaPdfAction({ instanceId, stageId, placement }: AgendaTarget & { placement: 'meetings' | 'workflow' }) {
  const requestInFlight = useRef(false);
  const download = useMutation({
    mutationFn: ({ instanceId: workflowId, stageId: meetingStageId }: AgendaTarget) => downloadMeetingAgenda(workflowId, meetingStageId),
    onSuccess: (blob, target) => downloadBlob(blob, `meeting-agenda-${target.instanceId}-${target.stageId}.pdf`),
    onSettled: () => { requestInFlight.current = false; },
  });
  const startDownload = () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    download.mutate({ instanceId, stageId });
  };
  const button = <Button variant={placement === 'meetings' ? 'ghost' : 'secondary'} size="s" type="button" loading={download.isPending} disabled={download.isPending} onClick={startDownload}>
    <DocumentText size={16} fill="currentColor" />
    {download.isPending ? 'Формирование…' : placement === 'meetings' ? 'Скачать повестку PDF' : 'Скачать повестку встречи'}
  </Button>;
  return <div className={styles.agendaPdfAction}>
    {placement === 'meetings' ? <Tooltip content="Краткая сводка программ, лицензий и открытых вопросов к встрече">{button}</Tooltip> : button}
    {download.isError ? <p className={styles.agendaError} role="alert">{normalizeApiError(download.error).message} Попробуйте ещё раз.</p> : null}
  </div>;
}

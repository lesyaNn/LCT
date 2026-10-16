'use client';

import Link from 'next/link';
import type { WorkflowInstanceApiRecord } from '@/shared/lib/universities-repository';
import { Button } from '@/shared/ui/rtk/button';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { WorkflowArchiveAction } from '@/widgets/workflows/workflow-archive-action';
import styles from './university-passport.module.css';

export function PassportWorkflowCard({ instance, programName, onLaunch }: {
  instance?: WorkflowInstanceApiRecord;
  programName?: string;
  onLaunch?: () => void;
}) {
  const current = instance?.stages.find((stage) => stage.id === instance.current_instance_stage_id || stage.template_stage_id === instance.current_stage_id)
    ?? instance?.stages.find((stage) => stage.status === 'current');
  const completed = instance?.stages.filter((stage) => stage.status === 'completed').length ?? 0;
  const total = instance?.stages.length ?? 0;
  const statusLabel = instance?.status === 'completed' ? 'Завершён' : instance?.is_overdue ? 'Просрочен' : instance ? 'В работе' : 'Workflow не запущен';
  return <article className={styles.workflowItem}>
    <div className={styles.workflowItemTop}>
      <strong>{programName || instance?.program_name || 'Без программы'}</strong>
      {instance ? <WorkflowArchiveAction instanceId={instance.id} universityId={instance.university_id} active={instance.status === 'active'} label="Удалить workflow" /> : null}
    </div>
    <div className={styles.workflowItemStatus}>
      <StatusBadge intent={!instance ? 'neutral' : instance.status === 'completed' ? 'success' : instance.is_overdue ? 'danger' : 'brand'}>{statusLabel}</StatusBadge>
    </div>
    {instance ? <><p>{instance.status === 'completed' ? 'Все этапы завершены' : current ? <>Текущий этап: <b>{current.name}</b></> : 'Этап не назначен'}</p><div className={styles.workflowProgress}><div className={styles.progressLabel}><span>Прогресс</span><strong>{completed} из {total} этапов</strong></div><div className={styles.progressTrack} role="progressbar" aria-label={`Пройдено ${completed} из ${total} этапов`} aria-valuemin={0} aria-valuemax={total} aria-valuenow={completed}><span style={{ width: `${total ? completed / total * 100 : 0}%` }} /></div></div><Link className={styles.workflowCardLink} href={`/workflows/${instance.id}`} aria-label={`Открыть Workflow: ${instance.program_name || 'Без программы'}`} /></>
      : onLaunch ? <Button variant="primary" size="s" type="button" onClick={onLaunch}>Запустить Workflow</Button> : null}
  </article>;
}

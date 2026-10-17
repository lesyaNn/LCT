import Link from 'next/link';
import type { ReactNode } from 'react';
import User from '@atomaro/icons/24/communication/User';
import Calendar from '@atomaro/icons/24/communication/Calendar';
import { formatDateRu } from '@/shared/lib/formatters';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import type { WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import { WorkflowArchiveAction } from './workflow-archive-action';
import styles from './workflow-overview.module.css';

function statusLabel(status: WorkflowOverviewItem['status']) {
  return status === 'completed' ? 'Завершён' : status === 'overdue' ? 'Просрочен' : 'В работе';
}

export function WorkflowCard({ item, dragHandle }: { item: WorkflowOverviewItem; dragHandle?: ReactNode }) {
  const href = isMockDataSourceFor('workflow') && item.programKey
    ? `/universities/${encodeURIComponent(item.universityId)}?tab=workflow&program=${encodeURIComponent(item.programKey)}&workflow=${encodeURIComponent(item.instanceId)}`
    : `/workflows/${encodeURIComponent(item.instanceId)}`;
  const responsible = item.stage.responsible;
  return <article className={`${styles.card} ${item.status === 'overdue' ? styles.cardOverdue : ''}`}>
    <Link className={styles.cardHitArea} href={href} aria-label={`Открыть Workflow: ${item.universityName}${item.programName ? ` — ${item.programName}` : ''}`} onKeyDown={(event) => {
      if (event.key === ' ') { event.preventDefault(); event.currentTarget.click(); }
    }} />
    <div className={styles.cardTop}><strong className={styles.cardTitle}>{item.universityName}</strong><div className={styles.cardTopActions}>{dragHandle}<WorkflowArchiveAction instanceId={item.instanceId} universityId={item.universityId} active={item.status !== 'completed'} label="Удалить workflow" /></div></div>
    {item.programName ? <p className={styles.program}>{item.programName}</p> : null}
    <p className={styles.stageName}>{item.stage.name}</p>
    <StatusBadge intent={item.status === 'completed' ? 'success' : item.status === 'overdue' ? 'orange' : 'brand'}>{statusLabel(item.status)}</StatusBadge>
    {responsible || item.stage.deadline ? <dl className={styles.meta}>
      {responsible ? <div className={styles.metaItem}><User size={20} fill="currentColor" /><div><dt>Ответственный за этап</dt><dd>{responsible.name}</dd></div></div> : null}
      {item.stage.deadline ? <div className={`${styles.metaItem} ${styles.deadlineMeta}`}><Calendar size={20} fill="currentColor" /><div><dt>Срок этапа</dt><dd>{formatDateRu(item.stage.deadline)}</dd></div></div> : null}
    </dl> : null}
    <div className={styles.cardActions}><Link href={href}>{item.status === 'completed' ? 'Открыть историю' : 'Открыть / перевести'}</Link></div>
  </article>;
}

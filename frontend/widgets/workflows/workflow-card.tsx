import Link from 'next/link';
import type { ReactNode } from 'react';
import { formatDateRu } from '@/shared/lib/formatters';
import type { WorkflowOverviewItem } from '@/shared/lib/workflow-overview-repository';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './workflow-overview.module.css';

function statusLabel(status: WorkflowOverviewItem['status']) {
  return status === 'completed' ? 'Завершён' : status === 'overdue' ? 'Просрочен' : 'В работе';
}

export function WorkflowCard({ item, dragHandle }: { item: WorkflowOverviewItem; dragHandle?: ReactNode }) {
  const href = item.programKey
    ? `/universities/${encodeURIComponent(item.universityId)}?tab=workflow&program=${encodeURIComponent(item.programKey)}&workflow=${encodeURIComponent(item.instanceId)}`
    : `/workflows/${encodeURIComponent(item.instanceId)}`;
  return <article className={styles.card}>
    <div className={styles.cardTop}><Link className={styles.cardTitle} href={href}>{item.universityName}</Link>{dragHandle}</div>
    <p className={styles.program}>{item.programName ?? 'Программа не привязана'}</p>
    <p className={styles.stageName}>{item.stage.name}</p>
    <StatusBadge intent={item.status === 'completed' ? 'success' : item.status === 'overdue' ? 'danger' : 'brand'}>{statusLabel(item.status)}</StatusBadge>
    <dl className={styles.meta}><div><dt>Ответственный за ВУЗ</dt><dd>{item.responsible?.name ?? 'Не назначен'}</dd></div><div><dt>Срок этапа</dt><dd>{item.stage.deadline ? formatDateRu(item.stage.deadline) : 'Не указан'}</dd></div></dl>
    <div className={styles.cardActions}><Link href={href}>Открыть / перевести</Link><Link href={`/universities/${encodeURIComponent(item.universityId)}?tab=responsibles`}>Сменить ответственного за ВУЗ</Link></div>
  </article>;
}

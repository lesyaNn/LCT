import type { ReactNode } from 'react';
import { StatusBadge } from '@/shared/ui/rtk/status-badge';
import styles from './passport-section-header.module.css';

export function PassportSectionHeader({ title, count, actions, id }: { title: string; count?: number; actions?: ReactNode; id?: string }) {
  return <div className={styles.header}>
    <div className={styles.title}><h2 id={id}>{title}</h2>{count !== undefined ? <StatusBadge intent="neutral" showIndicator={false}>{count}</StatusBadge> : null}</div>
    {actions ? <div className={styles.actions}>{actions}</div> : null}
  </div>;
}

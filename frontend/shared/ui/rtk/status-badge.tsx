import type { ReactNode } from 'react';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import styles from './status-badge.module.css';

export function StatusBadge({ intent, children, icon, size = 'sm', variant = 'filled' }: { intent: SemanticIntent; children: ReactNode; icon?: ReactNode; size?: 'sm' | 'md' | 'lg'; variant?: 'filled' | 'inline' }) {
  return <span className={`${styles.badge} ${styles[intent]} ${styles[size]} ${variant === 'inline' ? styles.inline : ''}`}><span className={styles.indicator} aria-hidden="true">{icon ?? <span className={styles.dot} />}</span>{children}</span>;
}

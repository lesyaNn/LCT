import type { ReactNode } from 'react';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import styles from './status-badge.module.css';

export function StatusBadge({ intent, children, variant = 'filled' }: { intent: SemanticIntent; children: ReactNode; variant?: 'filled' | 'inline' }) {
  return <span className={`${styles.badge} ${styles[intent]} ${variant === 'inline' ? styles.inline : ''}`}><span className={styles.dot} aria-hidden="true" />{children}</span>;
}

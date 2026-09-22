import type { ReactNode } from 'react';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import styles from './status-badge.module.css';

export function StatusBadge({ intent, children }: { intent: SemanticIntent; children: ReactNode }) {
  return <span className={`${styles.badge} ${styles[intent]}`}><span className={styles.dot} aria-hidden="true" />{children}</span>;
}

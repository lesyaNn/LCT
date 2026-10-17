import type { ReactNode } from 'react';
import type { SemanticIntent } from '@/shared/lib/status-semantics';
import styles from './status-badge.module.css';

export function StatusBadge({ intent, children, icon, showIndicator = true, size = 'sm', variant = 'filled', 'data-testid': testId }: { intent: SemanticIntent; children: ReactNode; icon?: ReactNode; showIndicator?: boolean; size?: 'sm' | 'md' | 'lg'; variant?: 'filled' | 'inline'; 'data-testid'?: string }) {
  return <span className={`${styles.badge} ${styles[intent]} ${styles[size]} ${variant === 'inline' ? styles.inline : ''}`} data-testid={testId}>{showIndicator ? <span className={styles.indicator} aria-hidden="true">{icon ?? <span className={styles.dot} />}</span> : null}{children}</span>;
}

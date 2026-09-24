import type { ReactNode } from 'react';
import styles from './tabbed-surface.module.css';

export function TabbedSurface({ tabs, children, className = '' }: { tabs?: ReactNode; children: ReactNode; className?: string }) {
  return <div className={`${styles.surface} ${className}`}>{tabs ? <div className={styles.tabs}>{tabs}</div> : null}<div className={styles.content}>{children}</div></div>;
}

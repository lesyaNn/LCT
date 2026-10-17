import type { ReactNode } from 'react';
import styles from './tabbed-surface.module.css';

export function TabbedSurface({ tabs, children, className = '', contentClassName = '' }: { tabs?: ReactNode; children: ReactNode; className?: string; contentClassName?: string }) {
  return <div className={`${styles.surface} ${className}`}>{tabs ? <div className={styles.tabs}>{tabs}</div> : null}<div className={`${styles.content} ${contentClassName}`}>{children}</div></div>;
}

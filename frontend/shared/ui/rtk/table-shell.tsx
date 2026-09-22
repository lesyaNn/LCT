import type { ReactNode } from 'react';
import styles from './data-table.module.css';

interface TableShellProps {
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
  ariaBusy?: boolean;
}

export function TableShell({ children, className = '', ariaLabel, ariaBusy }: TableShellProps) {
  return <div className={`${styles.shell} ${className}`} aria-label={ariaLabel} aria-busy={ariaBusy || undefined}>{children}</div>;
}

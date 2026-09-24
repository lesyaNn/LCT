import type { ReactNode } from 'react';
import styles from './filter-surface.module.css';

export function FilterSurface({ children, className, label = 'Фильтры' }: { children: ReactNode; className?: string; label?: string }) {
  return <section className={[styles.root, className].filter(Boolean).join(' ')} aria-label={label}>{children}</section>;
}

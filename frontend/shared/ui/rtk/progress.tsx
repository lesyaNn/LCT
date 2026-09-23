import type { CSSProperties } from 'react';
import styles from './progress.module.css';

export function Progress({ value, label }: { value: number | null | undefined; label: string }) {
  const indeterminate = value === null || value === undefined;
  const normalized = indeterminate ? 0 : Math.max(0, Math.min(100, Math.round(value)));
  const style = { '--rtk-progress-value': `${normalized}%` } as CSSProperties;
  return <div className={`${styles.progress} ${indeterminate ? styles.indeterminate : ''}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} {...(indeterminate ? { 'aria-valuetext': 'Выполняется' } : { 'aria-valuenow': normalized, 'aria-valuetext': `${normalized}%` })} aria-busy={indeterminate} style={style}><span /></div>;
}

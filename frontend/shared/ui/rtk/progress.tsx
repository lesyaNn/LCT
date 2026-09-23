import type { CSSProperties } from 'react';
import styles from './progress.module.css';

export function Progress({ value, label }: { value: number; label: string }) {
  const normalized = Math.max(0, Math.min(100, Math.round(value)));
  const style = { '--rtk-progress-value': `${normalized}%` } as CSSProperties;
  return <div className={styles.progress} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={normalized} aria-valuetext={`${normalized}%`} style={style}><span /></div>;
}

'use client';

import { useId, type ReactNode } from 'react';
import styles from './tooltip.module.css';

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  const id = useId();
  return <span className={styles.host}><span aria-describedby={id}>{children}</span><span className={styles.tooltip} id={id} role="tooltip">{content}</span></span>;
}

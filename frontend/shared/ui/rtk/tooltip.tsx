'use client';

import { useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './tooltip.module.css';

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  const id = useId();
  const hostRef = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const show = () => {
    const rect = hostRef.current?.getBoundingClientRect();
    if (!rect) return;
    const halfWidth = Math.min(140, (window.innerWidth - 24) / 2);
    setPosition({
      left: Math.max(halfWidth + 12, Math.min(rect.left + halfWidth, window.innerWidth - halfWidth - 12)),
      top: rect.bottom + 80 > window.innerHeight ? Math.max(12, rect.top - 80) : rect.bottom + 8,
    });
  };
  return <span className={styles.host} ref={hostRef} onMouseEnter={show} onMouseLeave={() => setPosition(null)} onFocusCapture={show} onBlurCapture={() => setPosition(null)}>
    <span aria-describedby={id}>{children}</span>
    {position && typeof document !== 'undefined' ? createPortal(<span className={styles.tooltip} id={id} role="tooltip" style={{ left: position.left, top: position.top }}>{content}</span>, document.body) : null}
  </span>;
}

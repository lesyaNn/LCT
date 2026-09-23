'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import styles from './modal.module.css';

export function Modal({ title, children, onClose, labelledBy, size = 'm' }: { title: string; children: ReactNode; onClose: () => void; labelledBy?: string; size?: 'm' | 'l' }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previous?.focus();
    };
  }, [onClose]);
  const titleId = labelledBy ?? 'rtk-modal-title';
  return <div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className={`${styles.dialog} ${styles[size]}`} role="dialog" aria-modal="true" aria-labelledby={titleId}><div className={styles.header}><h2 id={titleId}>{title}</h2><button ref={closeRef} className={styles.close} type="button" aria-label="Закрыть" onClick={onClose}><CloseLarge size={20} fill="currentColor" /></button></div><div className={styles.body}>{children}</div></div></div>;
}

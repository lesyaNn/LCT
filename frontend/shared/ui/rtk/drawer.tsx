'use client';

import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import styles from './drawer.module.css';

export function Drawer({ title, children, onClose, side = 'right', labelledBy }: { title: string; children: ReactNode; onClose: () => void; side?: 'left' | 'right'; labelledBy?: string }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const generatedTitleId = useId();
  const titleId = labelledBy ?? `rtk-drawer-title-${generatedTitleId}`;
  const onCloseRef = useRef(onClose);

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== 'Tab') return;
      const drawer = closeRef.current?.closest('[role="dialog"]') as HTMLElement | null;
      if (!drawer) return;
      const focusable = Array.from(drawer.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);
    return () => { document.body.style.overflow = ''; document.removeEventListener('keydown', handleKeyDown); previous?.focus(); };
  }, []);

  return <div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className={`${styles.drawer} ${styles[side]}`} role="dialog" aria-modal="true" aria-labelledby={titleId}><div className={styles.header}><h2 id={titleId}>{title}</h2><button ref={closeRef} className={styles.close} type="button" aria-label="Закрыть" onClick={onClose}><CloseLarge size={20} fill="currentColor" /></button></div><div className={styles.body}>{children}</div></aside></div>;
}

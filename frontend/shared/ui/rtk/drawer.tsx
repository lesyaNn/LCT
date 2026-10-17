'use client';

import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import { useEffect, useId, useRef, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styles from './drawer.module.css';

let openDrawers = 0;
let previousBodyOverflow = '';

export function Drawer({ title, children, footer, onClose, side = 'right', labelledBy, closeLabel = 'Закрыть', className = '' }: { title: string; children: ReactNode; footer?: ReactNode; onClose: () => void; side?: 'left' | 'right'; labelledBy?: string; closeLabel?: string; className?: string }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const generatedTitleId = useId();
  const titleId = labelledBy ?? `rtk-drawer-title-${generatedTitleId}`;
  const onCloseRef = useRef(onClose);
  const mounted = useSyncExternalStore(() => () => undefined, () => true, () => false);

  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => {
    if (!mounted) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      const drawer = closeRef.current?.closest('[role="dialog"]') as HTMLElement | null;
      if (!drawer || [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].at(-1) !== drawer) return;
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== 'Tab') return;
      const focusable = Array.from((drawer.parentElement ?? drawer).querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    if (openDrawers === 0) previousBodyOverflow = document.body.style.overflow;
    openDrawers += 1;
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', handleKeyDown);
    return () => { openDrawers -= 1; if (openDrawers === 0) document.body.style.overflow = previousBodyOverflow; document.removeEventListener('keydown', handleKeyDown); previous?.focus(); };
  }, [mounted]);

  if (!mounted) return null;
  return createPortal(<div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className={`${styles.drawer} ${styles[side]} ${className}`} role="dialog" aria-modal="true" aria-labelledby={titleId}><div className={styles.header}><h2 id={titleId}>{title}</h2><button ref={closeRef} className={styles.close} type="button" aria-label={closeLabel} onClick={onClose}><CloseLarge size={20} fill="currentColor" /></button></div><div className={styles.body}>{children}</div>{footer ? <div className={styles.footer}>{footer}</div> : null}</aside></div>, document.body);
}

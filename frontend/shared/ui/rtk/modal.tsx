'use client';

import { useEffect, useId, useRef, useSyncExternalStore, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import styles from './modal.module.css';

export function Modal({ title, children, onClose, labelledBy, initialFocusRef, size = 'm', fullHeight = false }: { title: string; children: ReactNode; onClose: () => void; labelledBy?: string; initialFocusRef?: RefObject<HTMLElement | null>; size?: 'm' | 'l' | 'xl'; fullHeight?: boolean }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const mounted = useSyncExternalStore(() => () => undefined, () => true, () => false);
  const onCloseRef = useRef(onClose);
  const generatedTitleId = useId();
  const titleId = labelledBy ?? `rtk-modal-title-${generatedTitleId}`;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!mounted) return;
    const previous = document.activeElement as HTMLElement | null;
    (initialFocusRef?.current ?? closeRef.current)?.focus();
    const dialog = closeRef.current?.closest('[role="dialog"]') as HTMLElement | null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialog) return;
      const focusable = Array.from((dialog.parentElement ?? dialog).querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previous?.focus();
    };
  }, [initialFocusRef, mounted]);

  if (!mounted) return null;
  return createPortal(<div className={styles.overlay} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className={`${styles.dialog} ${styles[size]}${fullHeight ? ` ${styles.full}` : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId}><div className={styles.header}><h2 id={titleId}>{title}</h2><button ref={closeRef} className={styles.close} type="button" aria-label="Закрыть" onClick={onClose}><CloseLarge size={20} fill="currentColor" /></button></div><div className={styles.body}>{children}</div></div></div>, document.body);
}

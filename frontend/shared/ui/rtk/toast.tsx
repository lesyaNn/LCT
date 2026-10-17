'use client';

import { useEffect, useRef, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import styles from './toast.module.css';

export type ToastIntent = 'success' | 'error' | 'warning' | 'info';

const AUTO_DISMISS_MS = 12_000;

let viewport: HTMLDivElement | null = null;
let mountedToasts = 0;

function getViewport(): HTMLDivElement {
  if (!viewport) {
    viewport = document.createElement('div');
    viewport.className = styles.viewport;
    viewport.setAttribute('aria-label', 'Уведомления');
    document.body.appendChild(viewport);
  }
  return viewport;
}

function subscribe(listener: () => void): () => void {
  mountedToasts += 1;
  getViewport();
  listener();
  return () => {
    mountedToasts -= 1;
    if (mountedToasts === 0) {
      viewport?.remove();
      viewport = null;
    }
  };
}

function currentViewport() { return viewport; }
function serverViewport() { return null; }

export function Toast({ intent, title, message, onClose }: { intent: ToastIntent; title: string; message?: ReactNode; onClose?: () => void }) {
  const host = useSyncExternalStore(subscribe, currentViewport, serverViewport);
  const closeRef = useRef(onClose);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const remainingRef = useRef(AUTO_DISMISS_MS);
  const hoveredRef = useRef(false);

  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    remainingRef.current = AUTO_DISMISS_MS;
    if (!hoveredRef.current && closeRef.current) {
      startedAtRef.current = Date.now();
      timerRef.current = window.setTimeout(() => closeRef.current?.(), AUTO_DISMISS_MS);
    }
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [intent, title, message]);

  const pause = () => {
    hoveredRef.current = true;
    if (timerRef.current === null) return;
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
    remainingRef.current = Math.max(0, remainingRef.current - (Date.now() - startedAtRef.current));
  };
  const resume = () => {
    hoveredRef.current = false;
    if (timerRef.current !== null || !closeRef.current) return;
    startedAtRef.current = Date.now();
    timerRef.current = window.setTimeout(() => closeRef.current?.(), remainingRef.current);
  };

  if (!host) return null;
  return createPortal(<div className={`${styles.toast} ${styles[intent]}`} role={intent === 'error' ? 'alert' : 'status'} aria-live={intent === 'error' ? 'assertive' : 'polite'} onMouseEnter={pause} onMouseLeave={resume} onFocusCapture={pause} onBlurCapture={resume}><div><strong>{title}</strong>{message ? <p>{message}</p> : null}</div>{onClose ? <button className={styles.close} type="button" aria-label="Закрыть уведомление" onClick={onClose}><CloseLarge size={16} fill="currentColor" /></button> : null}</div>, host);
}

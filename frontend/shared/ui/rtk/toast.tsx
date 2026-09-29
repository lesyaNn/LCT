'use client';

import { useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import styles from './toast.module.css';

export type ToastIntent = 'success' | 'error' | 'warning' | 'info';

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

  if (!host) return null;
  return createPortal(<div className={`${styles.toast} ${styles[intent]}`} role={intent === 'error' ? 'alert' : 'status'} aria-live={intent === 'error' ? 'assertive' : 'polite'}><div><strong>{title}</strong>{message ? <p>{message}</p> : null}</div>{onClose ? <button className={styles.close} type="button" aria-label="Закрыть уведомление" onClick={onClose}><CloseLarge size={16} fill="currentColor" /></button> : null}</div>, host);
}

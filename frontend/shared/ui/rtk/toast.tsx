'use client';

import type { ReactNode } from 'react';
import CloseLarge from '@atomaro/icons/24/navigation/CloseLarge';
import styles from './toast.module.css';

export type ToastIntent = 'success' | 'error' | 'info';

export function Toast({ intent, title, message, onClose }: { intent: ToastIntent; title: string; message?: ReactNode; onClose?: () => void }) {
  return <div className={`${styles.toast} ${styles[intent]}`} role="status" aria-live={intent === 'error' ? 'assertive' : 'polite'}><div><strong>{title}</strong>{message ? <p>{message}</p> : null}</div>{onClose ? <button className={styles.close} type="button" aria-label="Закрыть уведомление" onClick={onClose}><CloseLarge size={16} fill="currentColor" /></button> : null}</div>;
}

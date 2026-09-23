'use client';

import type { ReactNode } from 'react';
import ErrorStroke from '@atomaro/icons/24/alert/ErrorStroke';
import styles from './form-field.module.css';

export function FormField({ label, htmlFor, required = false, error, errorId, hint, hintId, children }: { label: string; htmlFor: string; required?: boolean; error?: string; errorId: string; hint?: string; hintId?: string; children: ReactNode }) {
  return <div className={styles.field}><label htmlFor={htmlFor}>{label}{required ? <sup aria-hidden="true"> *</sup> : null}</label>{children}{error ? <FormError id={errorId}>{error}</FormError> : hint ? <small className={styles.hint} id={hintId}>{hint}</small> : null}</div>;
}

export function FormError({ id, children }: { id: string; children: ReactNode }) {
  return <small className={styles.error} id={id} role="alert"><ErrorStroke size={14} fill="currentColor" aria-hidden="true" />{children}</small>;
}

export function FormErrorBanner({ children = 'Исправьте ошибки в форме' }: { children?: ReactNode }) {
  return <div className={styles.banner} role="alert"><ErrorStroke size={18} fill="currentColor" aria-hidden="true" /><span>{children}</span></div>;
}

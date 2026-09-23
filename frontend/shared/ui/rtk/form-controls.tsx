'use client';

import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import RemoveSmall from '@atomaro/icons/24/action/RemoveSmall';
import AddSmall from '@atomaro/icons/24/action/AddSmall';
import styles from './form-controls.module.css';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className = '', ...props }, ref) {
  return <input ref={ref} className={`${styles.input} ${className}`} {...props} />;
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className = '', ...props }, ref) {
  return <textarea ref={ref} className={`${styles.input} ${styles.textarea} ${className}`} {...props} />;
});

export function Switch({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: (checked: boolean) => void; label: string; disabled?: boolean }) {
  return <label className={`${styles.switchLabel} ${disabled ? styles.disabled : ''}`}><input className={styles.switchInput} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} /><span className={styles.switchTrack} aria-hidden="true"><span /></span><span className={styles.srOnly}>{label}</span></label>;
}

export function NumberStepper({ value, onChange, onCommit, label, disabled = false }: { value: number | null; onChange: (value: number | null) => void; onCommit: (value: number | null) => void; label: string; disabled?: boolean }) {
  const commit = (next: number | null) => {
    onChange(next);
    onCommit(next);
  };
  return <div className={styles.stepper} role="group" aria-label={label}><button type="button" aria-label={`${label}: уменьшить`} disabled={disabled || value === 0} onMouseDown={(event) => event.preventDefault()} onClick={() => commit(Math.max(0, (value ?? 0) - 1))}><RemoveSmall size={16} fill="currentColor" /></button><input type="number" min={0} step={1} inputMode="numeric" aria-label={label} value={value ?? ''} disabled={disabled} placeholder="—" onChange={(event) => { const raw = event.target.value; const parsed = Number(raw); onChange(raw === '' || !Number.isFinite(parsed) ? null : Math.max(0, Math.trunc(parsed))); }} onBlur={() => onCommit(value)} onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }} /><button type="button" aria-label={`${label}: увеличить`} disabled={disabled} onMouseDown={(event) => event.preventDefault()} onClick={() => commit((value ?? 0) + 1)}><AddSmall size={16} fill="currentColor" /></button></div>;
}

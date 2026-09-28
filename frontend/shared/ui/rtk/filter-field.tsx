'use client';

import { useId, type ReactNode } from 'react';
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import { Input } from './form-controls';
import styles from './filter-field.module.css';

export function FilterField({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) {
  return <label className={`${styles.field} ${className}`}><span className={styles.label}>{label}</span>{children}</label>;
}

export function SearchField({ label = 'Поиск', value, onChange, placeholder, className = '' }: { label?: string; value: string; onChange: (value: string) => void; placeholder?: string; className?: string }) {
  const id = useId();
  return <div className={`${styles.field} ${className}`}>
    <label className={styles.label} htmlFor={id}>{label}</label>
    <div className={styles.search}>
      <Input id={id} type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
      {value ? <button type="button" className={styles.clear} aria-label={`Очистить поле «${label}»`} onClick={() => onChange('')}><CloseSmall size={16} fill="currentColor" aria-hidden="true" /></button> : null}
    </div>
  </div>;
}

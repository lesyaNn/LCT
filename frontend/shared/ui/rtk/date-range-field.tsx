'use client';

import { useId } from 'react';
import { Input } from './form-controls';
import { Button } from './button';
import { periodPresetOptions, periodPresetRange } from '@/shared/lib/date-period';
import styles from './date-range-field.module.css';

export function DateRangeField({ label = 'Период', from, to, onFromChange, onToChange, onRangeChange, presets = false, disabled = false, fromError, toError }: {
  label?: string;
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  onRangeChange?: (from: string, to: string) => void;
  presets?: boolean;
  disabled?: boolean;
  fromError?: string;
  toError?: string;
}) {
  const id = useId();
  const selectedPreset = presets ? periodPresetOptions.find(({ id: preset }) => { const range = periodPresetRange(preset); return range.dateFrom === from && range.dateTo === to; })?.id : undefined;
  const selectPreset = (preset: (typeof periodPresetOptions)[number]['id']) => {
    const range = periodPresetRange(preset);
    if (onRangeChange) onRangeChange(range.dateFrom, range.dateTo);
    else { onFromChange(range.dateFrom); onToChange(range.dateTo); }
  };
  return <div className={styles.root} role="group" aria-label={label}>
    <span className={styles.label}>{label}</span>
    {presets ? <div className={styles.presets}>{periodPresetOptions.map(({ id: preset, label: text }) => <Button key={preset} variant={selectedPreset === preset ? (preset === 'current_year' ? 'orange' : 'primary') : 'secondary'} size="s" type="button" disabled={disabled} aria-pressed={selectedPreset === preset} onClick={() => selectPreset(preset)}>{text}</Button>)}</div> : null}
    <div className={styles.fields}>
      <label htmlFor={`${id}-from`}>От<Input id={`${id}-from`} type="date" value={from} max={to || undefined} disabled={disabled} aria-invalid={Boolean(fromError)} onChange={(event) => onFromChange(event.target.value)} />{fromError ? <small role="alert">{fromError}</small> : null}</label>
      <label htmlFor={`${id}-to`}>До<Input id={`${id}-to`} type="date" value={to} min={from || undefined} disabled={disabled} aria-invalid={Boolean(toError)} onChange={(event) => onToChange(event.target.value)} />{toError ? <small role="alert">{toError}</small> : null}</label>
    </div>
  </div>;
}

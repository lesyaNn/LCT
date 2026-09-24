'use client';

import { useMemo, useState, type ReactNode } from 'react';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import Search from '@atomaro/icons/24/action/Search';
import styles from './multiselect.module.css';

export interface MultiSelectOption {
  id: string;
  name: string;
  description?: string;
}

export function MultiSelect({ label, options, values, onChange, searchable = false, loading = false, disabled = false, placeholder = 'Не выбрано', renderOption, hint, className = '' }: { label: string; options: MultiSelectOption[]; values: string[]; onChange: (values: string[]) => void; searchable?: boolean; loading?: boolean; disabled?: boolean; placeholder?: string; renderOption?: (option: MultiSelectOption) => ReactNode; hint?: string; className?: string }) {
  const [search, setSearch] = useState('');
  const selectedOptions = options.filter((option) => values.includes(option.id));
  const visibleOptions = useMemo(() => {
    const term = search.trim().toLocaleLowerCase('ru-RU');
    return term ? options.filter((option) => `${option.name} ${option.description ?? ''}`.toLocaleLowerCase('ru-RU').includes(term)) : options;
  }, [options, search]);

  return (
    <details className={`${styles.root} ${disabled ? styles.disabled : ''} ${className}`}>
      <summary onClick={(event) => { if (disabled) event.preventDefault(); }} aria-disabled={disabled || undefined}>
        <span className={styles.summaryText}><strong>{label}</strong><small>{selectedOptions.length ? selectedOptions.map((option) => option.name).slice(0, 2).join(', ') + (selectedOptions.length > 2 ? ` +${selectedOptions.length - 2}` : '') : placeholder}</small></span>
        <ChevronDown size={16} fill="currentColor" aria-hidden="true" />
      </summary>
      <div className={styles.menu}>
        {hint ? <p className={styles.hint}>{hint}</p> : null}
        {loading ? <p className={styles.state}>Загрузка вариантов…</p> : null}
        {!loading && selectedOptions.length ? <div className={styles.selected}>{selectedOptions.map((option) => <button key={option.id} type="button" className={styles.chip} onClick={() => onChange(values.filter((value) => value !== option.id))} aria-label={`Убрать ${option.name} из фильтра «${label}»`}>{option.name}<CloseSmall size={14} fill="currentColor" aria-hidden="true" /></button>)}</div> : null}
        {!loading && searchable ? <div className={styles.search}><Search size={16} fill="currentColor" aria-hidden="true" /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти в списке" aria-label={`Поиск в поле «${label}»`} /></div> : null}
        {!loading && visibleOptions.map((option) => <label key={option.id}><span className={styles.optionContent}>{renderOption ? renderOption(option) : <><strong>{option.name}</strong>{option.description ? <small>{option.description}</small> : null}</>}</span><input className={styles.optionCheck} type="checkbox" checked={values.includes(option.id)} onChange={(event) => onChange(event.target.checked ? [...values, option.id] : values.filter((value) => value !== option.id))} /></label>)}
        {!loading && !visibleOptions.length ? <p className={styles.state}>Нет вариантов</p> : null}
      </div>
    </details>
  );
}

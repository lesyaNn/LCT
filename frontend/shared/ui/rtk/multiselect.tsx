'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import CheckSmall from '@atomaro/icons/24/navigation/CheckSmall';
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import Search from '@atomaro/icons/24/action/Search';
import styles from './multiselect.module.css';

export interface MultiSelectOption { id: string; name: string; description?: string }
type MenuPosition = { left: number; top?: number; bottom?: number; width: number; maxHeight: number };
type SelectProps = {
  id?: string; testId?: string; ariaInvalid?: boolean; ariaDescribedBy?: string;
  label: string; options: MultiSelectOption[]; values: string[]; onChange: (values: string[]) => void;
  searchable?: boolean; loading?: boolean; disabled?: boolean; placeholder?: string;
  renderOption?: (option: MultiSelectOption) => ReactNode; hint?: string; className?: string;
  labelPlacement?: 'inside' | 'outside' | 'hidden'; selectionMode?: 'single' | 'multiple'; clearable?: boolean;
  searchValue?: string; onSearchChange?: (value: string) => void; remoteSearch?: boolean;
};

export function MultiSelect({ id, testId, ariaInvalid, ariaDescribedBy, label, options, values, onChange, searchable = false, loading = false, disabled = false, placeholder = 'Не выбрано', renderOption, hint, className = '', labelPlacement = 'inside', selectionMode = 'multiple', clearable = true, searchValue, onSearchChange, remoteSearch = false }: SelectProps) {
  const [internalSearch, setInternalSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const menuId = useId();
  const search = searchValue ?? internalSearch;
  const setSearch = useCallback((next: string) => { if (searchValue === undefined) setInternalSearch(next); onSearchChange?.(next); }, [searchValue, onSearchChange]);
  const menuReady = Boolean(position);
  const selectedOptions = options.filter((option) => values.includes(option.id));
  const visibleOptions = useMemo(() => {
    const term = search.trim().toLocaleLowerCase('ru-RU');
    return !term || remoteSearch ? options : options.filter((option) => `${option.name} ${option.description ?? ''}`.toLocaleLowerCase('ru-RU').includes(term));
  }, [options, remoteSearch, search]);

  useEffect(() => { if (open && menuReady && searchable && !loading) searchRef.current?.focus(); }, [open, menuReady, searchable, loading]);
  useEffect(() => {
    if (!open || disabled) return;
    const updatePosition = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      if (!rect) return;
      const margin = 8;
      const gap = 5;
      const below = window.innerHeight - rect.bottom - margin - gap;
      const above = rect.top - margin - gap;
      const opensAbove = below < 280 && above > below;
      const maxHeight = Math.max(80, Math.min(320, opensAbove ? above : below));
      setPosition({ left: Math.max(margin, Math.min(rect.left, window.innerWidth - margin - Math.min(rect.width, window.innerWidth - margin * 2))), ...(opensAbove ? { bottom: window.innerHeight - rect.top + gap } : { top: rect.bottom + gap }), width: Math.min(rect.width, window.innerWidth - margin * 2), maxHeight });
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) { setOpen(false); setPosition(null); setSearch(''); }
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    document.addEventListener('scroll', updatePosition, true);
    document.addEventListener('pointerdown', onPointerDown);
    return () => { window.removeEventListener('resize', updatePosition); document.removeEventListener('scroll', updatePosition, true); document.removeEventListener('pointerdown', onPointerDown); };
  }, [open, disabled, setSearch]);

  const close = () => { setOpen(false); setPosition(null); setSearch(''); rootRef.current?.querySelector('button')?.focus(); };
  const choose = (id: string) => {
    if (selectionMode === 'single') { onChange([id]); close(); }
    else onChange(values.includes(id) ? values.filter((value) => value !== id) : [...values, id]);
  };
  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return; }
    const choices = [...(menuRef.current?.querySelectorAll<HTMLElement>('[data-select-option]') ?? [])];
    if (!choices.length) return;
    const index = choices.indexOf(document.activeElement as HTMLElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      choices[event.key === 'ArrowDown' ? (index + 1) % choices.length : (index < 0 ? choices.length - 1 : (index - 1 + choices.length) % choices.length)]?.focus();
    } else if (event.key === 'Home' && index >= 0) { event.preventDefault(); choices[0]?.focus(); }
    else if (event.key === 'End' && index >= 0) { event.preventDefault(); choices[choices.length - 1]?.focus(); }
    else if (event.key === 'Enter' && index < 0 && document.activeElement === searchRef.current) { event.preventDefault(); choices[0]?.click(); }
  };

  const select = <div className={`${styles.root} ${disabled ? styles.disabled : ''} ${className}`} ref={rootRef}>
    <button id={id} data-testid={testId} data-invalid={ariaInvalid || undefined} type="button" className={styles.trigger} aria-label={labelPlacement === 'hidden' ? `${label}: ${selectedOptions.map((option) => option.name).join(', ') || placeholder}` : labelPlacement === 'outside' ? label : undefined} aria-describedby={ariaDescribedBy} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? menuId : undefined} disabled={disabled} onClick={() => { const dialog = rootRef.current?.closest<HTMLElement>('[role="dialog"]'); setPortalHost(dialog?.parentElement ?? document.body); if (open) { setSearch(''); setPosition(null); } setOpen((current) => !current); }} onKeyDown={(event) => { if (event.key === 'Escape' && open) { event.stopPropagation(); close(); } }}>
      <span className={styles.summaryText}>{labelPlacement === 'inside' ? <strong>{label}</strong> : null}<small>{selectedOptions.length ? selectedOptions.map((option) => option.name).slice(0, 2).join(', ') + (selectedOptions.length > 2 ? ` +${selectedOptions.length - 2}` : '') : placeholder}</small></span>
      <ChevronDown size={16} fill="currentColor" aria-hidden="true" />
    </button>
    {open && position && portalHost ? createPortal(<div id={menuId} ref={menuRef} className={styles.menu} style={position} onKeyDown={onMenuKeyDown}>
      {hint ? <p className={styles.hint}>{hint}</p> : null}
      {searchable ? <div className={styles.search}><Search size={16} fill="currentColor" aria-hidden="true" /><input ref={searchRef} type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти в списке" aria-label={`Поиск в поле «${label}»`} /></div> : null}
      {selectionMode === 'multiple' && selectedOptions.length ? <div className={styles.selected}>{selectedOptions.map((option) => <button key={option.id} type="button" className={styles.chip} onClick={() => onChange(values.filter((value) => value !== option.id))} aria-label={`Убрать ${option.name} из фильтра «${label}»`}><span className={styles.chipText}>{option.name}</span><CloseSmall size={14} fill="currentColor" aria-hidden="true" /></button>)}<button type="button" className={styles.chip} onClick={() => onChange([])}>Сбросить</button></div> : null}
      {selectionMode === 'single' && clearable && values.length ? <button type="button" className={styles.clear} onClick={() => { onChange([]); close(); }}>Сбросить выбор</button> : null}
      {loading ? <p className={styles.state}>Загрузка вариантов…</p> : <div className={styles.options} role="listbox" aria-label={label} aria-multiselectable={selectionMode === 'multiple' || undefined}>
        {visibleOptions.map((option) => <button key={option.id} data-select-option type="button" role="option" aria-selected={values.includes(option.id)} className={styles.option} onClick={() => choose(option.id)}><span className={styles.optionContent}>{renderOption ? renderOption(option) : <><strong>{option.name}</strong>{option.description ? <small>{option.description}</small> : null}</>}</span>{selectionMode === 'multiple' ? <span className={`${styles.checkbox} ${values.includes(option.id) ? styles.checked : ''}`} aria-hidden="true">{values.includes(option.id) ? <CheckSmall size={14} fill="currentColor" /> : null}</span> : values.includes(option.id) ? <CheckSmall size={18} fill="currentColor" aria-hidden="true" /> : null}</button>)}
        {!visibleOptions.length ? <p className={styles.state}>{search ? 'Ничего не найдено' : 'Нет вариантов'}</p> : null}
      </div>}
    </div>, portalHost) : null}
  </div>;
  return labelPlacement === 'outside' ? <div className={styles.labeled}><span>{label}</span>{select}</div> : select;
}

export function SearchableSelect({ value, onChange, ...props }: Omit<SelectProps, 'values' | 'onChange' | 'selectionMode'> & { value: string; onChange: (value: string) => void }) {
  return <MultiSelect {...props} values={value ? [value] : []} onChange={(values) => onChange(values[0] ?? '')} selectionMode="single" searchable />;
}

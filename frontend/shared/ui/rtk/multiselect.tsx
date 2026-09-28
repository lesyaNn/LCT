'use client';

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import Search from '@atomaro/icons/24/action/Search';
import styles from './multiselect.module.css';

export interface MultiSelectOption {
  id: string;
  name: string;
  description?: string;
}

type MenuPosition = { left: number; top: number; width: number; maxHeight: number };

export function MultiSelect({ label, options, values, onChange, searchable = false, loading = false, disabled = false, placeholder = 'Не выбрано', renderOption, hint, className = '', labelPlacement = 'inside' }: { label: string; options: MultiSelectOption[]; values: string[]; onChange: (values: string[]) => void; searchable?: boolean; loading?: boolean; disabled?: boolean; placeholder?: string; renderOption?: (option: MultiSelectOption) => ReactNode; hint?: string; className?: string; labelPlacement?: 'inside' | 'outside' }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const selectedOptions = options.filter((option) => values.includes(option.id));
  const visibleOptions = useMemo(() => {
    const term = search.trim().toLocaleLowerCase('ru-RU');
    return term ? options.filter((option) => `${option.name} ${option.description ?? ''}`.toLocaleLowerCase('ru-RU').includes(term)) : options;
  }, [options, search]);

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
      const maxHeight = Math.max(80, Math.min(280, opensAbove ? above : below));
      setPosition({
        left: Math.max(margin, Math.min(rect.left, window.innerWidth - margin - Math.min(rect.width, window.innerWidth - margin * 2))),
        top: opensAbove ? rect.top - gap - maxHeight : rect.bottom + gap,
        width: Math.min(rect.width, window.innerWidth - margin * 2),
        maxHeight,
      });
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false);
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    document.addEventListener('scroll', updatePosition, true);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      window.removeEventListener('resize', updatePosition);
      document.removeEventListener('scroll', updatePosition, true);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open, disabled]);

  const select = <div className={`${styles.root} ${disabled ? styles.disabled : ''} ${className}`} ref={rootRef}>
    <button type="button" className={styles.trigger} aria-label={labelPlacement === 'outside' ? label : undefined} aria-expanded={open} aria-controls={menuId} disabled={disabled} onClick={() => { setPortalHost(rootRef.current?.closest('[role="dialog"]')?.parentElement ?? document.body); setOpen((current) => !current); }} onKeyDown={(event) => { if (event.key === 'Escape' && open) { event.stopPropagation(); setOpen(false); } }}>
      <span className={styles.summaryText}>{labelPlacement === 'inside' ? <strong>{label}</strong> : null}<small>{selectedOptions.length ? selectedOptions.map((option) => option.name).slice(0, 2).join(', ') + (selectedOptions.length > 2 ? ` +${selectedOptions.length - 2}` : '') : placeholder}</small></span>
      <ChevronDown size={16} fill="currentColor" aria-hidden="true" />
    </button>
    {open && position && portalHost ? createPortal(<div id={menuId} ref={menuRef} className={styles.menu} style={position} onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); rootRef.current?.querySelector('button')?.focus(); } }}>
      {hint ? <p className={styles.hint}>{hint}</p> : null}
      {loading ? <p className={styles.state}>Загрузка вариантов…</p> : null}
      {!loading && selectedOptions.length ? <div className={styles.selected}>{selectedOptions.map((option) => <button key={option.id} type="button" className={styles.chip} onClick={() => onChange(values.filter((value) => value !== option.id))} aria-label={`Убрать ${option.name} из фильтра «${label}»`}>{option.name}<CloseSmall size={14} fill="currentColor" aria-hidden="true" /></button>)}</div> : null}
      {!loading && searchable ? <div className={styles.search}><Search size={16} fill="currentColor" aria-hidden="true" /><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти в списке" aria-label={`Поиск в поле «${label}»`} /></div> : null}
      {!loading && visibleOptions.map((option) => <label key={option.id}><span className={styles.optionContent}>{renderOption ? renderOption(option) : <><strong>{option.name}</strong>{option.description ? <small>{option.description}</small> : null}</>}</span><input className={styles.optionCheck} type="checkbox" checked={values.includes(option.id)} onChange={(event) => onChange(event.target.checked ? [...values, option.id] : values.filter((value) => value !== option.id))} /></label>)}
      {!loading && !visibleOptions.length ? <p className={styles.state}>Нет вариантов</p> : null}
    </div>, portalHost) : null}
  </div>;
  return labelPlacement === 'outside' ? <div className={styles.labeled}><span>{label}</span>{select}</div> : select;
}

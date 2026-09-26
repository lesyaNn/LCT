'use client';

import { useId, useState, type ReactNode } from 'react';
import Filter from '@atomaro/icons/24/action/Filter';
import { Button } from './button';
import { Drawer } from './drawer';
import { ActiveFilters, type ActiveFilterItem } from './active-filters';
import styles from './filter-surface.module.css';

export function FilterSurface({ children, className, label = 'Фильтры', mobileDrawer = true }: { children: ReactNode; className?: string; label?: string; mobileDrawer?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!mobileDrawer) return <section className={[styles.root, className].filter(Boolean).join(' ')} aria-label={label}>{children}</section>;
  return <><section className={[styles.root, styles.desktop, className].filter(Boolean).join(' ')} aria-label={label}>{children}</section><Button className={styles.mobileTrigger} variant="secondary" size="s" type="button" onClick={() => setOpen(true)}><Filter size={16} fill="currentColor" />Фильтры</Button>{open ? <Drawer title="Фильтры" onClose={() => setOpen(false)}><div className={styles.mobileContent}>{children}</div><div className={styles.actions}><Button variant="primary" size="s" type="button" onClick={() => setOpen(false)}>Показать результаты</Button></div></Drawer> : null}</>;
}

/** Shared list-filter presentation. Domain controls and their state remain with the page. */
export function FilterToolbar({ label, controls, onReset, resetDisabled = false, actions, mobileCount = 0, embedded = false, collapsible = false, compact = false, activeFilters = [] }: {
  label: string;
  controls: (mobile: boolean) => ReactNode;
  onReset?: () => void;
  resetDisabled?: boolean;
  actions?: ReactNode;
  mobileCount?: number;
  embedded?: boolean;
  collapsible?: boolean;
  compact?: boolean;
  activeFilters?: ActiveFilterItem[];
}) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const panelId = useId();
  const reset = onReset && !resetDisabled ? <Button variant="ghost" size="s" type="button" onClick={onReset}>Сбросить</Button> : null;
  return <>
    <FilterSurface mobileDrawer={false} className={`${styles.desktop} ${embedded ? styles.embedded : ''}`} label={label}>
      {collapsible ? <Button variant="secondary" size="s" type="button" className={styles.collapseTrigger} aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((value) => !value)}><Filter size={16} fill="currentColor" />{expanded ? 'Скрыть фильтры' : 'Показать фильтры'}{mobileCount ? ` (${mobileCount})` : ''}</Button> : null}
      <div id={panelId} className={styles.panel} hidden={collapsible && !expanded}><div className={`${styles.desktopLayout} ${compact ? styles.compact : ''}`}><div className={styles.grid}>{controls(false)}</div>{reset || actions ? <div className={styles.desktopActions}>{reset}{actions}</div> : null}</div></div>
    </FilterSurface>
    <Button className={styles.mobileTrigger} variant="secondary" size="s" type="button" onClick={() => setOpen(true)}><Filter size={16} fill="currentColor" />Фильтры{mobileCount ? ` (${mobileCount})` : ''}</Button>
    {open ? <Drawer title="Фильтры" onClose={() => setOpen(false)}><div className={`${styles.grid} ${styles.mobileGrid}`}>{controls(true)}</div><div className={styles.actions}>{reset}{actions}<Button variant="primary" size="s" type="button" onClick={() => setOpen(false)}>Показать результаты</Button></div></Drawer> : null}
    <ActiveFilters items={activeFilters} onClearAll={onReset} />
  </>;
}

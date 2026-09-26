'use client';

import CloseSmall from '@atomaro/icons/24/navigation/CloseSmall';
import styles from './active-filters.module.css';

export interface ActiveFilterItem {
  id: string;
  label: string;
  onRemove: () => void;
}

export function ActiveFilters({ items, onClearAll }: { items: ActiveFilterItem[]; onClearAll?: () => void }) {
  if (!items.length) return null;
  return <div className={styles.root} aria-label="Активные фильтры">
    <span className={styles.title}>Активные фильтры</span>
    <div className={styles.list}>
      {items.map((item) => <button className={styles.chip} type="button" key={item.id} onClick={item.onRemove} aria-label={`Удалить фильтр «${item.label}»`}>{item.label}<CloseSmall size={14} fill="currentColor" aria-hidden="true" /></button>)}
      {onClearAll ? <button className={styles.clear} type="button" onClick={onClearAll}>Сбросить всё</button> : null}
    </div>
  </div>;
}

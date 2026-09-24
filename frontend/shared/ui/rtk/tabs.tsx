import styles from './tabs.module.css';

export interface TabItem { id: string; label: string }

export function Tabs({ items, activeId, onChange, label, prefix = 'tab' }: {
  items: readonly TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  label: string;
  prefix?: string;
}) {
  return <nav className={styles.root} aria-label={label}><div className={styles.list} role="tablist">{items.map((item) => <button className={activeId === item.id ? styles.active : styles.tab} id={`${prefix}-${item.id}`} type="button" role="tab" aria-selected={activeId === item.id} onClick={() => onChange(item.id)} key={item.id}>{item.label}</button>)}</div></nav>;
}

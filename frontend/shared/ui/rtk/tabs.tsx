import styles from './tabs.module.css';

export interface TabItem { id: string; label: string; testId?: string }

export function Tabs({ items, activeId, onChange, label, prefix = 'tab', panelPrefix, alternating = false, segmented = false }: {
  items: readonly TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  label: string;
  prefix?: string;
  panelPrefix?: string;
  alternating?: boolean;
  segmented?: boolean;
}) {
  return <nav className={`${styles.root} ${alternating ? styles.alternating : ''} ${segmented ? styles.segmented : ''}`} aria-label={label}><div className={styles.list} role="tablist">{items.map((item, index) => <button className={activeId === item.id ? styles.active : styles.tab} id={`${prefix}-${item.id}`} data-testid={item.testId} type="button" role="tab" aria-selected={activeId === item.id} aria-controls={panelPrefix ? `${panelPrefix}-${item.id}` : undefined} tabIndex={activeId === item.id ? 0 : -1} onClick={() => onChange(item.id)} onKeyDown={(event) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length;
    onChange(items[next].id);
    document.getElementById(`${prefix}-${items[next].id}`)?.focus();
  }} key={item.id}>{item.label}</button>)}</div></nav>;
}

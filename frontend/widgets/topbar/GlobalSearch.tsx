'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { apiFetch } from '@/shared/lib/api-client';
import { getVisibleNavigationItems } from '@/shared/config/navigation';
import type { AuthUser } from '@/shared/types/user';
import { Icon } from '@/shared/ui/rtk/icon';
import { Input } from '@/shared/ui/rtk/form-controls';
import styles from './global-search.module.css';

type Hit = { id: string; title: string; subtitle: string | null; university_id: string | null };
type Results = { universities: Hit[]; workflows: Hit[]; documents: Hit[]; contracts: Hit[]; products: Hit[]; responsibles: Hit[] };
type Option = { key: string; title: string; subtitle: string; href: string; icon: 'university' | 'workflow' | 'docs' | 'admin' | 'report' | 'audit' | 'dashboard' | 'api' };
const empty: Results = { universities: [], workflows: [], documents: [], contracts: [], products: [], responsibles: [] };

export function GlobalSearch({ user }: { user: AuthUser }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Results>(empty);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [active, setActive] = useState(-1);
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0 });
  const term = query.trim().toLocaleLowerCase('ru');

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setMobile(window.matchMedia("(max-width: 768px)").matches);
        setOpen(true);
        requestAnimationFrame(() => input.current?.focus());
      }
    };
    window.addEventListener('keydown', onShortcut);
    return () => window.removeEventListener('keydown', onShortcut);
  }, []);

  useEffect(() => {
    if (!open || mobile) return;
    const update = () => {
      const rect = root.current?.getBoundingClientRect();
      if (rect) setPosition({ top: rect.bottom + 8, left: rect.left, width: rect.width });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => { window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true); };
  }, [open, mobile]);

  useEffect(() => {
    if (!open || term.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError(false);
      const response = await apiFetch<Results>(`/api/v1/search?q=${encodeURIComponent(query.trim())}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setResults(response.ok ? response.data : empty);
      setError(!response.ok);
      setLoading(false);
    }, 300);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query, term, open]);

  const groups: { label: string; items: Option[] }[] = [
    { label: 'Вузы', items: results.universities.map((hit) => ({ key: `u-${hit.id}`, title: hit.title, subtitle: hit.subtitle || 'Паспорт вуза', href: `/universities/${hit.id}`, icon: 'university' })) },
    { label: 'Workflow', items: results.workflows.map((hit) => ({ key: `w-${hit.id}`, title: hit.title, subtitle: hit.subtitle || 'Workflow', href: `/workflows/${hit.id}`, icon: 'workflow' })) },
    { label: 'Документы', items: results.documents.map((hit) => ({ key: `d-${hit.id}`, title: hit.title, subtitle: hit.subtitle || 'Документ', href: `/universities/${hit.university_id}?tab=documents`, icon: 'docs' })) },
    { label: 'Договоры', items: results.contracts.map((hit) => ({ key: `c-${hit.id}`, title: hit.title, subtitle: hit.subtitle || 'Договор', href: `/universities/${hit.university_id}?tab=documents`, icon: 'docs' })) },
    { label: 'Продукты', items: results.products.map((hit) => ({ key: `p-${hit.id}-${hit.university_id}`, title: hit.title, subtitle: hit.subtitle || 'Продукт', href: `/universities/${hit.university_id}?tab=products`, icon: 'admin' })) },
    { label: 'Ответственные', items: results.responsibles.map((hit) => ({ key: `r-${hit.id}-${hit.university_id}`, title: hit.title, subtitle: hit.subtitle || 'Ответственный', href: `/universities/${hit.university_id}?tab=responsibles`, icon: 'admin' })) },
    { label: 'Разделы', items: getVisibleNavigationItems(user).filter((item) => item.label.toLocaleLowerCase('ru').includes(term)).slice(0, 6).map((item) => ({ key: `n-${item.href}`, title: item.label, subtitle: 'Раздел системы', href: item.href, icon: item.icon })) },
  ];
  const options = term.length >= 2 ? groups.flatMap((group) => group.items) : [];
  const choose = (option: Option) => {
    setOpen(false); setMobile(false); setQuery(''); setResults(empty); setActive(-1);
    router.push(option.href);
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') { setOpen(false); setMobile(false); input.current?.blur(); return; }
    if (!open) return;
    if (options.length && !loading && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      event.preventDefault();
      setActive((index) => event.key === 'ArrowDown' ? (index + 1) % options.length : (index <= 0 ? options.length - 1 : index - 1));
    }
    if (event.key === 'Enter' && options.length && !loading) { event.preventDefault(); choose(options[active >= 0 ? active : 0]); }
  };
  const dropdown = open ? <div className={`${styles.dropdown} ${mobile ? styles.mobileDropdown : ''}`} id={listId} role="listbox" aria-label="Результаты поиска" style={mobile ? undefined : { top: position.top, left: position.left, width: position.width }}>
    {term.length < 2 ? <p className={styles.message}>Введите минимум 2 символа</p>
      : loading ? <p className={styles.message} role="status">Поиск...</p>
      : error && options.length === 0 ? <p className={styles.message}>Не удалось выполнить поиск</p>
      : options.length === 0 ? <p className={styles.message}>Ничего не найдено</p>
      : groups.map((group) => group.items.length ? <div key={group.label} className={styles.group}><div className={styles.heading}>{group.label}</div>{group.items.map((option) => {
        const index = options.findIndex((item) => item.key === option.key);
        return <button type="button" role="option" aria-selected={active === index} id={`${listId}-${index}`} className={`${styles.option} ${active === index ? styles.selected : ''}`} key={option.key} onMouseEnter={() => setActive(index)} onClick={() => choose(option)}><Icon name={option.icon} size={18} /><span><strong>{option.title}</strong><small>{option.subtitle}</small></span></button>;
      })}</div> : null)}
  </div> : null;

  return <div className={`${styles.root} ${mobile ? styles.mobileOpen : ''}`} ref={root} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) window.setTimeout(() => setOpen(false), 150); }}>
    <button type="button" className={styles.mobileButton} aria-label="Открыть поиск" onClick={() => { setMobile(true); setOpen(true); requestAnimationFrame(() => input.current?.focus()); }}><span className={styles.magnifier} /></button>
    <div className={styles.field}><span className={styles.magnifier} aria-hidden="true" /><Input ref={input} type="search" aria-label="Поиск по системе" role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={listId} aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined} placeholder="Поиск по системе..." value={query} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setActive(-1); setResults(empty); setLoading(event.target.value.trim().length >= 2); }} onKeyDown={onKeyDown} /></div>
    {mobile ? <button className={styles.close} type="button" onClick={() => { setMobile(false); setOpen(false); }}>Отмена</button> : null}
    {typeof document !== 'undefined' && dropdown ? createPortal(dropdown, document.body) : null}
  </div>;
}

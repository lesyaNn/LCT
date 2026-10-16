'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Icon } from '@/shared/ui/rtk/icon';
import { Notification, notificationTarget, notificationTime, notificationsRepository, notifyInboxChanged } from '@/shared/lib/notifications-repository';
import styles from './notifications.module.css';

export function NotificationBell({ pathname }: { pathname: string }) {
  const router = useRouter();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    const result = await notificationsRepository.unreadCount();
    if (result.ok) setCount(result.data.count);
    if (open) {
      const latest = await notificationsRepository.list('all', 7);
      if (latest.ok) { setItems(latest.data.items); setError(''); }
      else setError('Не удалось загрузить уведомления.');
    }
  }, [open]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initial);
  }, [pathname, refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), 45_000);
    window.addEventListener('notifications:changed', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('notifications:changed', refresh); };
  }, [refresh]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (root.current && !root.current.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, []);

  async function openItem(item: Notification) {
    if (!item.is_read) {
      const result = await notificationsRepository.markRead(item.id);
      if (!result.ok) { setError('Не удалось отметить уведомление прочитанным.'); return; }
      setCount((value) => Math.max(0, value - 1));
      notifyInboxChanged();
    }
    setOpen(false);
    router.push(notificationTarget(item));
  }

  return <div className={styles.bellRoot} ref={root}>
    <button type="button" className={styles.bell} aria-label={count ? `Уведомления: ${count} непрочитанных` : 'Уведомления'} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((value) => !value)}>
      <Icon name="bell" size={21} />{count > 0 && <span className={styles.badge}>{count > 99 ? '99+' : count}</span>}
    </button>
    {open && <div className={styles.dropdown} role="dialog" aria-label="Последние уведомления">
      <div className={styles.dropdownHeading}><strong>Уведомления</strong><span>{count ? `${count} непрочитанных` : 'Всё прочитано'}</span></div>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {items.length ? <ul className={styles.list}>{items.map((item) => <li key={item.id}>
        <button type="button" className={`${styles.item} ${!item.is_read ? styles.unread : ''}`} onClick={() => void openItem(item)}>
          <span className={`${styles.priority} ${styles[item.priority.toLowerCase()]}`} aria-hidden="true" />
          <span><strong>{item.title}</strong><span className={styles.message}>{item.message}</span><small>{notificationTime(item.created_at)}</small></span>
        </button>
      </li>)}</ul> : !error && <p className={styles.empty}>Уведомлений пока нет.</p>}
      <Link className={styles.allLink} href="/notifications" onClick={() => setOpen(false)}>Все уведомления</Link>
    </div>}
  </div>;
}

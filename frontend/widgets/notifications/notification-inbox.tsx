'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Notification, NotificationFilter, notificationTarget, notificationTime, notificationsRepository, notifyInboxChanged } from '@/shared/lib/notifications-repository';
import styles from './notifications.module.css';

const filters: { value: NotificationFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'unread', label: 'Непрочитанные' },
  { value: 'attention', label: 'Требуют внимания' },
];
const PAGE_SIZE = 20;

export function NotificationInbox() {
  const router = useRouter();
  const [filter, setFilter] = useState<NotificationFilter>('all');
  const [page, setPage] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    const result = await notificationsRepository.list(filter, PAGE_SIZE, page * PAGE_SIZE);
    if (result.ok) { setItems(result.data.items); setTotal(result.data.total); setError(''); }
    else setError('Не удалось загрузить уведомления. Попробуйте ещё раз.');
    setLoading(false);
  }, [filter, page]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initial);
  }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), 45_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function openItem(item: Notification) {
    if (!item.is_read) {
      const result = await notificationsRepository.markRead(item.id);
      if (!result.ok) { setError('Не удалось отметить уведомление прочитанным.'); return; }
      notifyInboxChanged();
    }
    router.push(notificationTarget(item));
  }

  async function markAll() {
    const result = await notificationsRepository.markAllRead();
    if (!result.ok) { setError('Не удалось отметить уведомления прочитанными.'); return; }
    notifyInboxChanged();
    if (filter === 'unread') setPage(0);
    void refresh();
  }

  return <section className={styles.page} aria-labelledby="notifications-title">
    <div className={styles.pageHeading}><div><h1 id="notifications-title">Уведомления</h1><p>Важные события по вашей работе с ВУЗами.</p></div>
      <button type="button" className={styles.markAll} onClick={() => void markAll()}>Отметить все как прочитанные</button>
    </div>
    <div className={styles.filters} role="group" aria-label="Фильтр уведомлений">{filters.map((option) =>
      <button key={option.value} type="button" aria-pressed={filter === option.value} className={filter === option.value ? styles.activeFilter : ''}
        onClick={() => { setFilter(option.value); setPage(0); }}>{option.label}</button>)}</div>
    {error && <p className={styles.error} role="alert">{error} <button type="button" onClick={() => void refresh()}>Повторить</button></p>}
    {loading ? <p className={styles.empty} role="status">Загружаем уведомления…</p> : items.length ? <ul className={styles.inboxList}>{items.map((item) => <li key={item.id}>
      <button type="button" className={`${styles.inboxItem} ${!item.is_read ? styles.unread : ''}`} onClick={() => void openItem(item)}>
        <span className={`${styles.priority} ${styles[item.priority.toLowerCase()]}`} aria-hidden="true" />
        <span className={styles.inboxText}><strong>{item.title}</strong><span>{item.message}</span><small>{notificationTime(item.created_at)}</small></span>
        {!item.is_read && <span className={styles.newLabel}>Новое</span>}
      </button>
    </li>)}</ul> : <p className={styles.empty}>Здесь пока нет уведомлений.</p>}
    {total > PAGE_SIZE && <nav className={styles.pagination} aria-label="Страницы уведомлений">
      <button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Назад</button>
      <span>Страница {page + 1} из {Math.ceil(total / PAGE_SIZE)}</span>
      <button type="button" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((value) => value + 1)}>Далее</button>
    </nav>}
  </section>;
}

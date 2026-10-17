'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/shared/auth/AuthProvider';
import { canAccessRoute } from '@/shared/config/navigation';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { notificationTarget, notificationTime, type Notification, type NotificationFilter } from '@/shared/lib/notifications-repository';
import { useNotifications } from '@/widgets/topbar/notifications-state';
import styles from './notifications.module.css';

const filters: { value: NotificationFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'unread', label: 'Непрочитанные' },
  { value: 'attention', label: 'Требуют внимания' },
];
const PAGE_SIZE = 20;

export function NotificationInbox() {
  const router = useRouter();
  const { user } = useAuth();
  const [filter, setFilter] = useState<NotificationFilter>('all');
  const [page, setPage] = useState(0);
  const [actionError, setActionError] = useState('');
  const pendingReads = useRef(new Set<string>());
  const { items, total, unreadCount, loading, error, refresh, markRead, markAllRead, markingAll } = useNotifications({ filter, limit: PAGE_SIZE, offset: page * PAGE_SIZE });

  function openItem(item: Notification) {
    if (pendingReads.current.has(item.id)) return;
    if (!item.is_read) {
      pendingReads.current.add(item.id);
      void markRead(item.id)
        .then(() => setActionError(''))
        .catch((cause: unknown) => setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось отметить уведомление прочитанным.' }).message))
        .finally(() => pendingReads.current.delete(item.id));
    }
    const target = notificationTarget(item);
    const path = target?.split('?')[0];
    if (target && path && user && canAccessRoute(path, user)) router.push(target);
  }

  function markAll() {
    void markAllRead()
      .then(() => {
        setActionError('');
        if (filter === 'unread') setPage(0);
      })
      .catch((cause: unknown) => setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось отметить уведомления прочитанными.' }).message));
  }

  return <section className={styles.page} aria-labelledby="notifications-title">
    <div className={styles.pageHeading}><div><h1 id="notifications-title">Уведомления</h1><p>Важные события по вашей работе с ВУЗами.</p></div>
      <button type="button" className={styles.markAll} disabled={unreadCount === 0 || markingAll} onClick={markAll}>Отметить все как прочитанные</button>
    </div>
    <div className={styles.filters} role="group" aria-label="Фильтр уведомлений">{filters.map((option) =>
      <button key={option.value} type="button" aria-pressed={filter === option.value} className={filter === option.value ? styles.activeFilter : ''}
        onClick={() => { setFilter(option.value); setPage(0); }}>{option.label}</button>)}</div>
    {(error || actionError) && <p className={styles.error} role="alert">{actionError || error} <button type="button" onClick={() => { setActionError(''); void refresh(); }}>Повторить</button></p>}
    {loading ? <p className={styles.empty} role="status">Загружаем уведомления…</p> : items.length ? <ul className={styles.inboxList}>{items.map((item) => <li key={item.id}>
      <button type="button" className={`${styles.inboxItem} ${!item.is_read ? styles.unread : ''}`} onClick={() => openItem(item)}>
        <span className={`${styles.priority} ${styles[item.priority.toLowerCase()]}`} aria-hidden="true" />
        <span className={styles.inboxText}><strong>{item.title}</strong><span>{item.message}</span><small>{notificationTime(item.created_at)}</small></span>
        {!item.is_read && <span className={styles.newLabel}>Новое</span>}
      </button>
    </li>)}</ul> : !error && <p className={styles.empty}>Здесь пока нет уведомлений.</p>}
    {total > PAGE_SIZE && <nav className={styles.pagination} aria-label="Страницы уведомлений">
      <button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Назад</button>
      <span>Страница {page + 1} из {Math.ceil(total / PAGE_SIZE)}</span>
      <button type="button" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((value) => value + 1)}>Далее</button>
    </nav>}
  </section>;
}

'use client';

import { useState } from 'react';
import { PageIntro } from '@/shared/ui/page-intro';
import { Button } from '@/shared/ui/rtk/button';
import { Tabs } from '@/shared/ui/rtk/tabs';
import { EmptyState } from '@/shared/ui/empty-state';
import type { NotificationItem } from '@/shared/types/notification';
import { NotificationRow } from '@/widgets/topbar/NotificationsPopover';
import { useNotifications } from '@/widgets/topbar/notifications-state';
import styles from './notifications-page.module.css';

type Filter = 'all' | 'unread';

export default function NotificationsPage() {
  const { notifications, unreadCount, markAllRead } = useNotifications();
  const [filter, setFilter] = useState<Filter>('all');
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  const groups: { label: string; items: NotificationItem[] }[] = [
    { label: 'Сегодня', items: [] },
    { label: 'Вчера', items: [] },
    { label: 'Ранее', items: [] },
  ];

  for (const notification of notifications) {
    if (filter === 'unread' && notification.read) continue;
    const date = new Date(notification.createdAt).toDateString();
    const group = date === today.toDateString() ? groups[0] : date === yesterday.toDateString() ? groups[1] : groups[2];
    group.items.push(notification);
  }

  const hasItems = groups.some((group) => group.items.length > 0);

  return <div className={styles.page}>
    <PageIntro title="Уведомления" description="События и изменения в CRM. Сейчас показаны демонстрационные уведомления." />
    <div className={styles.toolbar}>
      <Tabs
        items={[{ id: 'all', label: 'Все' }, { id: 'unread', label: `Непрочитанные${unreadCount ? ` (${unreadCount})` : ''}` }]}
        activeId={filter}
        onChange={(id) => setFilter(id as Filter)}
        label="Фильтр уведомлений"
        prefix="notifications-filter"
      />
      <Button type="button" variant="ghost" size="s" disabled={unreadCount === 0} onClick={markAllRead}>Отметить все как прочитанные</Button>
    </div>
    <div role="tabpanel" aria-labelledby={`notifications-filter-${filter}`} className={styles.results}>
      {hasItems ? groups.filter((group) => group.items.length > 0).map((group) => <section className={styles.group} aria-label={group.label} key={group.label}>
        <h2>{group.label}</h2>
        <ul className={styles.list}>{group.items.sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((notification) => <NotificationRow key={notification.id} notification={notification} variant="page" />)}</ul>
      </section>) : <EmptyState title={filter === 'unread' ? 'Непрочитанных уведомлений нет' : 'Уведомлений пока нет'} description={filter === 'unread' ? 'Новые уведомления появятся здесь.' : 'События появятся здесь, когда они будут доступны.'} />}
    </div>
  </div>;
}

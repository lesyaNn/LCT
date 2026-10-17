import { forwardRef, type ToggleEventHandler } from 'react';
import Link from 'next/link';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import CheckLarge from '@atomaro/icons/24/navigation/CheckLarge';
import TimeStroke from '@atomaro/icons/24/alert/TimeStroke';
import Message from '@atomaro/icons/24/communication/Message';
import { formatRelativeDateRu } from '@/shared/lib/formatters';
import { Button } from '@/shared/ui/rtk/button';
import { Icon } from '@/shared/ui/rtk/icon';
import type { NotificationItem, NotificationType } from '@/shared/types/notification';
import styles from './notifications.module.css';

const icons: Record<NotificationType, React.ReactNode> = {
  report: <DocumentText size={24} fill="currentColor" />,
  workflow: <Icon name="workflow" size={25} />,
  stage: <span className={styles.stageCheck}><CheckLarge size={15} fill="currentColor" /></span>,
  license: <TimeStroke size={25} fill="currentColor" />,
  comment: <Message size={24} fill="currentColor" />,
};

export function NotificationRow({ notification, onOpen, variant = 'popover' }: { notification: NotificationItem; onOpen: (notification: NotificationItem) => void; variant?: 'popover' | 'page' }) {
  const content = <>
    <span className={styles.unreadSlot}>{notification.read ? null : <span className={styles.unreadDot} />}</span>
    <span className={`${styles.iconCircle} ${styles[notification.type]}`} aria-hidden="true">{icons[notification.type]}</span>
    <span className={styles.itemContent}>
      <span className={styles.itemHeading}>
        <strong>{notification.title}</strong>
        <time dateTime={notification.createdAt}>{formatRelativeDateRu(notification.createdAt, undefined, 'compact')}</time>
      </span>
      <span className={styles.description}>{notification.description}</span>
    </span>
  </>;

  return <li className={`${styles.item} ${notification.read ? '' : styles.unreadItem} ${variant === 'page' ? styles.pageItem : ''}`}>
    <button className={styles.itemInner} type="button" onClick={() => onOpen(notification)}>{content}</button>
  </li>;
}

interface NotificationsPopoverProps {
  id: string;
  notifications: NotificationItem[];
  unreadCount: number;
  onMarkAllRead: () => void;
  onOpenNotification: (notification: NotificationItem) => void;
  onRetry: () => void;
  onClose: () => void;
  onToggle: ToggleEventHandler<HTMLDivElement>;
  loading: boolean;
  error: string;
  markingAll: boolean;
}

export const NotificationsPopover = forwardRef<HTMLDivElement, NotificationsPopoverProps>(function NotificationsPopover({ id, notifications, unreadCount, onMarkAllRead, onOpenNotification, onRetry, onClose, onToggle, loading, error, markingAll }, ref) {
  return <div id={id} ref={ref} popover="auto" tabIndex={-1} className={styles.panel} role="dialog" aria-labelledby={`${id}-title`} onToggle={onToggle}>
    <div className={styles.heading}>
      <div className={styles.headingTitle}>
        <h2 id={`${id}-title`}>Уведомления</h2>
        {unreadCount > 0 ? <span className={styles.headingBadge} aria-label={`Непрочитанных: ${unreadCount}`}>{unreadCount}</span> : null}
      </div>
      <Button type="button" variant="ghost" size="s" className={styles.markAll} disabled={unreadCount === 0 || markingAll} onClick={onMarkAllRead}>Отметить все как прочитанные</Button>
    </div>
    <ul className={styles.list} aria-label="Список уведомлений">
      {notifications.map((notification) => <NotificationRow key={notification.id} notification={notification} onOpen={onOpenNotification} />)}
    </ul>
    {loading && !notifications.length ? <p className={styles.empty} role="status">Загружаем уведомления…</p> : null}
    {error ? <p className={styles.empty} role="alert">{error} <button className={styles.retry} type="button" onClick={onRetry}>Повторить</button></p> : null}
    {!loading && !error && notifications.length === 0 ? <p className={styles.empty}>Уведомлений пока нет</p> : null}
    <Link className={styles.footer} href="/notifications" onClick={onClose}>
      <span>Все уведомления</span><Icon name="chevron-right" size={22} />
    </Link>
  </div>;
});

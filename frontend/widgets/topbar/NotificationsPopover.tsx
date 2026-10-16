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
  report: <DocumentText size={30} fill="currentColor" />,
  workflow: <Icon name="workflow" size={31} />,
  stage: <span className={styles.stageCheck}><CheckLarge size={19} fill="currentColor" /></span>,
  license: <TimeStroke size={31} fill="currentColor" />,
  comment: <Message size={30} fill="currentColor" />,
};

function NotificationRow({ notification }: { notification: NotificationItem }) {
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

  return <li className={styles.item}>
    {notification.target ? <Link className={styles.itemInner} href={notification.target}>{content}</Link> : <div className={styles.itemInner}>{content}</div>}
  </li>;
}

interface NotificationsPopoverProps {
  id: string;
  notifications: NotificationItem[];
  unreadCount: number;
  onMarkAllRead: () => void;
  onToggle: ToggleEventHandler<HTMLDivElement>;
}

export const NotificationsPopover = forwardRef<HTMLDivElement, NotificationsPopoverProps>(function NotificationsPopover({ id, notifications, unreadCount, onMarkAllRead, onToggle }, ref) {
  return <div id={id} ref={ref} popover="auto" tabIndex={-1} className={styles.panel} role="dialog" aria-labelledby={`${id}-title`} onToggle={onToggle}>
    <div className={styles.heading}>
      <div className={styles.headingTitle}>
        <h2 id={`${id}-title`}>Уведомления</h2>
        {unreadCount > 0 ? <span className={styles.headingBadge} aria-label={`Непрочитанных: ${unreadCount}`}>{unreadCount}</span> : null}
      </div>
      <Button type="button" variant="ghost" size="s" className={styles.markAll} disabled={unreadCount === 0} onClick={onMarkAllRead}>Отметить все как прочитанные</Button>
    </div>
    <ul className={styles.list} aria-label="Список уведомлений">
      {notifications.map((notification) => <NotificationRow key={notification.id} notification={notification} />)}
    </ul>
    {notifications.length === 0 ? <p className={styles.empty}>Уведомлений пока нет</p> : null}
    <div className={styles.footer} aria-disabled="true" title="Раздел уведомлений пока недоступен">
      <span>Все уведомления</span><Icon name="chevron-right" size={22} />
    </div>
  </div>;
});

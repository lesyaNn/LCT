'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/shared/auth/AuthProvider';
import { canAccessRoute } from '@/shared/config/navigation';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { notificationPresentation } from '@/shared/lib/notifications-repository';
import type { NotificationItem } from '@/shared/types/notification';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { NotificationsPopover } from './NotificationsPopover';
import { useNotifications } from './notifications-state';
import styles from './notifications.module.css';

export function NotificationsButton() {
  const { user } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [actionError, setActionError] = useState('');
  const { items, unreadCount, loading, error, refresh, markRead, markAllRead, markingAll } = useNotifications({ enabled: open });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const pendingReads = useRef(new Set<string>());
  const panelId = useId();
  const notifications = items.map(notificationPresentation);

  // The native popover supplies light dismiss, Escape and top-layer rendering.
  const positionPanel = useCallback(() => {
    const trigger = triggerRef.current?.getBoundingClientRect();
    const panel = panelRef.current;
    if (!trigger || !panel) return;
    const margin = 12;
    const width = Math.min(440, window.innerWidth - margin * 2);
    const right = Math.max(margin, Math.min(window.innerWidth - trigger.right, window.innerWidth - width - margin));
    panel.style.top = `${trigger.bottom + 8}px`;
    panel.style.right = `${right}px`;
    panel.style.maxHeight = `${Math.max(140, Math.min(480, window.innerHeight - trigger.bottom - 20))}px`;
  }, []);

  useEffect(() => {
    if (!open) return;
    window.addEventListener('resize', positionPanel);
    window.addEventListener('scroll', positionPanel, true);
    return () => {
      window.removeEventListener('resize', positionPanel);
      window.removeEventListener('scroll', positionPanel, true);
    };
  }, [open, positionPanel]);

  function openNotification(notification: NotificationItem) {
    if (pendingReads.current.has(notification.id)) return;
    if (!notification.read) {
      pendingReads.current.add(notification.id);
      void markRead(notification.id)
        .then(() => setActionError(''))
        .catch((cause: unknown) => setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось отметить уведомление прочитанным.' }).message))
        .finally(() => pendingReads.current.delete(notification.id));
    }
    const path = notification.target?.split('?')[0];
    if (notification.target && path && user && canAccessRoute(path, user)) {
      panelRef.current?.hidePopover();
      router.push(notification.target);
    }
  }

  function markAll() {
    void markAllRead()
      .then(() => { setActionError(''); requestAnimationFrame(() => panelRef.current?.focus()); })
      .catch((cause: unknown) => setActionError(normalizeApiError(cause, { fallbackMessage: 'Не удалось отметить уведомления прочитанными.' }).message));
  }

  return <>
    <span ref={triggerRef} className={styles.triggerWrap}>
      <IconButton
        icon={<><Icon name="bell" size={22} />{unreadCount > 0 ? <span className={styles.triggerBadge} aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span> : null}</>}
        label={unreadCount > 0 ? `Уведомления, непрочитанных: ${unreadCount}` : 'Уведомления'}
        aria-controls={panelId}
        aria-expanded={open}
        aria-haspopup="dialog"
        popoverTarget={panelId}
        className={styles.trigger}
        onClick={positionPanel}
      />
    </span>
    <NotificationsPopover
      id={panelId}
      ref={panelRef}
      notifications={notifications}
      unreadCount={unreadCount}
      loading={loading}
      error={actionError || error}
      markingAll={markingAll}
      onOpenNotification={openNotification}
      onRetry={() => { setActionError(''); void refresh(); }}
      onToggle={(event) => {
        const isOpen = event.currentTarget.matches(':popover-open');
        setOpen(isOpen);
        if (isOpen) panelRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
      }}
      onMarkAllRead={markAll}
      onClose={() => panelRef.current?.hidePopover()}
    />
  </>;
}

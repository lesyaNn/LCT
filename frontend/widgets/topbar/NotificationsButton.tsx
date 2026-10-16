'use client';

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { NotificationsPopover } from './NotificationsPopover';
import { useNotifications } from './notifications-state';
import styles from './notifications.module.css';

export function NotificationsButton() {
  const { notifications, unreadCount, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

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

  return <>
    <span ref={triggerRef} className={styles.triggerWrap}>
      <IconButton
        icon={<><Icon name="bell" size={22} />{unreadCount > 0 ? <span className={styles.triggerBadge} aria-hidden="true">{unreadCount}</span> : null}</>}
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
      onToggle={(event) => {
        const isOpen = event.currentTarget.matches(':popover-open');
        setOpen(isOpen);
        if (isOpen) panelRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
      }}
      onMarkAllRead={() => {
        markAllRead();
        requestAnimationFrame(() => panelRef.current?.focus());
      }}
      onClose={() => panelRef.current?.hidePopover()}
    />
  </>;
}

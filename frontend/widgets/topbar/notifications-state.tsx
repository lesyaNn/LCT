'use client';

import { createContext, useContext, useState, useSyncExternalStore, type ReactNode } from 'react';
import type { NotificationItem } from '@/shared/types/notification';
import { createDemoNotifications } from './notification-demo';

interface NotificationsState {
  notifications: NotificationItem[];
  unreadCount: number;
  markAllRead: () => void;
}

const NotificationsContext = createContext<NotificationsState | null>(null);
// Demo timestamps depend on the current time, so show them after hydration.
const subscribeToHydration = () => () => {};

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false);
  const [items, setItems] = useState<NotificationItem[]>(createDemoNotifications);
  const notifications = hydrated ? items : [];
  const unreadCount = notifications.filter((item) => !item.read).length;

  const markAllRead = () => {
    setItems((current) => current.map((item) => item.read ? item : { ...item, read: true }));
  };

  return <NotificationsContext.Provider value={{ notifications, unreadCount, markAllRead }}>{children}</NotificationsContext.Provider>;
}

export function useNotifications() {
  const state = useContext(NotificationsContext);
  if (!state) throw new Error('useNotifications must be used within NotificationsProvider');
  return state;
}

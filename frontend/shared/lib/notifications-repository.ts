import { apiFetch } from './api-client';

export type Notification = {
  id: string;
  type: string;
  priority: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  message: string;
  entity_type: string;
  entity_id: string;
  university_id: string | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
};

export type NotificationFilter = 'all' | 'unread' | 'attention';
export type NotificationPage = { items: Notification[]; total: number; limit: number; offset: number };

export const notificationsRepository = {
  list: (filter: NotificationFilter = 'all', limit = 20, offset = 0) =>
    apiFetch<NotificationPage>(`/api/v1/notifications?filter=${filter}&limit=${limit}&offset=${offset}`),
  unreadCount: () => apiFetch<{ count: number }>('/api/v1/notifications/unread-count'),
  markRead: (id: string) => apiFetch<void>(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' }),
  markAllRead: () => apiFetch<{ updated: number }>('/api/v1/notifications/read-all', { method: 'POST' }),
};

export function notificationTarget(item: Notification): string {
  if (item.entity_type === 'workflow') return `/workflows/${encodeURIComponent(item.entity_id)}`;
  if (item.entity_type === 'university') return `/universities/${encodeURIComponent(item.entity_id)}`;
  if (item.entity_type === 'contract' || item.entity_type === 'license') {
    return item.university_id ? `/universities/${encodeURIComponent(item.university_id)}?tab=licenses` : '/universities';
  }
  if (item.entity_type === 'import_job') return `/admin/import?job=${encodeURIComponent(item.entity_id)}`;
  return '/notifications';
}

export function notificationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export function notifyInboxChanged() {
  window.dispatchEvent(new Event('notifications:changed'));
}

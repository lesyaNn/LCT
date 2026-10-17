import { apiFetch } from './api-client';
import type { NotificationItem, NotificationType } from '@/shared/types/notification';

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
  list: (filter: NotificationFilter = 'all', limit = 20, offset = 0, signal?: AbortSignal) =>
    apiFetch<NotificationPage>(`/api/v1/notifications?filter=${filter}&limit=${limit}&offset=${offset}`, { signal }),
  unreadCount: (signal?: AbortSignal) => apiFetch<{ count: number }>('/api/v1/notifications/unread-count', { signal }),
  markRead: (id: string) => apiFetch<void>(`/api/v1/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' }),
  markAllRead: () => apiFetch<{ updated: number }>('/api/v1/notifications/read-all', { method: 'POST' }),
};

export function notificationTarget(item: Notification): string | null {
  if (item.entity_type === 'workflow' && item.entity_id) return `/workflows/${encodeURIComponent(item.entity_id)}`;
  if (item.entity_type === 'university' && item.entity_id) return `/universities/${encodeURIComponent(item.entity_id)}`;
  if (item.entity_type === 'contract' && item.university_id) return `/universities/${encodeURIComponent(item.university_id)}?tab=documents`;
  if (item.entity_type === 'license' && item.university_id) return `/universities/${encodeURIComponent(item.university_id)}?tab=licenses`;
  if (item.entity_type === 'import_job') return '/admin/import';
  return null;
}

const presentationTypes: Record<string, NotificationType> = {
  assignment: 'workflow',
  workflow_stage_changed: 'stage',
  workflow_rollback: 'workflow',
  overdue: 'stage',
  deadline_approaching: 'stage',
  contract_expiry: 'license',
  license_expiry: 'license',
  import_error: 'report',
};

export function notificationPresentation(item: Notification): NotificationItem {
  return {
    id: item.id,
    type: presentationTypes[item.type] ?? 'comment',
    title: item.title,
    description: item.message,
    createdAt: item.created_at,
    read: item.is_read,
    target: notificationTarget(item) ?? undefined,
  };
}

export function notificationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

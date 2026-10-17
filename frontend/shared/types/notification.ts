export type NotificationType = 'report' | 'workflow' | 'stage' | 'license' | 'comment';

export interface NotificationItem {
  id: string;
  type: NotificationType;
  title: string;
  description: string;
  createdAt: string;
  read: boolean;
  target?: string;
}

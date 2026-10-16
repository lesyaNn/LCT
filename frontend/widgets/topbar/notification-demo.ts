// Temporary display fixtures. Replace this source when real notifications are available.
import type { NotificationItem } from '@/shared/types/notification';

export function createDemoNotifications(now = new Date()): NotificationItem[] {
  const minutesAgo = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  yesterday.setHours(16, 20, 0, 0);

  return [
    { id: 'demo-report', type: 'report', title: 'Сформирован отчет «Сводка по вузам»', description: 'Отчет готов и доступен для скачивания.', createdAt: minutesAgo(5), read: false },
    { id: 'demo-workflow', type: 'workflow', title: 'Изменён workflow для программы DevOps', description: 'Высокий приоритет этапа согласования.', createdAt: minutesAgo(27), read: false },
    { id: 'demo-stage', type: 'stage', title: 'Завершён этап «Подписание документов»', description: 'По вузу МГТУ им. Н.Э. Баумана', createdAt: minutesAgo(60), read: false },
    { id: 'demo-license', type: 'license', title: 'Истекает лицензия через 7 дней', description: 'Лицензия для 3 пользователей (ВШЭ).', createdAt: minutesAgo(180), read: true },
    { id: 'demo-comment', type: 'comment', title: 'Добавлен комментарий к статусу взаимодействия', description: 'Пользователь Иванова А.С. оставил комментарий.', createdAt: yesterday.toISOString(), read: true },
  ];
}

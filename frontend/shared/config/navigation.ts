import type { NavigationItem } from '@/shared/types/navigation';
import { hasPermission } from '@/shared/lib/access-control';
import type { AuthUser } from '@/shared/types/user';

export const navigationItems: NavigationItem[] = [
  { label: 'Обзор', href: '/dashboard', icon: 'dashboard', requiredPermission: 'analytics.read' },
  { label: 'ВУЗы', href: '/universities', icon: 'university', requiredPermission: 'university.read' },
  { label: 'Workflow', href: '/workflows', icon: 'workflow', requiredPermission: 'workflow.read' },
  { label: 'Отчёты', href: '/reports', icon: 'report', requiredPermission: 'reports.read' },
  { label: 'Аудит', href: '/audit', icon: 'audit', requiredPermission: 'audit.read' },
  { label: 'Администрирование', href: '/admin', icon: 'admin', requiredPermission: 'admin.users' },
  { label: 'Пользователи и права', href: '/admin/users', icon: 'admin', requiredPermission: 'admin.users' },
  { label: 'Управление каталогами', href: '/admin/catalogs', icon: 'admin', requiredPermission: 'university.edit' },
  { label: 'Импорт каталогов', href: '/admin/import', icon: 'admin', requiredPermission: 'import.write' },
  { label: 'Шаблоны Workflow', href: '/admin/workflow/templates', icon: 'workflow', requiredPermission: 'workflow_template.manage' },
  { label: 'Тестирование API', href: '/api-testing', icon: 'api', requiredPermission: 'admin.settings' },
  { label: 'Документация', href: '/docs', icon: 'docs' },
];

export const routeLabels: Record<string, string> = {
  dashboard: 'Обзор',
  notifications: 'Уведомления',
  universities: 'ВУЗы',
  workflows: 'Workflow',
  reports: 'Отчёты',
  audit: 'Аудит',
  admin: 'Администрирование',
  users: 'Пользователи и права',
  catalogs: 'Управление каталогами',
  docs: 'Документация',
  'api-testing': 'Тестирование API',
};

export const detailRouteLabels: Record<string, string> = {
  universities: 'Университет',
  workflows: 'Взаимодействие',
};

function canAccessNavigationItem(item: NavigationItem, user: AuthUser): boolean {
  return !item.requiredPermission || hasPermission(user, item.requiredPermission);
}

export function getVisibleNavigationItems(user: AuthUser): NavigationItem[] {
  return navigationItems.filter((item) => canAccessNavigationItem(item, user));
}

export function canAccessRoute(pathname: string, user: AuthUser): boolean {
  const path = pathname === '/' ? '/dashboard' : pathname.replace(/\/$/, '');
  const rule = [...navigationItems]
    .sort((left, right) => right.href.length - left.href.length)
    .find((item) => path === item.href || path.startsWith(`${item.href}/`));

  return !rule || canAccessNavigationItem(rule, user);
}

import type { NavigationItem } from '@/shared/types/navigation';
import type { UserRole } from '@/shared/types/user';

export const navigationItems: NavigationItem[] = [
  { label: 'Обзор', href: '/dashboard', icon: 'dashboard', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'ВУЗы', href: '/universities', icon: 'university', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Преподаватели', href: '/teachers', icon: 'teacher', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Workflow', href: '/workflows', icon: 'workflow', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Отчёты', href: '/reports', icon: 'report', allowedRoles: ['manager', 'admin'] },
  { label: 'Аудит', href: '/audit', icon: 'audit', allowedRoles: ['manager', 'admin'] },
  { label: 'Администрирование', href: '/admin', icon: 'admin', allowedRoles: ['admin'] },
  { label: 'Пользователи и права', href: '/admin/users', icon: 'admin', allowedRoles: ['admin'] },
  { label: 'Импорт каталогов', href: '/admin/import', icon: 'admin', allowedRoles: ['manager', 'admin'] },
  { label: 'Документация', href: '/docs', icon: 'docs', allowedRoles: ['user', 'manager', 'admin'] },
];

export const routeLabels: Record<string, string> = {
  dashboard: 'Обзор',
  universities: 'ВУЗы',
  teachers: 'Преподаватели',
  workflows: 'Workflow',
  reports: 'Отчёты',
  audit: 'Аудит',
  admin: 'Администрирование',
  users: 'Пользователи и права',
  docs: 'Документация',
};

export const detailRouteLabels: Record<string, string> = {
  universities: 'Университет',
  teachers: 'Преподаватель',
  workflows: 'Взаимодействие',
};

export function getVisibleNavigationItems(role: UserRole): NavigationItem[] {
  return navigationItems.filter((item) => !item.allowedRoles || item.allowedRoles.includes(role));
}

export function canAccessRoute(pathname: string, role: UserRole): boolean {
  const path = pathname === '/' ? '/dashboard' : pathname.replace(/\/$/, '');
  const rule = [...navigationItems]
    .sort((left, right) => right.href.length - left.href.length)
    .find((item) => path === item.href || path.startsWith(`${item.href}/`));

  return !rule || !rule.allowedRoles || rule.allowedRoles.includes(role);
}

import type { NavigationItem } from '@/shared/types/navigation';
import type { UserRole } from '@/shared/types/user';

export const navigationItems: NavigationItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: 'dashboard', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'ВУЗы', href: '/universities', icon: 'university', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Преподаватели', href: '/teachers', icon: 'teacher', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Workflow', href: '/workflows', icon: 'workflow', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Отчёты', href: '/reports', icon: 'report', allowedRoles: ['user', 'manager', 'admin'] },
  { label: 'Аудит', href: '/audit', icon: 'audit', allowedRoles: ['manager', 'admin'] },
  { label: 'Администрирование', href: '/admin', icon: 'admin', allowedRoles: ['admin'] },
  { label: 'Документация', href: '/docs', icon: 'docs', allowedRoles: ['user', 'manager', 'admin'] },
];

export const routeLabels: Record<string, string> = {
  dashboard: 'Dashboard',
  universities: 'ВУЗы',
  teachers: 'Преподаватели',
  workflows: 'Workflow',
  reports: 'Отчёты',
  audit: 'Аудит',
  admin: 'Администрирование',
  docs: 'Документация',
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

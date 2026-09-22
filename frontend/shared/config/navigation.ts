import type { NavigationItem, UserRole } from '@/shared/types/navigation';

export const navigationItems: NavigationItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: 'dashboard' },
  { label: 'ВУЗы', href: '/universities', icon: 'university' },
  { label: 'Преподаватели', href: '/teachers', icon: 'teacher' },
  { label: 'Workflow', href: '/workflows', icon: 'workflow' },
  { label: 'Отчёты', href: '/reports', icon: 'report' },
  { label: 'Аудит', href: '/audit', icon: 'audit' },
  { label: 'Администрирование', href: '/admin', icon: 'admin', roles: ['admin'] },
  { label: 'Документация', href: '/docs', icon: 'docs' },
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
  return navigationItems.filter((item) => !item.roles || item.roles.includes(role));
}

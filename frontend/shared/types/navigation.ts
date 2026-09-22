import type { UserRole } from './user';

export type IconName =
  | 'dashboard'
  | 'university'
  | 'teacher'
  | 'workflow'
  | 'report'
  | 'audit'
  | 'admin'
  | 'docs';

export interface NavigationItem {
  label: string;
  href: string;
  icon: IconName;
  allowedRoles?: UserRole[];
}

export interface BreadcrumbEntry {
  label: string;
  href?: string;
}

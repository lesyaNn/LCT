export type UserRole = 'admin' | 'manager' | 'viewer';

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
  roles?: UserRole[];
}

export interface BreadcrumbEntry {
  label: string;
  href?: string;
}

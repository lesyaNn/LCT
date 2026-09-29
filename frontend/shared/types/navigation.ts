export type IconName =
  | 'dashboard'
  | 'university'
  | 'workflow'
  | 'report'
  | 'audit'
  | 'admin'
  | 'docs'
  | 'api';

export interface NavigationItem {
  label: string;
  href: string;
  icon: IconName;
  requiredPermission?: string;
}

export interface BreadcrumbEntry {
  label: string;
  href?: string;
}

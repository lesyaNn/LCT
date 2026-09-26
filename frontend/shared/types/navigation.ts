export type IconName =
  | 'dashboard'
  | 'university'
  | 'workflow'
  | 'report'
  | 'audit'
  | 'admin'
  | 'docs';

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

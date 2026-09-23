'use client';

import Link from 'next/link';
import { detailRouteLabels, routeLabels } from '@/shared/config/navigation';
import type { BreadcrumbEntry } from '@/shared/types/navigation';
import { Icon } from '@/shared/ui/rtk/icon';
import styles from './breadcrumbs.module.css';

function getBreadcrumbs(pathname: string): BreadcrumbEntry[] {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [{ label: 'Обзор' }];

  if (segments[0] === 'admin' && segments[1] === 'workflow' && segments[2] === 'templates') {
    const entries: BreadcrumbEntry[] = [
      { label: 'Администрирование', href: '/admin' },
      { label: 'Шаблоны Workflow', href: segments.length > 3 ? '/admin/workflow/templates' : undefined },
    ];
    if (segments.length > 3) entries.push({ label: 'Редактор шаблона' });
    return entries;
  }

  return segments.map((segment, index) => ({
    label: routeLabels[segment]
      ?? (index === segments.length - 1 ? detailRouteLabels[segments[index - 1]] ?? 'Детали' : 'Раздел'),
    href: index < segments.length - 1 ? `/${segments.slice(0, index + 1).join('/')}` : undefined,
  }));
}

export function Breadcrumbs({ pathname }: { pathname: string }) {
  const entries = getBreadcrumbs(pathname);

  return (
    <nav className={styles.breadcrumbs} aria-label="Хлебные крошки">
      {entries.map((entry, index) => (
        <span className={styles.entry} key={`${entry.label}-${index}`}>
          {index > 0 && <Icon name="chevron-right" size={14} />}
          {entry.href ? <Link href={entry.href}>{entry.label}</Link> : <span aria-current="page">{entry.label}</span>}
        </span>
      ))}
    </nav>
  );
}

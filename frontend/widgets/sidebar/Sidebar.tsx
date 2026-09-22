'use client';

import Link from 'next/link';
import { getVisibleNavigationItems } from '@/shared/config/navigation';
import type { UserRole } from '@/shared/types/user';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import styles from './sidebar.module.css';

interface SidebarProps {
  role: UserRole;
  pathname: string;
  collapsed: boolean;
  mobileOpen?: boolean;
  onToggleCollapse?: () => void;
  onCloseMobile?: () => void;
}

export function Sidebar({ role, pathname, collapsed, mobileOpen = false, onToggleCollapse, onCloseMobile }: SidebarProps) {
  const items = getVisibleNavigationItems(role);

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${mobileOpen ? styles.mobileOpen : ''}`} aria-label="Основная навигация">
      <div className={styles.brand}>
        <span className={styles.brandMark} aria-hidden="true">РТ</span>
        {(!collapsed || mobileOpen) && <span className={styles.brandName}>ИТ Школа РТК</span>}
        {mobileOpen && <IconButton icon="close" label="Закрыть меню" className={styles.mobileClose} autoFocus onClick={onCloseMobile} />}
      </div>

      <nav className={styles.nav}>
        <p className={styles.sectionLabel}>{(!collapsed || mobileOpen) && 'Рабочая область'}</p>
        {items.map((item) => {
          const active = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(`${item.href}/`));
          return (
            <Link
              className={`${styles.navItem} ${active ? styles.active : ''}`}
              href={item.href}
              key={item.href}
              onClick={onCloseMobile}
              title={collapsed ? item.label : undefined}
              aria-current={active ? 'page' : undefined}
            >
              <Icon name={item.icon} size={20} />
              {(!collapsed || mobileOpen) && <span>{item.label}</span>}
              {active && <span className={styles.activeMarker} aria-hidden="true" />}
            </Link>
          );
        })}
      </nav>

      <div className={styles.bottom}>
        {(!collapsed || mobileOpen) && <p className={styles.version}>CRM v0.1 · mock frontend</p>}
        {onToggleCollapse && <IconButton icon="chevron-right" label={collapsed ? 'Развернуть меню' : 'Свернуть меню'} className={`${styles.collapseButton} ${collapsed ? styles.collapseButtonRotated : ''}`} onClick={onToggleCollapse} />}
      </div>
    </aside>
  );
}

'use client';

import Link from 'next/link';
import { getVisibleNavigationItems } from '@/shared/config/navigation';
import type { UserRole } from '@/shared/types/user';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Drawer } from '@/shared/ui/rtk/drawer';
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
  if (mobileOpen) {
    return (
      <Drawer title="Основная навигация" closeLabel="Закрыть меню" side="left" onClose={onCloseMobile ?? (() => undefined)}>
        <SidebarContent role={role} pathname={pathname} collapsed={false} mobile onCloseMobile={onCloseMobile} />
      </Drawer>
    );
  }

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`} aria-label="Основная навигация">
      <SidebarContent role={role} pathname={pathname} collapsed={collapsed} onToggleCollapse={onToggleCollapse} />
    </aside>
  );
}

function SidebarContent({ role, pathname, collapsed, mobile = false, onToggleCollapse, onCloseMobile }: SidebarProps & { mobile?: boolean }) {
  const items = getVisibleNavigationItems(role);

  return (
    <div className={mobile ? styles.mobileDrawerContent : undefined}>
      <div className={styles.brand}>
        <span className={styles.brandMark} aria-hidden="true">РТ</span>
        {(!collapsed || mobile) && <span className={styles.brandName}>ИТ Школа РТК</span>}
      </div>

      <nav className={styles.nav}>
        <p className={styles.sectionLabel}>{(!collapsed || mobile) && 'Рабочая область'}</p>
        {items.map((item) => {
          const active = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(`${item.href}/`));
          return (
            <Link
              className={`${styles.navItem} ${active ? styles.active : ''}`}
              href={item.href}
              key={item.href}
              onClick={mobile ? onCloseMobile : undefined}
              title={collapsed && !mobile ? item.label : undefined}
              aria-current={active ? 'page' : undefined}
            >
              <Icon name={item.icon} size={20} />
              {(!collapsed || mobile) && <span>{item.label}</span>}
              {active && <span className={styles.activeMarker} aria-hidden="true" />}
            </Link>
          );
        })}
      </nav>

      <div className={styles.bottom}>
        {(!collapsed || mobile) && <p className={styles.version}>CRM v0.1 · mock frontend</p>}
        {!mobile && onToggleCollapse && <IconButton icon="chevron-right" label={collapsed ? 'Развернуть меню' : 'Свернуть меню'} className={`${styles.collapseButton} ${collapsed ? styles.collapseButtonRotated : ''}`} onClick={onToggleCollapse} />}
      </div>
    </div>
  );
}

'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useState } from 'react';
import { getVisibleNavigationItems } from '@/shared/config/navigation';
import type { AuthUser } from '@/shared/types/user';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Drawer } from '@/shared/ui/rtk/drawer';
import styles from './sidebar.module.css';

interface SidebarProps {
  user: AuthUser;
  pathname: string;
  collapsed: boolean;
  mobileOpen?: boolean;
  onToggleCollapse?: () => void;
  onCloseMobile?: () => void;
}

export function Sidebar({ user, pathname, collapsed, mobileOpen = false, onToggleCollapse, onCloseMobile }: SidebarProps) {
  if (mobileOpen) {
    return (
      <Drawer title="Основная навигация" closeLabel="Закрыть меню" side="left" onClose={onCloseMobile ?? (() => undefined)}>
        <SidebarContent user={user} pathname={pathname} collapsed={false} mobile onCloseMobile={onCloseMobile} />
      </Drawer>
    );
  }

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`} aria-label="Основная навигация">
      <SidebarContent user={user} pathname={pathname} collapsed={collapsed} onToggleCollapse={onToggleCollapse} />
    </aside>
  );
}

function SidebarContent({ user, pathname, collapsed, mobile = false, onToggleCollapse, onCloseMobile }: SidebarProps & { mobile?: boolean }) {
  const visibleItems = getVisibleNavigationItems(user);
  const items = visibleItems.filter((item) => item.href !== '/admin' && !item.href.startsWith('/admin/') && item.href !== '/api-testing');
  const adminItems = visibleItems.filter((item) => item.href.startsWith('/admin/'));
  const apiTestingItem = visibleItems.find((item) => item.href === '/api-testing');
  const [adminOpen, setAdminOpen] = useState(false);
  const adminExpanded = adminOpen || pathname.startsWith('/admin');
  const activeHref = items
    .filter((item) => pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(`${item.href}/`)))
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;

  return (
    <div className={`${styles.sidebarContent} ${mobile ? styles.mobileDrawerContent : ''}`}>
      <div className={styles.brand}>
        <div className={styles.brandVisual}>
          <Image className={styles.brandLogo} src="/brand/rostelecom-horizontal.svg" alt="Ростелеком" width={174} height={46} priority unoptimized />
          {collapsed && !mobile ? <Image className={styles.brandLogoCompact} src="/brand/rostelecom-vertical.svg" alt="" aria-hidden="true" width={46} height={46} unoptimized /> : null}
        </div>
      </div>

      <nav className={styles.nav}>
        <p className={styles.sectionLabel}>{(!collapsed || mobile) && 'Рабочая область'}</p>
        {items.map((item) => {
          const active = activeHref === item.href;
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
        {adminItems.length ? <>
          <button className={`${styles.navItem} ${pathname.startsWith('/admin') ? styles.active : ''}`} type="button" onClick={() => setAdminOpen((value) => !value)} aria-expanded={adminExpanded} title={collapsed && !mobile ? 'Администрирование' : undefined}>
            <Icon name="admin" size={20} />
            {(!collapsed || mobile) && <><span>Администрирование</span><Icon name={adminExpanded ? 'chevron-down' : 'chevron-right'} size={16} /></>}
            {pathname.startsWith('/admin') && <span className={styles.activeMarker} aria-hidden="true" />}
          </button>
          {adminExpanded && (!collapsed || mobile) ? <div className={styles.subnav} aria-label="Разделы администрирования">
            {adminItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return <Link className={`${styles.subnavItem} ${active ? styles.subnavActive : ''}`} href={item.href} key={item.href} onClick={mobile ? onCloseMobile : undefined} aria-current={active ? 'page' : undefined}><span>{item.label}</span></Link>;
            })}
          </div> : null}
        </> : null}
        {apiTestingItem ? <Link
          className={`${styles.navItem} ${pathname === apiTestingItem.href ? styles.active : ''}`}
          href={apiTestingItem.href}
          onClick={mobile ? onCloseMobile : undefined}
          title={collapsed && !mobile ? apiTestingItem.label : undefined}
          aria-current={pathname === apiTestingItem.href ? 'page' : undefined}
        >
          <Icon name={apiTestingItem.icon} size={20} />
          {(!collapsed || mobile) && <span>{apiTestingItem.label}</span>}
          {pathname === apiTestingItem.href && <span className={styles.activeMarker} aria-hidden="true" />}
        </Link> : null}
      </nav>

      {!mobile && onToggleCollapse ? <div className={styles.sidebarFooter}><IconButton icon="chevron-right" label={collapsed ? 'Развернуть меню' : 'Свернуть меню'} className={`${styles.collapseButton} ${collapsed ? styles.collapseButtonRotated : ''}`} onClick={onToggleCollapse} /></div> : null}
    </div>
  );
}

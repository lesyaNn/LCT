'use client';

import { Breadcrumbs } from './Breadcrumbs';
import { GlobalSearch } from './GlobalSearch';
import type { AuthUser } from '@/shared/types/user';
import { UserMenu } from './UserMenu';
import { NotificationsButton } from './NotificationsButton';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import styles from './topbar.module.css';

interface TopbarProps {
  pathname: string;
  user: AuthUser;
  mobileOpen: boolean;
  onMenuOpen: () => void;
}

export function Topbar({ pathname, user, mobileOpen, onMenuOpen }: TopbarProps) {
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <IconButton icon="menu" label="Открыть меню" aria-expanded={mobileOpen} className={styles.menuButton} onClick={onMenuOpen} />
        <Breadcrumbs pathname={pathname} />
      </div>
      <GlobalSearch user={user} />
      <div className={styles.actions}><NotificationsButton /><UserMenu /></div>
    </header>
  );
}

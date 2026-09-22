'use client';

import { Breadcrumbs } from './Breadcrumbs';
import { UserMenu } from './UserMenu';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import styles from './topbar.module.css';

interface TopbarProps {
  pathname: string;
  onMenuOpen: () => void;
}

export function Topbar({ pathname, onMenuOpen }: TopbarProps) {
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <IconButton icon="menu" label="Открыть меню" className={styles.menuButton} onClick={onMenuOpen} />
        <Breadcrumbs pathname={pathname} />
      </div>
      <div className={styles.actions}>
        <IconButton icon="bell" label="Уведомления" />
        <div className={styles.separator} aria-hidden="true" />
        <UserMenu />
      </div>
    </header>
  );
}

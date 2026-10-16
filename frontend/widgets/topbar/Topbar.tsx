'use client';

import { Breadcrumbs } from './Breadcrumbs';
import { GlobalSearch } from './GlobalSearch';
import type { AuthUser } from '@/shared/types/user';
import { UserMenu } from './UserMenu';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import HelpStroke from '@atomaro/icons/24/alert/HelpStroke';
import { NotificationBell } from '@/widgets/notifications/notification-bell';
import styles from './topbar.module.css';

interface TopbarProps {
  pathname: string;
  user: AuthUser;
  mobileOpen: boolean;
  onMenuOpen: () => void;
  assistantOpen: boolean;
  onOpenAssistant: () => void;
}

export function Topbar({ pathname, user, mobileOpen, onMenuOpen, assistantOpen, onOpenAssistant }: TopbarProps) {
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        <IconButton icon="menu" label="Открыть меню" aria-expanded={mobileOpen} className={styles.menuButton} onClick={onMenuOpen} />
        <Breadcrumbs pathname={pathname} />
      </div>
      <GlobalSearch user={user} />
      <div className={styles.actions}>
        <Tooltip content="ИИ-помощник"><IconButton icon={<HelpStroke size={22} fill="currentColor" />} label="ИИ-помощник" aria-expanded={assistantOpen} aria-haspopup="dialog" onClick={onOpenAssistant} /></Tooltip>
        <NotificationBell pathname={pathname} /><UserMenu />
      </div>
    </header>
  );
}

'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authService } from '@/shared/lib/auth-service';
import { currentUser } from '@/shared/mocks/current-user';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Icon } from '@/shared/ui/rtk/icon';
import styles from './user-menu.module.css';

export function UserMenu() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => { document.removeEventListener('pointerdown', onPointerDown); document.removeEventListener('keydown', onKeyDown); };
  }, []);

  return (
    <div className={styles.root} ref={rootRef}>
      <button className={styles.trigger} type="button" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((value) => !value)}>
        <Avatar initials={currentUser.initials} size="s" />
        <span className={styles.triggerText}><strong>{currentUser.name}</strong><small>{currentUser.roleLabel}</small></span>
        <Icon name="chevron-down" size={16} />
      </button>
      {open && (
        <div className={styles.menu} role="menu">
          <div className={styles.profile}>
            <Avatar initials={currentUser.initials} size="m" />
            <div><strong>{currentUser.name}</strong><span>{currentUser.email}</span><small>{currentUser.roleLabel}</small></div>
          </div>
          <div className={styles.divider} />
          <button className={styles.menuItem} role="menuitem" type="button"><Icon name="user" size={18} />Профиль</button>
          <button className={styles.menuItem} role="menuitem" type="button"><Icon name="settings" size={18} />Настройки</button>
          <div className={styles.divider} />
          <button className={`${styles.menuItem} ${styles.danger}`} role="menuitem" type="button" onClick={() => { authService.logout(); router.push('/dashboard'); }}><Icon name="logout" size={18} />Выйти</button>
        </div>
      )}
    </div>
  );
}

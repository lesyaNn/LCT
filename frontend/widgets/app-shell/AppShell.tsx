'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Sidebar } from '@/widgets/sidebar/Sidebar';
import { Topbar } from '@/widgets/topbar/Topbar';
import styles from './app-shell.module.css';

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div className={`${styles.shell} ${collapsed ? styles.isCollapsed : ''}`}>
      <Sidebar pathname={pathname} collapsed={collapsed} mobileOpen={mobileOpen} onToggleCollapse={() => setCollapsed((value) => !value)} onCloseMobile={() => setMobileOpen(false)} />
      {mobileOpen && <button className={styles.backdrop} type="button" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)} />}
      <div className={styles.workspace}>
        <Topbar pathname={pathname} onMenuOpen={() => setMobileOpen(true)} />
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}

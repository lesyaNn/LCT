'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { canAccessRoute } from '@/shared/config/navigation';
import { AuthError, AuthLoading, AuthRequired, ForbiddenState } from '@/shared/ui/access-state';
import { useAuth } from '@/shared/auth/AuthProvider';
import { Sidebar } from '@/widgets/sidebar/Sidebar';
import { Topbar } from '@/widgets/topbar/Topbar';
import styles from './app-shell.module.css';

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const { status, user, error, login, retry } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const wasMobileOpen = useRef(false);

  useEffect(() => {
    const updateLayoutMode = () => {
      const isMobile = window.innerWidth <= 768;
      setCollapsed(!isMobile && window.innerWidth < 1200);
      if (isMobile) setMobileOpen(false);
    };

    updateLayoutMode();
    window.addEventListener('resize', updateLayoutMode);
    return () => window.removeEventListener('resize', updateLayoutMode);
  }, []);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (mobileOpen) {
      document.querySelector<HTMLButtonElement>('[aria-label="Закрыть меню"]')?.focus();
    } else if (wasMobileOpen.current) {
      document.querySelector<HTMLButtonElement>('[aria-label="Открыть меню"]')?.focus();
    }
    wasMobileOpen.current = mobileOpen;
  }, [mobileOpen]);

  if (status === 'loading') return <AuthLoading />;
  if (status === 'error') return <AuthError message={error ?? 'Неизвестная ошибка.'} onRetry={retry} />;
  if (status === 'unauthenticated' || !user) return <AuthRequired onLogin={() => void login()} />;

  const forbidden = !canAccessRoute(pathname, user.role);

  return (
    <div className={styles.shell}>
      <Sidebar role={user.role} pathname={pathname} collapsed={collapsed} mobileOpen={mobileOpen} onToggleCollapse={() => setCollapsed((value) => !value)} onCloseMobile={() => setMobileOpen(false)} />
      {mobileOpen && <button className={styles.backdrop} type="button" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)} />}
      <div className={styles.workspace}>
        <Topbar pathname={pathname} mobileOpen={mobileOpen} onMenuOpen={() => setMobileOpen(true)} />
        <main className={styles.content}>{forbidden ? <ForbiddenState /> : children}</main>
      </div>
    </div>
  );
}

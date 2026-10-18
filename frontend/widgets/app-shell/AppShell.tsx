'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { canAccessRoute } from '@/shared/config/navigation';
import { AuthError, AuthLoading, AuthRequired, ForbiddenState } from '@/shared/ui/access-state';
import { useAuth } from '@/shared/auth/AuthProvider';
import { Sidebar } from '@/widgets/sidebar/Sidebar';
import { Topbar } from '@/widgets/topbar/Topbar';
import { AssistantWidget } from '@/widgets/assistant/assistant-widget';
import styles from './app-shell.module.css';

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const { status, user, error, login, retry } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const wasMobileOpen = useRef(false);

  useEffect(() => {
    const updateLayoutMode = () => {
      const isMobile = window.innerWidth <= 768;
      setCollapsed(!isMobile && window.innerWidth < 1200);
      if (!isMobile) setMobileOpen(false);
    };

    updateLayoutMode();
    window.addEventListener('resize', updateLayoutMode);
    return () => window.removeEventListener('resize', updateLayoutMode);
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
  if (status === 'unauthenticated' || !user) {
    return <AuthRequired message={error ?? undefined} onLogin={() => void login(pathname)} />;
  }

  const forbidden = !canAccessRoute(pathname, user);

  return (
    <>
      <div className={styles.shell}>
        <Sidebar user={user} pathname={pathname} collapsed={collapsed} mobileOpen={mobileOpen} onToggleCollapse={() => setCollapsed((value) => !value)} onCloseMobile={() => setMobileOpen(false)} />
        <div className={styles.workspace}>
          <Topbar user={user} pathname={pathname} mobileOpen={mobileOpen} onMenuOpen={() => setMobileOpen(true)} assistantOpen={assistantOpen} onOpenAssistant={() => setAssistantOpen(true)} />
          <main className={styles.content}>{forbidden ? <ForbiddenState /> : children}</main>
        </div>
      </div>
      <AssistantWidget key={`${user.id}:${user.role}`} user={user} pathname={pathname} open={assistantOpen} onOpen={() => setAssistantOpen(true)} onClose={() => setAssistantOpen(false)} />
    </>
  );
}

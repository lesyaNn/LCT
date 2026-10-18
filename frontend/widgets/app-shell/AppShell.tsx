'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import dynamic from 'next/dynamic';
import { canAccessRoute, navigationItems } from '@/shared/config/navigation';
import { AuthError, AuthLoading, AuthRequired, ForbiddenState } from '@/shared/ui/access-state';
import { useAuth } from '@/shared/auth/AuthProvider';
import { Sidebar } from '@/widgets/sidebar/Sidebar';
import { Topbar } from '@/widgets/topbar/Topbar';
import { AssistantWidget } from '@/widgets/assistant/assistant-widget';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { Button } from '@/shared/ui/rtk/button';
import { NotesLauncherProvider, type NoteInsertion } from '@/widgets/notes/notes-launcher';
import styles from './app-shell.module.css';

const NotesWorkspace = dynamic(() => import('@/widgets/notes/notes-workspace').then((module) => module.NotesWorkspace), { ssr: false });

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const { status, user, error, login, retry } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [noteInsertion, setNoteInsertion] = useState<NoteInsertion | null>(null);
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
  const currentSection = navigationItems.find((item) => item.href === pathname);
  const currentLinkKind = pathname.startsWith('/universities/') ? 'university' : pathname.startsWith('/workflows/') ? 'workflow' : currentSection ? 'section' : null;

  return (
    <NotesLauncherProvider value={{ open: () => { setNoteInsertion(null); setNotesOpen(true); }, close: () => { setNotesOpen(false); setNoteInsertion(null); }, openWithLink: (link) => { setNoteInsertion({ ...link, key: Date.now() }); setNotesOpen(true); } }}>
      <div className={styles.shell}>
        <Sidebar user={user} pathname={pathname} collapsed={collapsed} mobileOpen={mobileOpen} onToggleCollapse={() => setCollapsed((value) => !value)} onCloseMobile={() => setMobileOpen(false)} />
        <div className={styles.workspace}>
          <Topbar user={user} pathname={pathname} mobileOpen={mobileOpen} onMenuOpen={() => setMobileOpen(true)} assistantOpen={assistantOpen} onOpenAssistant={() => setAssistantOpen(true)} notesOpen={notesOpen} onOpenNotes={() => { setNoteInsertion(null); setNotesOpen(true); }} />
          <main className={styles.content}>{forbidden ? <ForbiddenState /> : children}</main>
        </div>
      </div>
      <AssistantWidget key={`${user.id}:${user.role}`} user={user} pathname={pathname} open={assistantOpen} onOpen={() => setAssistantOpen(true)} onClose={() => setAssistantOpen(false)} />
      {notesOpen ? <Drawer title="Быстрые заметки" onClose={() => { setNotesOpen(false); setNoteInsertion(null); }}>
        {currentLinkKind ? <Button variant="ghost" size="s" type="button" onClick={() => setNoteInsertion({ key: Date.now(), kind: currentLinkKind, href: pathname, title: currentSection?.label ?? document.querySelector(currentLinkKind === 'university' ? 'main h1' : 'main h2')?.textContent?.trim() ?? 'Текущая страница' })}>+ Ссылка на эту страницу</Button> : null}
        <NotesWorkspace userId={user.id} compact insertion={noteInsertion} onInsertionConsumed={() => setNoteInsertion(null)} />
      </Drawer> : null}
    </NotesLauncherProvider>
  );
}

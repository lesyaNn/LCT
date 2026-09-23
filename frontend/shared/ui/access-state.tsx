'use client';

import { Button } from '@/shared/ui/rtk/button';
import { ErrorState } from './error-state';
import { LoadingState } from './loading-state';
import { StatusPage } from './status-page';
import styles from './access-state.module.css';

export function AuthLoading() {
  return <main><LoadingState title="Проверяем доступ" description="Подождите, пока CRM завершит проверку сессии." /></main>;
}

export function AuthRequired({ onLogin, message }: { onLogin: () => void; message?: string }) {
  return (
    <main className={styles.state} aria-live="polite">
      <p className={styles.eyebrow}>Требуется вход</p>
      <h1>Войдите в CRM</h1>
      <p>{message ?? 'Для продолжения используйте корпоративную учётную запись.'}</p>
      <Button variant="primary" size="m" onClick={onLogin}>Войти через Keycloak</Button>
    </main>
  );
}

export function AuthError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main><ErrorState title="Не удалось проверить доступ" description={message} presentation="large" onRetry={onRetry} headingLevel={1} /></main>;
}

export function ForbiddenState() {
  return <StatusPage code="403" title="Доступ запрещён" description="У вас нет прав для просмотра этой страницы." withinAppShell />;
}

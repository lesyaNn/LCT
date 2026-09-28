'use client';

import Image from 'next/image';
import { Button } from '@/shared/ui/rtk/button';
import { ErrorState } from './error-state';
import { LoadingState } from './loading-state';
import { StatusPage } from './status-page';
import styles from './access-state.module.css';

export function AuthLoading() {
  return <main><LoadingState title="Проверяем доступ" description="Подождите, пока CRM завершит проверку сессии." /></main>;
}

export function AuthRequired({ onLogin, message }: {
  onLogin: () => void;
  message?: string;
}) {
  return (
    <main className={styles.authPage} aria-live="polite">
      <div className={styles.authBrand}><Image src="/brand/rostelecom-horizontal.svg" alt="Ростелеком" width={238} height={62} priority unoptimized /></div>
      <section className={styles.authCard} aria-labelledby="auth-title">
        <span className={styles.authAccent} aria-hidden="true" />
        <p className={styles.eyebrow}>CRM ИТ-Школа</p>
        <h1 id="auth-title">Войдите в CRM</h1>
        <p>{message ?? 'Используйте корпоративную учётную запись Ростелекома.'}</p>
        <Button variant="primary" size="l" onClick={onLogin}>Войти через Ростелеком</Button>
      </section>
    </main>
  );
}

export function AuthError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main><ErrorState title="Не удалось проверить доступ" description={message} presentation="large" onRetry={onRetry} headingLevel={1} /></main>;
}

export function ForbiddenState() {
  return <StatusPage code="403" title="Доступ запрещён" description="У вас нет прав для просмотра этой страницы." withinAppShell />;
}

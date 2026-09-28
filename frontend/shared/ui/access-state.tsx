'use client';

import { useState } from 'react';
import Image from 'next/image';
import { Button } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import { ErrorState } from './error-state';
import { LoadingState } from './loading-state';
import { StatusPage } from './status-page';
import styles from './access-state.module.css';

export function AuthLoading() {
  return <main><LoadingState title="Проверяем доступ" description="Подождите, пока CRM завершит проверку сессии." /></main>;
}

const demoAccounts = [
  { username: 'admin', label: 'Администратор', description: 'Полный доступ и настройки' },
  { username: 'manager', label: 'Руководитель', description: 'Управление и контроль работы' },
  { username: 'user', label: 'Пользователь', description: 'Работа с доступными вузами' },
] as const;

export function AuthRequired({ onLogin, onDemoLogin, message }: {
  onLogin: () => void;
  onDemoLogin?: (username: 'admin' | 'manager' | 'user') => void;
  message?: string;
}) {
  const [demoOpen, setDemoOpen] = useState(false);
  return (
    <main className={styles.authPage} aria-live="polite">
      <div className={styles.authBrand}><Image src="/brand/rostelecom-horizontal.svg" alt="Ростелеком" width={238} height={62} priority unoptimized /></div>
      <section className={styles.authCard} aria-labelledby="auth-title">
        <span className={styles.authAccent} aria-hidden="true" />
        <p className={styles.eyebrow}>CRM ИТ-Школа</p>
        <h1 id="auth-title">Войдите в CRM</h1>
        <p>{message ?? 'Используйте корпоративную учётную запись Ростелекома.'}</p>
        <Button variant="primary" size="l" onClick={onLogin}>Войти через Ростелеком</Button>
        {onDemoLogin && <Button variant="orange" size="m" onClick={() => setDemoOpen(true)}>Демо-вход</Button>}
      </section>
      {demoOpen && onDemoLogin && <Modal title="Демо-вход" onClose={() => setDemoOpen(false)}>
        <p className={styles.demoIntro}>Выберите роль, чтобы посмотреть систему с разными правами доступа.</p>
        <div className={styles.demoRoles}>
          {demoAccounts.map(({ username, label, description }) => <div className={styles.demoRole} key={username}>
            <div><strong>{label}</strong><p>{description}</p></div>
            <Button variant="secondary" size="m" onClick={() => onDemoLogin(username)} aria-label={`Войти как ${label}`}>Войти</Button>
          </div>)}
        </div>
      </Modal>}
    </main>
  );
}

export function AuthError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main><ErrorState title="Не удалось проверить доступ" description={message} presentation="large" onRetry={onRetry} headingLevel={1} /></main>;
}

export function ForbiddenState() {
  return <StatusPage code="403" title="Доступ запрещён" description="У вас нет прав для просмотра этой страницы." withinAppShell />;
}

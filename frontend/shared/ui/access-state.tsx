'use client';

import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import styles from './access-state.module.css';

export function AuthLoading() {
  return (
    <main className={styles.state} aria-live="polite">
      <span className={styles.spinner} role="status" aria-label="Проверяем авторизацию" />
      <h1>Проверяем доступ</h1>
      <p>Подождите, пока CRM завершит проверку сессии.</p>
    </main>
  );
}

export function AuthRequired({ onLogin }: { onLogin: () => void }) {
  return (
    <main className={styles.state} aria-live="polite">
      <p className={styles.eyebrow}>Требуется вход</p>
      <h1>Войдите в CRM</h1>
      <p>Для продолжения используйте корпоративную учётную запись.</p>
      <Button variant="primary" size="m" onClick={onLogin}>Войти через Keycloak</Button>
    </main>
  );
}

export function AuthError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className={styles.state} aria-live="assertive">
      <p className={styles.eyebrow}>Ошибка авторизации</p>
      <h1>Не удалось проверить доступ</h1>
      <p>{message}</p>
      <Button variant="primary" size="m" onClick={onRetry}>Повторить</Button>
    </main>
  );
}

export function ForbiddenState() {
  return (
    <section className={styles.state} aria-labelledby="forbidden-title">
      <p className={styles.eyebrow}>403</p>
      <h1 id="forbidden-title">Недостаточно прав</h1>
      <p>У вашей роли нет доступа к этому разделу CRM.</p>
      <ButtonLink href="/dashboard" variant="primary" size="m">На главную</ButtonLink>
    </section>
  );
}

'use client';

import { Button, ButtonLink } from '@/shared/ui/rtk/button';
import styles from './route-state.module.css';

export function RouteErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <section className={styles.error} aria-labelledby="route-error-title">
      <p className={styles.eyebrow}>Ошибка загрузки</p>
      <h1 id="route-error-title">Не удалось открыть раздел</h1>
      <p>Повторите попытку. Если ошибка сохранится, вернитесь на главную страницу CRM.</p>
      <div className={styles.actions}>
        <Button variant="primary" size="m" onClick={onRetry}>Повторить</Button>
        <ButtonLink href="/dashboard" variant="secondary" size="m">На главную</ButtonLink>
      </div>
    </section>
  );
}

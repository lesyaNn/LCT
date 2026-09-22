import { ButtonLink } from '@/shared/ui/rtk/button';
import styles from './not-found-state.module.css';

export function NotFoundState() {
  return (
    <main className={styles.page}>
      <p className={styles.eyebrow}>404</p>
      <h1>Страница не найдена</h1>
      <p>Проверьте адрес или вернитесь на главную страницу CRM.</p>
      <ButtonLink href="/dashboard" variant="primary" size="m">На главную</ButtonLink>
    </main>
  );
}

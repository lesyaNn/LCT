import { ButtonLink } from '@/shared/ui/rtk/button';

export default function NotFound() {
  return (
    <main className="not-found-page">
      <p className="eyebrow">404</p>
      <h1>Страница не найдена</h1>
      <p>Проверьте адрес или вернитесь на главную страницу CRM.</p>
      <ButtonLink href="/dashboard" variant="primary" size="m">На главную</ButtonLink>
    </main>
  );
}

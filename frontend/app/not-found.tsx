import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="not-found-page">
      <p className="eyebrow">404</p>
      <h1>Страница не найдена</h1>
      <p>Проверьте адрес или вернитесь на главную страницу CRM.</p>
      <Link className="not-found-link" href="/dashboard">
        Перейти в Dashboard
      </Link>
    </main>
  );
}

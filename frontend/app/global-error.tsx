'use client';

import { StatusPage } from '@/shared/ui/status-page';

export default function GlobalError({ reset }: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return (
    <html lang="ru" className="Theme_root_rtk_purple_light">
      <body><StatusPage code="500" title="Ошибка сервера" description="Что-то пошло не так. Попробуйте повторить действие." onRetry={reset} /></body>
    </html>
  );
}

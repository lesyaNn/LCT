'use client';

import { StatusPage } from '@/shared/ui/status-page';

export default function ErrorPage({ reset }: Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>) {
  return <StatusPage code="500" title="Ошибка сервера" description="Что-то пошло не так. Попробуйте повторить действие." onRetry={reset} withinAppShell />;
}

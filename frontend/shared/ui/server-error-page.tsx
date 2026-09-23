'use client';

import { useRouter } from 'next/navigation';
import { StatusPage } from './status-page';

export function ServerErrorPage() {
  const router = useRouter();
  return <StatusPage code="500" title="Ошибка сервера" description="Что-то пошло не так. Попробуйте повторить действие." onRetry={() => router.refresh()} />;
}

'use client';

import { ErrorState } from './error-state';

export function RouteErrorState({ onRetry, compact = false, title = 'Не удалось загрузить данные', description = 'Попробуйте повторить запрос.' }: { onRetry: () => void | Promise<void>; compact?: boolean; title?: string; description?: string }) {
  return <ErrorState title={title} description={description} presentation={compact ? 'compact' : 'large'} onRetry={onRetry} secondaryAction={compact ? undefined : { label: 'На главную', href: '/dashboard' }} />;
}

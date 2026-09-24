'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AuthError, AuthLoading, AuthRequired } from '@/shared/ui/access-state';
import { useAuth } from '@/shared/auth/AuthProvider';
import { authService } from '@/shared/lib/auth-service';
import { getSafeReturnPath } from '@/shared/lib/keycloak-adapter';

export default function LoginPage() {
  const router = useRouter();
  const { status, error, login, retry } = useAuth();
  const [{ returnTo, notice }] = useState(() => {
    if (typeof window === 'undefined') return { returnTo: '/dashboard', notice: undefined as string | undefined };
    const query = new URLSearchParams(window.location.search);
    const reason = query.get('reason');
    return {
      returnTo: getSafeReturnPath(query.get('returnTo')),
      notice: reason === 'session-expired'
        ? 'Сессия истекла. Войдите снова.'
        : reason === 'login-error'
          ? 'Не удалось выполнить вход. Попробуйте ещё раз.'
          : undefined,
    };
  });

  useEffect(() => {
    if (status === 'authenticated') router.replace(returnTo);
    if (status === 'unauthenticated' && authService.mode() === 'keycloak') void login(returnTo);
  }, [login, returnTo, router, status]);

  if (status === 'loading' || status === 'authenticated'
    || (status === 'unauthenticated' && authService.mode() === 'keycloak')) return <AuthLoading />;
  if (status === 'error') return <AuthError message={error ?? 'Не удалось проверить сессию.'} onRetry={retry} />;

  return <AuthRequired message={notice} onLogin={() => void login(returnTo)} />;
}

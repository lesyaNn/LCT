'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { AuthError, AuthLoading, AuthRequired } from '@/shared/ui/access-state';
import { useAuth } from '@/shared/auth/AuthProvider';

export default function LoginPage() {
  const router = useRouter();
  const { status, error, login, retry } = useAuth();

  useEffect(() => {
    if (status === 'authenticated') router.replace('/dashboard');
  }, [router, status]);

  if (status === 'loading' || status === 'authenticated') return <AuthLoading />;
  if (status === 'error') return <AuthError message={error ?? 'Не удалось проверить сессию.'} onRetry={retry} />;

  return <AuthRequired onLogin={() => void login()} />;
}

'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authService } from '@/shared/lib/auth-service';
import { useCurrentUser } from '@/shared/auth/use-current-user';
import { ApiRequestError, normalizeApiError } from '@/shared/lib/api-errors';
import {
  initializeKeycloak,
  loginToKeycloak,
  logoutFromKeycloak,
  registerSessionExpiredHandler,
} from '@/shared/lib/keycloak-adapter';
import { queryKeys } from '@/shared/lib/query-keys';
import { currentUser } from '@/shared/mocks/current-user';
import type { AuthUser } from '@/shared/types/user';

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

export interface AuthContextValue {
  status: AuthStatus;
  isLoading: boolean;
  isAuthenticated: boolean;
  user: AuthUser | null;
  error: string | null;
  login: (returnTo?: string, loginHint?: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const mode = authService.mode();
  const queryClient = useQueryClient();
  const [attempt, setAttempt] = useState(0);
  const [keycloakStatus, setKeycloakStatus] = useState<AuthStatus>(() => (
    mode === 'keycloak' ? 'loading' : 'authenticated'
  ));
  const [mockAuthenticated, setMockAuthenticated] = useState(mode === 'mock');
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const currentUserQuery = useCurrentUser({
    enabled: mode === 'keycloak' && keycloakStatus === 'authenticated',
  });

  useEffect(() => {
    if (mode !== 'keycloak') return undefined;

    let cancelled = false;
    const unregisterSessionExpiredHandler = registerSessionExpiredHandler(() => {
      queryClient.removeQueries({ queryKey: queryKeys.auth.all });
      setKeycloakStatus('unauthenticated');
      setBootstrapError('Сессия истекла. Войдите снова.');
    });

    void initializeKeycloak()
      .then((result) => {
        if (cancelled) return;
        if (!result.authenticated) queryClient.removeQueries({ queryKey: queryKeys.auth.all });
        setKeycloakStatus(result.authenticated ? 'authenticated' : 'unauthenticated');
        setBootstrapError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        queryClient.removeQueries({ queryKey: queryKeys.auth.all });
        setKeycloakStatus('error');
        setBootstrapError(cause instanceof Error ? cause.message : 'Не удалось определить состояние Keycloak.');
      });

    return () => {
      cancelled = true;
      unregisterSessionExpiredHandler();
    };
  }, [attempt, mode, queryClient]);

  const login = useCallback(async (returnTo = '/dashboard', loginHint?: string) => {
    setBootstrapError(null);
    if (mode === 'keycloak') {
      try {
        await loginToKeycloak(returnTo, loginHint);
      } catch (cause: unknown) {
        setKeycloakStatus('error');
        setBootstrapError(cause instanceof Error ? cause.message : 'Не удалось выполнить вход. Попробуйте ещё раз.');
      }
      return;
    }
    setMockAuthenticated(true);
  }, [mode]);

  const logout = useCallback(async () => {
    queryClient.removeQueries({ queryKey: queryKeys.auth.all });
    setBootstrapError(null);
    if (mode === 'keycloak') {
      setKeycloakStatus('unauthenticated');
      try {
        await logoutFromKeycloak();
      } catch (cause: unknown) {
        setBootstrapError(cause instanceof Error ? cause.message : 'Не удалось завершить сессию Keycloak.');
      }
      return;
    }
    authService.logout();
    setMockAuthenticated(false);
  }, [mode, queryClient]);

  const retry = useCallback(() => {
    setBootstrapError(null);
    if (keycloakStatus === 'authenticated' && currentUserQuery.isError) {
      void currentUserQuery.refetch();
      return;
    }
    setKeycloakStatus('loading');
    setAttempt((value) => value + 1);
  }, [currentUserQuery, keycloakStatus]);

  let status: AuthStatus;
  let user: AuthUser | null;
  let error = bootstrapError;
  if (mode === 'mock') {
    status = mockAuthenticated ? 'authenticated' : 'unauthenticated';
    user = mockAuthenticated ? currentUser : null;
  } else if (keycloakStatus !== 'authenticated') {
    status = keycloakStatus;
    user = null;
  } else if (currentUserQuery.isPending || currentUserQuery.isFetching && !currentUserQuery.data) {
    status = 'loading';
    user = null;
  } else if (currentUserQuery.isError) {
    status = currentUserQuery.error instanceof ApiRequestError && currentUserQuery.error.status === 401
      ? 'unauthenticated'
      : 'error';
    user = null;
    error = normalizeApiError(currentUserQuery.error, {
      fallbackMessage: 'Не удалось загрузить данные текущего пользователя.',
    }).message;
  } else {
    status = 'authenticated';
    user = currentUserQuery.data ?? null;
  }

  const value = useMemo<AuthContextValue>(() => ({
    status,
    isLoading: status === 'loading',
    isAuthenticated: status === 'authenticated',
    user,
    error,
    login,
    logout,
    retry,
  }), [error, login, logout, retry, status, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider.');
  return context;
}

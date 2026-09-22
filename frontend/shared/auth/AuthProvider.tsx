'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { authService } from '@/shared/lib/auth-service';
import {
  initializeKeycloak,
  loginToKeycloak,
  logoutFromKeycloak,
  type KeycloakAuthResult,
} from '@/shared/lib/keycloak-adapter';
import { currentUser } from '@/shared/mocks/current-user';
import { roleLabels, type AuthUser, type UserRole } from '@/shared/types/user';

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

export interface AuthContextValue {
  status: AuthStatus;
  isLoading: boolean;
  isAuthenticated: boolean;
  user: AuthUser | null;
  error: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function getFrontendRole(rawRoles: string[]): UserRole {
  if (rawRoles.includes('admin')) return 'admin';
  if (rawRoles.includes('manager')) return 'manager';
  // `curator` is a real realm role; the frontend maps it to the least
  // privileged authenticated UI role until a dedicated permission matrix exists.
  return 'user';
}

function getInitials(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('');

  return initials.toLocaleUpperCase('ru-RU') || 'П';
}

function userFromKeycloak(result: KeycloakAuthResult): AuthUser {
  const role = getFrontendRole(result.roles);
  const name = result.name || result.username || 'Пользователь';

  return {
    id: result.id,
    username: result.username,
    name,
    email: result.email,
    role,
    roleLabel: roleLabels[role],
    initials: getInitials(name),
    rawRoles: result.roles,
    authSource: 'keycloak',
  };
}

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const mode = authService.mode();
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<AuthStatus>(() => (
    mode === 'keycloak' ? 'loading' : 'authenticated'
  ));
  const [user, setUser] = useState<AuthUser | null>(() => (
    mode === 'keycloak' ? null : currentUser
  ));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== 'keycloak') return undefined;

    let cancelled = false;

    void initializeKeycloak()
      .then((result) => {
        if (cancelled) return;
        setUser(result.authenticated ? userFromKeycloak(result) : null);
        setStatus(result.authenticated ? 'authenticated' : 'unauthenticated');
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setUser(null);
        setStatus('error');
        setError(cause instanceof Error ? cause.message : 'Не удалось определить состояние Keycloak.');
      });

    return () => {
      cancelled = true;
    };
  }, [attempt, mode]);

  const login = useCallback(async () => {
    if (mode === 'keycloak') {
      await loginToKeycloak();
      return;
    }
    setUser(currentUser);
    setStatus('authenticated');
  }, [mode]);

  const logout = useCallback(async () => {
    if (mode === 'keycloak') {
      await logoutFromKeycloak();
      return;
    }
    authService.logout();
    setUser(null);
    setStatus('unauthenticated');
  }, [mode]);

  const retry = useCallback(() => {
    setError(null);
    setStatus('loading');
    setAttempt((value) => value + 1);
  }, []);
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

'use client';

import type KeycloakInstance from 'keycloak-js';
import { authService } from './auth-service';

/**
 * Keycloak is the auth source for the existing backend. It is enabled by
 * default; mock mode is an explicit local preview override without
 * reintroducing the old Vite router.
 */
export type KeycloakRuntimeConfig = {
  url: string;
  realm: string;
  clientId: string;
};

export interface KeycloakAuthResult {
  authenticated: boolean;
  id: string;
  username: string;
  name: string;
  email: string;
  roles: string[];
}

export interface KeycloakAccessClaims {
  universityIds: string[];
}

const defaultConfig: KeycloakRuntimeConfig = {
  url: 'http://localhost:8081',
  realm: 'rtk',
  clientId: 'rtk-frontend',
};

let instance: KeycloakInstance | null = null;
let refreshPromise: Promise<string | null> | null = null;
let sessionExpiredHandler: (() => void) | null = null;
let sessionExpiredRedirectArmed = false;

export function isKeycloakMode(): boolean {
  return authService.mode() === 'keycloak';
}

export function getKeycloakConfig(): KeycloakRuntimeConfig {
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || defaultConfig.url,
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || defaultConfig.realm,
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID || defaultConfig.clientId,
  };
}

export function getSafeReturnPath(candidate?: string | null): string {
  const fallback = '/dashboard';
  if (typeof window === 'undefined' || !candidate || !candidate.startsWith('/') || candidate.startsWith('//')) {
    return fallback;
  }

  try {
    const url = new URL(candidate, window.location.origin);
    if (url.origin !== window.location.origin || url.pathname === '/login') return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}

export function registerSessionExpiredHandler(handler: (() => void) | null): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) sessionExpiredHandler = null;
  };
}

export async function ensureKeycloak(): Promise<KeycloakInstance> {
  if (typeof window === 'undefined') {
    throw new Error('Keycloak can only be initialized in a browser.');
  }

  if (!instance) {
    const { default: Keycloak } = await import('keycloak-js');
    instance = new Keycloak(getKeycloakConfig());
  }

  return instance;
}

export async function initializeKeycloak(): Promise<KeycloakAuthResult> {
  const keycloak = await ensureKeycloak();
  keycloak.onTokenExpired = () => {
    void refreshKeycloakToken(60)
      .then((token) => { if (!token) return expireKeycloakSession(); })
      .catch(() => expireKeycloakSession());
  };

  const authenticated = await keycloak.init({
    onLoad: 'check-sso',
    pkceMethod: 'S256',
    checkLoginIframe: false,
    silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
    silentCheckSsoFallback: false,
  });

  const token = keycloak.tokenParsed ?? {};
  const rawRoles = token.realm_access?.roles;

  return {
    authenticated,
    id: token.sub ?? '',
    username: token.preferred_username ?? '',
    name: token.name ?? token.preferred_username ?? '',
    email: token.email ?? '',
    roles: Array.isArray(rawRoles) ? rawRoles.filter((role): role is string => typeof role === 'string') : [],
  };
}

export async function refreshKeycloakToken(minValidity = 30): Promise<string | null> {
  const keycloak = await ensureKeycloak();
  if (!keycloak.authenticated || !keycloak.token) return null;
  if (!refreshPromise) {
    refreshPromise = keycloak.updateToken(minValidity)
      .then(() => keycloak.token ?? null)
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

/**
 * Return only the assignment claim that the backend also reads when building
 * its data scope. Access tokens remain encapsulated in the Keycloak adapter.
 */
export function getKeycloakAccessClaims(): KeycloakAccessClaims {
  const claims = instance?.tokenParsed as Record<string, unknown> | undefined;
  const raw = claims?.university_ids ?? claims?.university_id;
  const values = typeof raw === 'string' ? [raw] : Array.isArray(raw) ? raw : [];
  return {
    universityIds: [...new Set(values.filter((value): value is string => typeof value === 'string' && Boolean(value.trim())).map((value) => value.trim()))],
  };
}

export async function expireKeycloakSession(): Promise<void> {
  if (sessionExpiredRedirectArmed) return;
  sessionExpiredRedirectArmed = true;

  try {
    const keycloak = await ensureKeycloak();
    keycloak.clearToken();
  } catch {
    // The browser may already be navigating away or Keycloak may be unavailable.
  }

  sessionExpiredHandler?.();
  if (typeof window !== 'undefined') window.location.replace('/login?reason=session-expired');
}

export async function loginToKeycloak(returnTo = '/dashboard', loginHint?: string): Promise<void> {
  const keycloak = await ensureKeycloak();
  sessionExpiredRedirectArmed = false;
  const redirectUrl = new URL('/login', window.location.origin);
  const safeReturnPath = getSafeReturnPath(returnTo);
  if (safeReturnPath !== '/dashboard') redirectUrl.searchParams.set('returnTo', safeReturnPath);
  await keycloak.login({ redirectUri: redirectUrl.toString(), ...(loginHint ? { loginHint } : {}) });
}

export async function logoutFromKeycloak(): Promise<void> {
  const keycloak = await ensureKeycloak();
  sessionExpiredRedirectArmed = false;
  try {
    await keycloak.logout({ redirectUri: `${window.location.origin}/login?openAuth=1` });
  } finally {
    keycloak.clearToken();
  }
}

export function resetKeycloakForTests(): void {
  instance = null;
  refreshPromise = null;
  sessionExpiredHandler = null;
  sessionExpiredRedirectArmed = false;
}

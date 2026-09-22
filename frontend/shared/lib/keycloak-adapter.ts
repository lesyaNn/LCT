'use client';

import type KeycloakInstance from 'keycloak-js';

/**
 * Keycloak is the auth source for the existing backend. The provider opts into
 * it when NEXT_PUBLIC_AUTH_MODE=keycloak; mock mode remains available for the
 * local App Shell preview without reintroducing the old Vite router.
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

const defaultConfig: KeycloakRuntimeConfig = {
  url: 'http://localhost:8081',
  realm: 'rtk',
  clientId: 'rtk-frontend',
};

let instance: KeycloakInstance | null = null;

export function isKeycloakMode(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_MODE === 'keycloak';
}

export function getKeycloakConfig(): KeycloakRuntimeConfig {
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || defaultConfig.url,
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || defaultConfig.realm,
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID || defaultConfig.clientId,
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
    void keycloak.updateToken(60).catch(() => keycloak.login({ redirectUri: window.location.origin }));
  };

  const authenticated = await keycloak.init({
    onLoad: 'check-sso',
    pkceMethod: 'S256',
    checkLoginIframe: false,
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

export async function loginToKeycloak(): Promise<void> {
  const keycloak = await ensureKeycloak();
  await keycloak.login({ redirectUri: window.location.origin });
}

export async function logoutFromKeycloak(): Promise<void> {
  const keycloak = await ensureKeycloak();
  await keycloak.logout({ redirectUri: window.location.origin });
}

export function resetKeycloakForTests(): void {
  instance = null;
}

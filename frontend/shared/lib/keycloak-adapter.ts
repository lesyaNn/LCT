'use client';

import type KeycloakInstance from 'keycloak-js';

/**
 * Keycloak remains an explicit integration seam for the existing backend.
 * P3-01-01 intentionally runs in mock mode, so this module is not imported by
 * the App Shell. A later auth task can opt in with NEXT_PUBLIC_AUTH_MODE=keycloak
 * without reintroducing the old Vite router or storing tokens in localStorage.
 */
export type KeycloakRuntimeConfig = {
  url: string;
  realm: string;
  clientId: string;
};

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

export async function initializeKeycloak(): Promise<boolean> {
  const keycloak = await ensureKeycloak();
  keycloak.onTokenExpired = () => {
    void keycloak.updateToken(60).catch(() => keycloak.login({ redirectUri: window.location.origin }));
  };

  return keycloak.init({
    onLoad: 'check-sso',
    pkceMethod: 'S256',
    checkLoginIframe: false,
  });
}

export async function logoutFromKeycloak(): Promise<void> {
  const keycloak = await ensureKeycloak();
  await keycloak.logout({ redirectUri: window.location.origin });
}

export function resetKeycloakForTests(): void {
  instance = null;
}

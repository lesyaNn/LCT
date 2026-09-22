'use client';

import { ensureKeycloak, isKeycloakMode } from './keycloak-adapter';

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string };

export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  anonymous?: boolean;
};

let loginRedirectArmed = false;

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
}

/**
 * Shared transport for the existing FastAPI endpoints. P3 pages do not call
 * it yet, but future domain modules get one place for Bearer, 401 and JSON
 * handling instead of reviving the old page-specific fetches.
 */
export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<ApiResult<T>> {
  const keycloak = isKeycloakMode() ? await ensureKeycloak() : null;
  let token: string | undefined;

  if (!options.anonymous) {
    if (!keycloak?.token) {
      return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
    }

    try {
      await keycloak.updateToken(30);
      token = keycloak.token;
    } catch {
      if (!loginRedirectArmed) {
        loginRedirectArmed = true;
        await keycloak.login({ redirectUri: window.location.origin });
      }
      return { ok: false, status: 401, error: 'Сессия истекла, выполняется повторный вход…' };
    }
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: options.method ?? 'GET',
      headers: {
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { ok: false, status: 0, error: 'Запрос отменён' };
    }
    return { ok: false, status: 0, error: `Backend недоступен: ${String(error)}` };
  }

  if (response.status === 204 || response.status === 205) {
    return { ok: true, status: response.status, data: undefined as T };
  }

  if (response.status === 401 && keycloak && !loginRedirectArmed) {
    loginRedirectArmed = true;
    await keycloak.login({ redirectUri: window.location.origin });
    return { ok: false, status: 401, error: 'Сессия истекла, выполняется повторный вход…' };
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    return { ok: false, status: response.status, error: `${response.status} ${text}`.trim() };
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    const text = await response.text().catch(() => '');
    return { ok: false, status: response.status, error: `Неожиданный ответ (не JSON): ${text.slice(0, 200)}` };
  }

  try {
    return { ok: true, status: response.status, data: (await response.json()) as T };
  } catch {
    return { ok: false, status: response.status, error: 'Не удалось разобрать JSON ответа' };
  }
}

export function resetApiClientForTests(): void {
  loginRedirectArmed = false;
}

'use client';

import { ensureKeycloak, expireKeycloakSession, isKeycloakMode, refreshKeycloakToken } from './keycloak-adapter';

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string };

export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  anonymous?: boolean;
};

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');
}

async function request<T>(path: string, options: ApiOptions, token?: string): Promise<ApiResult<T>> {
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

/**
 * Shared transport for the existing FastAPI endpoints. Keycloak keeps tokens
 * in its in-memory adapter; this client only attaches the current access token.
 * A 401 can trigger one shared refresh and one retry, never an unbounded loop.
 * TODO: if the backend later exposes an httpOnly-cookie proxy, prefer that
 * transport without moving tokens into browser storage.
 */
export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<ApiResult<T>> {
  const keycloak = isKeycloakMode() ? await ensureKeycloak() : null;
  let token: string | undefined;

  if (!options.anonymous) {
    if (!keycloak?.authenticated) {
      return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
    }

    try {
      token = await refreshKeycloakToken(30) ?? undefined;
    } catch {
      await expireKeycloakSession();
      return { ok: false, status: 401, error: 'Сессия истекла. Войдите снова.' };
    }

    if (!token) return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
  }

  let result = await request<T>(path, options, token);
  if (result.status !== 401 || !keycloak || options.anonymous) return result;

  try {
    const refreshedToken = await refreshKeycloakToken(30);
    if (refreshedToken) result = await request<T>(path, options, refreshedToken);
  } catch {
    // The common expiry path below clears the in-memory session and redirects.
  }

  if (result.status === 401) {
    await expireKeycloakSession();
    return { ok: false, status: 401, error: 'Сессия истекла. Войдите снова.' };
  }

  return result;
}

export function resetApiClientForTests(): void {
  // Kept as a stable test seam; refresh coordination lives in the Keycloak adapter.
}

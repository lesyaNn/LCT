'use client';

import { ensureKeycloak, expireKeycloakSession, isKeycloakMode, refreshKeycloakToken } from './keycloak-adapter';

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string; body?: unknown };

export type ApiOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  anonymous?: boolean;
  headers?: Record<string, string>;
};

const safeHeaders = new Set(['accept', 'accept-language', 'x-request-id']);

function allowedHeaders(headers: Record<string, string> | undefined): Record<string, string> {
  return Object.fromEntries(Object.entries(headers ?? {}).filter(([key, value]) =>
    safeHeaders.has(key.toLowerCase()) && !/[\r\n]/.test(value)));
}

export type ApiUploadOptions = {
  signal?: AbortSignal;
  onProgress?: (progress: number) => void;
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
        ...allowedHeaders(options.headers),
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
    let body: unknown;
    try { body = text ? JSON.parse(text) : undefined; } catch { body = undefined; }
    return { ok: false, status: response.status, error: `HTTP ${response.status}`, body };
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
  const keycloak = !options.anonymous && isKeycloakMode() ? await ensureKeycloak() : null;
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
    // A backend 401 means the token already presented was rejected. Force one
    // refresh instead of reusing a still-time-valid token, then retry once.
    const refreshedToken = await refreshKeycloakToken(-1);
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

/** Authenticated binary download, optionally generated from a JSON payload. */
export async function apiDownload(path: string, signal?: AbortSignal, options: Pick<ApiOptions, 'method' | 'body'> = {}): Promise<ApiResult<Blob>> {
  const keycloak = isKeycloakMode() ? await ensureKeycloak() : null;
  if (!keycloak?.authenticated) return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
  let token: string | null;
  try { token = await refreshKeycloakToken(30); }
  catch { await expireKeycloakSession(); return { ok: false, status: 401, error: 'Сессия истекла. Войдите снова.' }; }
  if (!token) return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
  const fetchBlob = async (accessToken: string): Promise<ApiResult<Blob>> => {
    try {
      const response = await fetch(`${apiBaseUrl()}${path}`, {
        method: options.method ?? 'GET',
        headers: { Authorization: `Bearer ${accessToken}`, ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal,
      });
      if (!response.ok) {
        const raw = await response.text().catch(() => '');
        let body: unknown;
        try { body = raw ? JSON.parse(raw) : undefined; } catch { body = undefined; }
        return { ok: false, status: response.status, error: `HTTP ${response.status}`, body };
      }
      return { ok: true, status: response.status, data: await response.blob() };
    } catch (error) {
      return { ok: false, status: 0, error: error instanceof DOMException && error.name === 'AbortError' ? 'Запрос отменён' : `Backend недоступен: ${String(error)}` };
    }
  };
  let result = await fetchBlob(token);
  if (result.status === 401) {
    try { const fresh = await refreshKeycloakToken(-1); if (fresh) result = await fetchBlob(fresh); } catch { /* expiry below */ }
    if (result.status === 401) await expireKeycloakSession();
  }
  return result;
}

/**
 * Multipart transport for uploads that need real browser upload progress.
 * XMLHttpRequest stays in the shared data layer; callers only provide a
 * FormData body, progress callback and AbortSignal.
 */
export async function apiUploadFormData<T>(path: string, body: FormData, options: ApiUploadOptions = {}): Promise<ApiResult<T>> {
  if (options.signal?.aborted) throw new DOMException('Загрузка отменена', 'AbortError');

  const keycloak = isKeycloakMode() ? await ensureKeycloak() : null;
  let token: string | undefined;
  if (keycloak) {
    if (!keycloak.authenticated) return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
    try {
      token = await refreshKeycloakToken(30) ?? undefined;
    } catch {
      await expireKeycloakSession();
      return { ok: false, status: 401, error: 'Сессия истекла. Войдите снова.' };
    }
    if (!token) return { ok: false, status: 401, error: 'AUTH_REQUIRED — войдите в систему' };
  }
  if (options.signal?.aborted) throw new DOMException('Загрузка отменена', 'AbortError');

  return new Promise<ApiResult<T>>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const cleanup = () => options.signal?.removeEventListener('abort', abort);
    xhr.open('POST', `${apiBaseUrl()}${path}`);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      options.onProgress?.(Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100))));
    };
    xhr.upload.onload = () => options.onProgress?.(100);
    xhr.onload = () => {
      cleanup();
      if (xhr.status === 401 && keycloak) void expireKeycloakSession();
      if (xhr.status < 200 || xhr.status >= 300) {
        let body: unknown;
        try { body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined; } catch { body = undefined; }
        resolve({ ok: false, status: xhr.status, error: `HTTP ${xhr.status}`, body });
        return;
      }
      const contentType = xhr.getResponseHeader('content-type') ?? '';
      if (!contentType.includes('application/json')) {
        resolve({ ok: false, status: xhr.status, error: 'Неожиданный ответ при upload (не JSON)' });
        return;
      }
      try {
        resolve({ ok: true, status: xhr.status, data: JSON.parse(xhr.responseText) as T });
      } catch {
        resolve({ ok: false, status: xhr.status, error: 'Не удалось разобрать JSON ответа' });
      }
    };
    xhr.onerror = () => { cleanup(); resolve({ ok: false, status: 0, error: 'Backend недоступен во время upload' }); };
    xhr.onabort = () => { cleanup(); reject(new DOMException('Загрузка отменена', 'AbortError')); };
    options.signal?.addEventListener('abort', abort, { once: true });
    options.onProgress?.(0);
    xhr.send(body);
  });
}

export function resetApiClientForTests(): void {
  // Kept as a stable test seam; refresh coordination lives in the Keycloak adapter.
}

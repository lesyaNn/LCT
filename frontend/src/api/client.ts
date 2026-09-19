import { getConfig } from "../config";
import { ensureKeycloak } from "../auth/keycloak";

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string };

export type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Skip the proactive refresh (public endpoints). */
  anonymous?: boolean;
};

let loginRedirectArmed = false;

function baseUrl(): string {
  return getConfig().apiUrl.replace(/\/$/, "");
}

async function refreshOrLogin(): Promise<boolean> {
  const keycloak = ensureKeycloak();
  if (!keycloak.token) return false; // not authenticated yet — no Bearer, no redirect
  try {
    await keycloak.updateToken(30);
    return true;
  } catch {
    // Refresh failed: single login redirect (anti-loop flag), then report.
    if (!loginRedirectArmed) {
      loginRedirectArmed = true;
      await keycloak.login({ redirectUri: window.location.origin + "/" });
    }
    return false;
  }
}

/** Test seam: re-arm the one-shot login redirect. */
export function __resetApiForTests(): void {
  loginRedirectArmed = false;
}

/** Unified API client: methods, body, abort, 204/HTML guards, 401 handling. */
export async function apiFetch<T>(path: string, opts: ApiOptions = {}): Promise<ApiResult<T>> {
  const keycloak = ensureKeycloak();
  if (!opts.anonymous) {
    const fresh = await refreshOrLogin();
    if (!fresh) {
      return keycloak.token
        ? { ok: false, status: 0, error: "Сессия истекла, выполняется повторный вход…" }
        : { ok: false, status: 401, error: "AUTH_REQUIRED — войдите в систему" };
    }
  }
  let resp: Response;
  try {
    resp = await fetch(`${baseUrl()}${path}`, {
      method: opts.method ?? "GET",
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(keycloak.token ? { Authorization: `Bearer ${keycloak.token}` } : {}),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      return { ok: false, status: 0, error: "Запрос отменён" };
    }
    return { ok: false, status: 0, error: `Backend недоступен: ${String(e)}` };
  }
  if (resp.status === 204 || resp.status === 205) {
    return { ok: true, status: resp.status, data: undefined as T };
  }
  if (!resp.ok) {
    if (resp.status === 401 && !opts.anonymous && !loginRedirectArmed) {
      loginRedirectArmed = true; // expired mid-flight — one re-login, no loop
      await keycloak.login({ redirectUri: window.location.origin + "/" });
      return { ok: false, status: 401, error: "Сессия истекла, выполняется повторный вход…" };
    }
    const text = await resp.text().catch(() => "");
    return { ok: false, status: resp.status, error: `${resp.status} ${text}`.trim() };
  }
  const contentType = resp.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await resp.text().catch(() => "");
    return {
      ok: false,
      status: resp.status,
      error: `Неожиданный ответ (не JSON): ${text.slice(0, 200)}`.trim(),
    };
  }
  try {
    return { ok: true, status: resp.status, data: (await resp.json()) as T };
  } catch {
    return { ok: false, status: resp.status, error: "Не удалось разобрать JSON ответа" };
  }
}

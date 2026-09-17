import { keycloak } from "../auth/keycloak";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type ApiResult<T> = { ok: true; status: number; data: T } | { ok: false; status: number; error: string };

/** Single API client: refreshes the token before every protected call. */
export async function apiFetch<T>(path: string): Promise<ApiResult<T>> {
  try {
    await keycloak.updateToken(30);
  } catch {
    // Refresh failed: drop local auth state and go back to login.
    await keycloak.login({ redirectUri: window.location.origin + "/" });
    return { ok: false, status: 0, error: "Сессия истекла, выполняется повторный вход…" };
  }
  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, {
      headers: { Authorization: `Bearer ${keycloak.token}` },
    });
  } catch (e) {
    return { ok: false, status: 0, error: `Backend недоступен: ${String(e)}` };
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    return { ok: false, status: resp.status, error: `${resp.status} ${text}`.trim() };
  }
  return { ok: true, status: resp.status, data: (await resp.json()) as T };
}

/** Runtime configuration (P0-2 fix).
 *
 * Build-time `VITE_*` values are only FALLBACK defaults. In Docker the
 * entrypoint rewrites `/config.json` from environment, so the same image
 * runs on any host without a rebuild. An empty `apiUrl` means "same
 * origin" — requests go to the nginx `/api/` proxy (no CORS involved).
 */
export type AppConfig = {
  keycloakUrl: string;
  keycloakRealm: string;
  keycloakClientId: string;
  apiUrl: string;
};

const BUILD_DEFAULTS: AppConfig = {
  keycloakUrl: import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8081",
  keycloakRealm: import.meta.env.VITE_KEYCLOAK_REALM ?? "rtk",
  keycloakClientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "rtk-frontend",
  // Same-origin by default: prefer the /api proxy over a baked host.
  apiUrl: import.meta.env.VITE_API_URL ?? "",
};

let cached: AppConfig | null = null;
let inflight: Promise<AppConfig> | null = null;

export async function loadConfig(): Promise<AppConfig> {
  if (cached) return cached;
  if (!inflight) {
    inflight = fetch("/config.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}))
      .then((json) => {
        const raw = (json ?? {}) as Partial<AppConfig>;
        cached = {
          keycloakUrl: raw.keycloakUrl || BUILD_DEFAULTS.keycloakUrl,
          keycloakRealm: raw.keycloakRealm || BUILD_DEFAULTS.keycloakRealm,
          keycloakClientId: raw.keycloakClientId || BUILD_DEFAULTS.keycloakClientId,
          apiUrl: raw.apiUrl ?? BUILD_DEFAULTS.apiUrl,
        };
        return cached;
      });
  }
  return inflight;
}

/** Synchronous access after `loadConfig()` resolved (AuthProvider awaits it). */
export function getConfig(): AppConfig {
  return cached ?? BUILD_DEFAULTS;
}

/** Test seam: reset the cache between tests. */
export function __resetConfigForTests(): void {
  cached = null;
  inflight = null;
}

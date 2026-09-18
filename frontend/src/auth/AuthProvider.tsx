import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { loadConfig } from "../config";
import { ensureKeycloak } from "./keycloak";

type AuthState = {
  ready: boolean;
  authenticated: boolean;
  error: string | null;
  retry: () => void;
  login: () => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState>({
  ready: false,
  authenticated: false,
  error: null,
  retry: () => {},
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setError(null);
    void (async () => {
      try {
        await loadConfig(); // runtime /config.json first — never baked hosts
        const keycloak = ensureKeycloak();
        keycloak.onTokenExpired = () => {
          void keycloak.updateToken(60).catch(() => keycloak.login());
        };
        const auth = await keycloak.init({
          onLoad: "check-sso",
          pkceMethod: "S256",
          checkLoginIframe: false,
        });
        if (!cancelled) {
          setAuthenticated(auth);
          setReady(true);
        }
      } catch (e) {
        if (!cancelled) {
          // init failure is surfaced (not swallowed): UI shows retry, not a bare login.
          setError(e instanceof Error ? e.message : String(e));
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const login = useCallback(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("error")) {
      setError(`Keycloak: ${qs.get("error") ?? ""} ${qs.get("error_description") ?? ""}`.trim());
      return;
    }
    void ensureKeycloak().login({ redirectUri: window.location.origin + "/" });
  }, []);

  const logout = useCallback(() => {
    void ensureKeycloak().logout({ redirectUri: window.location.origin + "/" });
  }, []);

  const value = useMemo(
    () => ({ ready, authenticated, error, retry, login, logout }),
    [ready, authenticated, error, retry, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { keycloak } from "./keycloak";

type AuthState = {
  ready: boolean;
  authenticated: boolean;
  login: () => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState>({
  ready: false,
  authenticated: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    keycloak
      .init({
        onLoad: "check-sso",
        pkceMethod: "S256",
        checkLoginIframe: false,
      })
      .then((auth) => {
        if (!cancelled) {
          setAuthenticated(auth);
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(() => {
    void keycloak.login({ redirectUri: window.location.origin + "/" });
  }, []);

  const logout = useCallback(() => {
    void keycloak.logout({ redirectUri: window.location.origin + "/" });
  }, []);

  const value = useMemo(
    () => ({ ready, authenticated, login, logout }),
    [ready, authenticated, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

import { useEffect, useState } from "react";
import { apiFetch } from "./api/client";
import { useAuth } from "./auth/useAuth";
import { AnalyticsPage, CatalogPage, HomePage } from "./pages/pages";
import { routeHref, useRoute } from "./router";
import type { Me } from "./types";

export default function App() {
  const { ready, authenticated, error, retry, login, logout } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const route = useRoute();

  useEffect(() => {
    if (ready && authenticated) {
      const ctrl = new AbortController();
      void apiFetch<Me>("/api/v1/auth/me", { signal: ctrl.signal }).then((r) => {
        if (!ctrl.signal.aborted && r.ok) setMe(r.data);
      });
      return () => ctrl.abort();
    } else {
      setMe(null);
    }
  }, [ready, authenticated]);

  if (!ready) {
    return (
      <div className="page"><div className="center">Загрузка…</div></div>
    );
  }

  if (!authenticated) {
    return (
      <div className="page">
        <div className="hero">
          <h1>Цифровой конвейер<br />подготовки кадров</h1>
          <p>Единая платформа управления взаимодействием с вузами</p>
          {error ? (
            <div className="card" role="alert">
              <p className="err">Не удалось связаться с Keycloak: {error}</p>
              <button className="btn primary" onClick={retry}>Повторить</button>
            </div>
          ) : (
            <button className="btn primary" onClick={login}>Войти</button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="topbar">
        <strong>Цифровой конвейер подготовки кадров</strong>
        <nav aria-label="Разделы">
          <a className="btn" aria-current={route === "home" ? "page" : undefined} href={routeHref("home")}>Главная</a>
          {" "}
          <a className="btn" aria-current={route === "catalog" ? "page" : undefined} href={routeHref("catalog")}>Каталог</a>
          {" "}
          <a className="btn" aria-current={route === "analytics" ? "page" : undefined} href={routeHref("analytics")}>Аналитика</a>
          {" "}
          <button className="btn" onClick={logout}>Выйти</button>
        </nav>
      </header>
      <main className="content">
        {route === "catalog" ? <CatalogPage /> : route === "analytics" ? <AnalyticsPage /> : <HomePage me={me} onMe={setMe} />}
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import { apiFetch } from "./api/client";
import { useAuth } from "./auth/useAuth";
import { CatalogViewer } from "./components/CatalogViewer";
import { UserCard } from "./components/UserCard";
import type { Me } from "./components/UserCard";

type Check = { label: string; text: string; tone: "ok" | "err" | "idle" };

export default function App() {
  const { ready, authenticated, login, logout } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);

  useEffect(() => {
    if (ready && authenticated) {
      void apiFetch<Me>("/api/v1/auth/me").then((r) => {
        if (r.ok) setMe(r.data);
      });
    } else {
      setMe(null);
    }
  }, [ready, authenticated]);

  useEffect(() => {
    const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
    fetch(`${API}/health`)
      .then((r) => setBackendUp(r.ok))
      .catch(() => setBackendUp(false));
  }, []);

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
          <button className="btn primary" onClick={login}>Войти</button>
        </div>
      </div>
    );
  }

  const runCheck = async (kind: "me" | "admin") => {
    const path = kind === "me" ? "/api/v1/auth/me" : "/api/v1/auth/test/admin";
    const r = await apiFetch<unknown>(path);
    const label = kind === "me" ? "Backend" : "Admin доступ";
    if (r.ok) {
      setChecks((c) => [...c, { label, text: `✅ ${r.status} — доступ разрешён`, tone: "ok" }]);
      if (kind === "me") setMe(r.data as Me);
    } else if (r.status === 403) {
      setChecks((c) => [...c, { label, text: "⛔ 403 — недостаточно прав (ожидаемо)", tone: "err" }]);
    } else {
      setChecks((c) => [...c, { label, text: `⚠️ ${r.error}`, tone: "err" }]);
    }
  };

  return (
    <div className="page">
      <header className="topbar">
        <strong>Цифровой конвейер подготовки кадров</strong>
        <button className="btn" onClick={logout}>Выйти</button>
      </header>
      <main className="content">
        {me && <UserCard me={me} />}
        <CatalogViewer />
        <div className="card">
          <p>Backend API: {backendUp === null ? "…" : backendUp ? "✅ доступен" : "❌ недоступен"}</p>
          <div className="row">
            <button className="btn primary" onClick={() => void runCheck("me")}>Проверить Backend</button>
            <button className="btn" onClick={() => void runCheck("admin")}>Проверить Admin доступ</button>
          </div>
          <ul className="checks">
            {checks.map((c, i) => (
              <li key={i} className={c.tone}><strong>{c.label}:</strong> {c.text}</li>
            ))}
          </ul>
        </div>
      </main>
    </div>
  );
}

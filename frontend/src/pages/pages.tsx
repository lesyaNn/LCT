import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { getConfig } from "../config";
import { CatalogViewer } from "../components/CatalogViewer";
import { UserCard } from "../components/UserCard";
import type { Me } from "../types";

type Check = { id: number; label: string; text: string; tone: "ok" | "err" | "idle" };

let checkSeq = 0;

export function HomePage({ me, onMe }: { me: Me | null; onMe: (me: Me) => void }) {
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);

  useEffect(() => {
    const ctrl = new AbortController();
    // Anonymous liveness probe (no token needed). Same-origin mode goes
    // through the /api/health proxy mapping; direct mode hits /health.
    const probe = getConfig().apiUrl ? "/health" : "/api/health";
    void apiFetch<unknown>(probe, { anonymous: true, signal: ctrl.signal }).then((r) => {
      if (!ctrl.signal.aborted) setBackendUp(r.ok);
    });
    return () => ctrl.abort();
  }, []);

  const runCheck = async (kind: "me" | "admin") => {
    const path = kind === "me" ? "/api/v1/auth/me" : "/api/v1/auth/test/admin";
    const r = await apiFetch<unknown>(path);
    const label = kind === "me" ? "Backend" : "Admin доступ";
    checkSeq += 1;
    const id = checkSeq;
    if (r.ok) {
      setChecks((c) => [...c.slice(-19), { id, label, text: `✅ ${r.status} — доступ разрешён`, tone: "ok" }]);
      if (kind === "me") onMe(r.data as Me);
    } else if (r.status === 403) {
      setChecks((c) => [...c.slice(-19), { id, label, text: "⛔ 403 — недостаточно прав (ожидаемо)", tone: "err" }]);
    } else {
      setChecks((c) => [...c.slice(-19), { id, label, text: `⚠️ ${r.error}`, tone: "err" }]);
    }
  };

  return (
    <>
      {me && <UserCard me={me} />}
      <div className="card">
        <p>Backend API: {backendUp === null ? "…" : backendUp ? "✅ доступен" : "❌ недоступен"}</p>
        <div className="row">
          <button className="btn primary" onClick={() => void runCheck("me")}>Проверить Backend</button>
          <button className="btn" onClick={() => void runCheck("admin")}>Проверить Admin доступ</button>
        </div>
        <ul className="checks" aria-live="polite">
          {checks.map((c) => (
            <li key={c.id} className={c.tone}><strong>{c.label}:</strong> {c.text}</li>
          ))}
        </ul>
      </div>
    </>
  );
}

export function CatalogPage() {
  return <CatalogViewer />;
}

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import type { CatalogOverview } from "../types";

export type { CatalogDirection, CatalogOverview, CatalogRow } from "../types";

export function CatalogViewer() {
  const [data, setData] = useState<CatalogOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ctrlRef = useRef<AbortController | null>(null);

  useEffect(() => () => ctrlRef.current?.abort(), []);

  const load = async () => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setLoading(true);
    setError(null);
    const r = await apiFetch<CatalogOverview>("/api/v1/catalog/overview?page_size=100", {
      signal: ctrl.signal,
    });
    if (ctrl.signal.aborted) return;
    setLoading(false);
    if (r.ok) {
      setData(r.data);
    } else {
      setError(r.status === 0 ? r.error : `Ошибка ${r.status}: ${r.error}`);
    }
  };

  return (
    <div className="card">
      <h2>Загруженные данные</h2>
      <p className="muted">Что сейчас лежит в БД (вузы, договоры, лицензии, направления).</p>
      <div className="row">
        <button className="btn primary" onClick={() => void load()} disabled={loading}>
          {loading ? "Загрузка…" : data ? "Обновить" : "Показать данные"}
        </button>
      </div>
      {error && <p className="err" role="alert">{error}</p>}
      {data && (
        <>
          <p>
            Вузов: <strong>{data.total_universities}</strong>
            {" · "}Лицензий: <strong>{data.total_licenses}</strong>
          </p>
          {data.rows.length === 0 ? (
            <p className="muted">Пока пусто — загрузите файл через импорт.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Название ВУЗа</th>
                    <th>Вендор</th>
                    <th>ПО</th>
                    <th>Номер договора</th>
                    <th>Подписание лицензии</th>
                    <th>Срок действия (год)</th>
                    <th>Статус передачи</th>
                    <th>ФИО Менеджера</th>
                    <th>Ответственные от ВУЗа</th>
                    <th>Комментарий</th>
                    <th>IT направление</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={`${r.contract_number ?? "row"}-${i}`}>
                      <td>{r.university ?? "—"}</td>
                      <td>{r.vendor ?? "—"}</td>
                      <td>{r.product ?? "—"}</td>
                      <td>{r.contract_number ?? "—"}</td>
                      <td>{r.signed_at ?? "—"}</td>
                      <td>{r.expires_at ?? "—"}</td>
                      <td>{r.transfer_status ?? "—"}</td>
                      <td>{r.manager ?? "—"}</td>
                      <td>{(r.responsibles ?? []).join("; ") || "—"}</td>
                      <td>{r.comment ?? "—"}</td>
                      <td>{r.direction ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.directions.length > 0 && (
            <>
              <h3>IT-направления</h3>
              <ul className="checks">
                {data.directions.map((d) => (
                  <li key={d.code}>
                    <strong>{d.code}</strong> — {d.name}
                    {d.programs > 0 && ` (программ: ${d.programs})`}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}

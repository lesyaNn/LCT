import type { Me } from "../types";

export type { Me } from "../types";

export function UserCard({ me }: { me: Me }) {
  const roles = me.roles ?? [];
  const permissions = me.permissions ?? [];
  return (
    <div className="card">
      <h2>Вы вошли в систему</h2>
      <dl className="kv">
        <div><dt>Имя</dt><dd>{me.name ?? "—"}</dd></div>
        <div><dt>Email</dt><dd>{me.email ?? "—"}</dd></div>
        <div><dt>Username</dt><dd>{me.username ?? "—"}</dd></div>
      </dl>
      <h3>Роль</h3>
      <div className="chips">
        {roles.map((r) => (
          <span key={r} className="chip">{r}</span>
        ))}
      </div>
      <h3>Права</h3>
      <ul className="perms">
        {permissions.map((p) => (
          <li key={p}>• {p}</li>
        ))}
      </ul>
    </div>
  );
}

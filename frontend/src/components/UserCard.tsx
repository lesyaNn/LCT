export type Me = {
  id: string;
  username: string | null;
  email: string | null;
  name: string | null;
  roles: string[];
  permissions: string[];
};

export function UserCard({ me }: { me: Me }) {
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
        {me.roles.map((r) => (
          <span key={r} className="chip">{r}</span>
        ))}
      </div>
      <h3>Права</h3>
      <ul className="perms">
        {me.permissions.map((p) => (
          <li key={p}>• {p}</li>
        ))}
      </ul>
    </div>
  );
}

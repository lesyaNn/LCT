#!/bin/sh
# Backend entrypoint: wait for PostgreSQL, run Alembic, start API.
# Race-free: postgres healthcheck in compose + retry loop here (60s),
# single backend replica runs migrations (no concurrent writers).
set -e

if [ -n "$DATABASE_URL" ]; then
  echo "[entrypoint] waiting for database..."
  python - <<'EOF'
import os, socket, time, urllib.parse
url = os.environ["DATABASE_URL"]
p = urllib.parse.urlparse(url)
host, port = (p.hostname or "localhost"), (p.port or 5432)
for i in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] database reachable at {host}:{port}")
            break
    except OSError:
        if i == 59:
            raise SystemExit(f"[entrypoint] database {host}:{port} unreachable after 60s")
        time.sleep(1)
EOF
  echo "[entrypoint] alembic upgrade head..."
  python -m alembic upgrade head
else
  echo "[entrypoint] DATABASE_URL not set, skipping migrations (SQLite dev mode)."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000

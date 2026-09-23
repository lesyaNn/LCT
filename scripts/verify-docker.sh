#!/bin/bash
# P5-10-02: верификация `docker compose up -d --build` с нуля.
# Проверки: build+up, healthchecks, HTTP сервисов, миграции, smoke-тест.
set -euo pipefail

echo "=== Docker Compose Verification ==="

# 1. Build & Up
echo "--- [1/5] docker compose up -d --build"
docker compose up -d --build

# 2. Wait for healthy
echo "--- [2/5] wait for healthy"
./scripts/wait-healthy.sh 300

# 3. HTTP checks
echo "--- [3/5] HTTP checks"
curl -sf http://localhost:8000/health > /dev/null \
  && echo "  backend :8000/health: OK"
curl -sf http://localhost:3000/health > /dev/null \
  && echo "  frontend :3000/health: OK"
curl -sf http://localhost:8081/realms/rtk > /dev/null \
  && echo "  keycloak :8081 realms/rtk: OK"

# 4. DB migration check (backend entrypoint применяет SQL-миграции на старте)
echo "--- [4/5] migration check"
docker compose exec -T backend python scripts/migrate.py status \
  && echo "  migrations: OK"

# 5. Smoke test (нужен access token: см. scripts/smoke_test.py --help)
echo "--- [5/5] smoke test"
if [ -n "${SMOKE_TOKEN:-}" ]; then
  python3 scripts/smoke_test.py --token "$SMOKE_TOKEN"
else
  echo "  SKIP (no SMOKE_TOKEN): прогоните вручную:"
  echo "    python3 scripts/smoke_test.py --token <Keycloak access token>"
fi

echo "=== All checks passed ==="

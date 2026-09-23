#!/bin/bash
# P5-18-01: backup demo mode — полный локальный стек без внешнего интернета.
# Внешних LMS/сайта нет: backend работает на встроенных данных seed,
# Keycloak локальный (realm rtk), файлы — локальный volume.
set -euo pipefail

echo "Setting up Backup Demo Mode (fully local, no internet required)..."

# 1. Копия env (пароли для демо)
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env created from .env.example (отредактируйте пароли при желании)"
fi

# 2. Запуск всего стека
docker compose up -d --build

# 3. Ожидание здоровья
./scripts/wait-healthy.sh 300

# 4. Seed демо-данных (идемпотентно; только после migrate на старте backend)
echo "Loading demo seed (idempotent)..."
docker compose exec -T backend python -m app.db.seed || {
  echo "  WARN: seed failed — проверьте логи backend (docker compose logs backend)"
}

echo ""
echo "Demo ready (offline-capable):"
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000/docs"
echo "  Keycloak:  http://localhost:8081"
echo "  Users:     admin/admin123, manager/manager123, curator/curator123, user/user123"
echo ""
echo "Smoke (нужен токен из браузера):"
echo "  SMOKE_TOKEN=<token> ./scripts/smoke.sh"

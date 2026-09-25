#!/bin/bash
# P5-17-01: bash-обёртка над smoke_test.py.
# Использование: SMOKE_TOKEN=<token> ./scripts/smoke.sh [--instance UUID --stage UUID]
set -euo pipefail

if [ -z "${SMOKE_TOKEN:-}" ]; then
  echo "Нужен SMOKE_TOKEN (Keycloak access token из браузера после логина):"
  echo "  SMOKE_TOKEN=<token> ./scripts/smoke.sh"
  exit 2
fi

docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Health}}'
python3 scripts/smoke_test.py --token "$SMOKE_TOKEN" "$@"

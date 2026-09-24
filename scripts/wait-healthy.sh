#!/bin/bash
# P5-10-02: ожидание healthy-статуса всех compose-сервисов.
# Использование: ./scripts/wait-healthy.sh [timeout_sec]
# Только новые файлы — существующий стек не меняется.
set -euo pipefail

TIMEOUT="${1:-300}"
POLL=5
ELAPSED=0

echo "Waiting for compose services to become healthy (timeout ${TIMEOUT}s)..."

while true; do
  NOT_READY=$(docker compose ps --format '{{.Name}} {{.Health}} {{.Status}}' \
    | awk '$2 != "" && $2 != "healthy" {print $1" ("$2")"} $2 == "" && $3 !~ /Up|running/ {print $1" ("$3")"}' || true)
  if [ -z "$NOT_READY" ]; then
    echo "All services healthy:"
    docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Health}}'
    exit 0
  fi
  if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    echo "Timeout waiting for healthy services. Current state:"
    docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Health}}'
    echo "Not ready: $NOT_READY"
    exit 1
  fi
  echo "  ...not ready yet: $NOT_READY"
  sleep "$POLL"
  ELAPSED=$((ELAPSED + POLL))
done

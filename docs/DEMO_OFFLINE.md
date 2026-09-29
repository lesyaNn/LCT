# Демонстрация без внешней сети

## Офлайн-прогон

```bash
./scripts/demo-setup.sh   # .env → up --build → wait-healthy → seed (идемпотентно)
```

Локально работают PostgreSQL, Redis и Keycloak (realm `rtk`, импорт из
`keycloak/realm-export.json`). Демонстрационные записи добавляет seed;
файлы хранятся в локальных volumes. Для основных сценариев CRM внешнее
подключение к LMS или сайту не требуется.

Единственное сетевое требование — Docker-образы (`postgres:16-alpine`,
`redis:7-alpine`, `keycloak:26.7.4`, `python:3.12-slim`): скачайте заранее
(`docker compose pull`) — дальше стенд работает без интернета.

Проверка после `demo-setup.sh`:

```bash
curl -sf http://localhost:8000/health && curl -sf http://localhost:3000/health
SMOKE_TOKEN=<токен-из-браузера> ./scripts/smoke.sh
```

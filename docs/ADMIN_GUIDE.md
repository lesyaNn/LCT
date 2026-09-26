# Руководство администратора (P5-15-01)

## 1. Пользователи и роли (Keycloak)
- Admin console: `http://localhost:8081` (логин из `KEYCLOAK_ADMIN`).
- Realm `rtk` импортируется из `keycloak/realm-export.json` на пустых данных
  (`start-dev --import-realm`, стратегия IGNORE_EXISTING).
- Роли realm: `admin`, `manager` (Руководитель), `user`.
- Клиент `rtk-frontend` (public, PKCE S256). Токен содержит `aud=rtk-api`
  через scope `rtk-api-audience`; backend проверяет подпись/exp/iss/aud по JWKS.
- Демо-пользователи: admin/manager/user (пароли `*123`).

## 2. Шаблоны workflow
- CRUD шаблонов/этапов через `/api/v1/workflow/*` (права admin/manager).
- Переходы только вперёд, с `expected_revision` и append-only историей.

## 3. Каталоги
- Directions / Programs / Products / Vendors / Responsibles — CRUD
  (`/api/v1/directions`, `/programs`, `/products`, `/vendors`, `/responsibles`).
- После изменений каталогов инвалидируйте кэш `catalogs:*`
  (см. `backend/app/services/cache.py`).

## 4. Импорт XLSX
- Staging в `/tmp/rtk-imports` (volume `import-staging` переживает рестарты).
- Тяжёлая обработка — в worker'е (`xlsx_import` jobs).

## 5. Мониторинг и логи
- `docker compose ps` + `./scripts/wait-healthy.sh` — здоровье.
- `docker compose logs -f backend worker frontend keycloak`.
- Smoke: `SMOKE_TOKEN=<token> ./scripts/smoke.sh`.

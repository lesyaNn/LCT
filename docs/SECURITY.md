# Безопасность

## Модель
- Аутентификация: Keycloak OIDC, JWT RS256, проверка signature/exp/iss/aud по JWKS.
- Fail-closed: `AUTH_DEV_BYPASS=false` в compose (обход только в тестах с моком JWKS).
- Авторизация: RBAC-роли + university scope (`university_responsibles.keycloak_sub`).

## Меры
- Секреты только через `.env` (образец — `.env.example`), никогда в коде.
- PostgreSQL/Redis не публикуются наружу (internal expose).
- CORS: только `FRONTEND_ORIGIN`; API принимает `Authorization`, `Content-Type`.
- Загрузки: лимит 50MB, опциональный allowlist расширений, MIME записывается как заявлен.
- Non-root: backend (`appuser`), минимальные образы (`-alpine`/`-slim`).
- Логи без секретов; JSON-лимит 10m×3.

## 152-ФЗ / ФСТЭК
- ПДн: минимум (ФИО/email/телефон ответственных и преподавателей, студенты —
  только учебные атрибуты без избыточных ПДн).
- Аудит действий: append-only (`audit_events`, `workflow_stage_transitions`).
- Резервное копирование: volumes `pgdata` + `pg_dump` (см. INSTALL.md).

## Инциденты
1. Отозвать компрометированные секреты (сменить в `.env`, пересоздать контейнеры).
2. Проверить audit log на аномалии.
3. Перевыпустить Keycloak credentials при необходимости.

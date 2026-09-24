# SQLite-дефолт (M10): test-only, PG — единственная прод-БД

## Контракт

- `app/config.py: database_url = "sqlite:///./dev.db"` — дефолт **только для
  локальных юнит-тестов и скриптов без схемы**. Это удобство, а не поддержка
  второй СУБД.
- `backend/migrations/*.up.sql` — PostgreSQL-native DDL (`TIMESTAMPTZ`,
  native UUID, JSONB); `scripts/migrate.py` **отказывается** работать на
  SQLite (`SystemExit`, fail-closed).
- Контейнер (`backend/entrypoint.sh`, `set -e`) без `DATABASE_URL` **не
  стартует** (fail-closed): `baseline → up → verify`, затем uvicorn.

## Что это значит на практике

| Запуск | БД | Поведение |
| --- | --- | --- |
| `pytest backend/tests` без `TEST_DATABASE_URL` | — | pure-unit зелёные; `*_pg.py` skipped |
| `pytest` с `TEST_DATABASE_URL=.../rtk_test` | PG test | полный E2E; guard имени БД (M6) |
| `uvicorn app.main:app` без `DATABASE_URL` | SQLite dev.db | API поднимется, но схема дрейфует от PG — **только для ручной отладки без БД** |
| `docker compose up` | PG `rtk` | единственный прод-путь |

## Требование к API (владелец — Dev-2, `app/`)

При старте API без PostgreSQL (SQLite-дефолт активен) требуется:
1. loud warning в лог на старте (`SQLite default active — schema drift from
   PostgreSQL, test-only`);
2. `GET /ready` → degraded-статус (не `200 ok`), чтобы оркестратор не лил
   трафик на узел без настоящей схемы.

До реализации в `app/` этот документ + `test_p5_sqlite_default_guard.py`
фиксируют контракт снаружи: дефолт не должен тихо стать прод-путём.

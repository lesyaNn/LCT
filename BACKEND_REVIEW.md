# Backend Review

Дата ревью: 2026-09-24. Ветка: `develop` (commit `9d6077a`, после `git pull origin develop`).
Метод: статический анализ кода + сверка каждой задачи из `hackathon_rostelecom_tasks/tasks/{p1,p2,p4,p5}` с фактической реализацией. Код не изменялся. Живой стенд (Postgres/Redis/Keycloak), `docker compose up`, нагрузочные прогоны не выполнялись — PG-gated тесты локально скипаются, такие пункты помечены `NEEDS VERIFICATION`. Фронтенд-критерии и фронтенд-задачи не учитываются (по указанию): backend-часть оценивается отдельно, клиентские UI (чекбоксы, polling, Dashboard/матрица-рендер, PNG-кнопки, TanStack/zustand) не снижают статус.

---

## 1. Executive Summary

Backend — модульный монолит на FastAPI + SQLAlchemy 2.0 (sync) + PostgreSQL 16, Keycloak JWT-аутентификация (RS256/JWKS), RBAC + data-scope политики, единый формат ошибок `ErrorResponse{code,message,request_id,details}`, audit через `audit_events` + outbox-relay, worker-контейнер для отчётов/импорта (`SKIP LOCKED`, ретраи x3), Redis-кэш с in-memory fallback. Миграции — raw SQL `backend/migrations/000001..000023`, Alembic архивирован. OpenAPI генерируется (56 paths), CI `.github/workflows/backend.yml` существует.

Основные сильные стороны:

- Сквозные механизмы централизованы: `app/core/security.py` (JWKS TTL 600с, kid-refresh, iss/aud/exp, fail-closed), `app/core/permissions.py`, `app/core/policies.py` (`OWN/GROUP/ALL/DENY`, `apply_university_scope`, 403 vs 404), `app/core/errors.py` + `app/schemas/errors.py` (реестр кодов + RU-сообщения + `security-errors.json`), `app/modules/audit/service.py` (без commit, sanitize).
- Health Score полностью детерминирован: `health_score/aggregate.py` (веса 0.25/0.20/0.20/0.20/0.15), `tasks_score/documents_score/stages_score/educators_score/launch_score`, `status.py` (пороги 85/60), `health_service.calculate_health_score` (breakdown/reasons/counters).
- Паспорт вуза оптимизирован: batched SELECT по блокам, `?include=health_score` +0 запросов (in-memory), `?include=audit` +1, лимиты 20/10, subresources.
- P4 backend почти полон: `UnifiedFilter` везде, dataset 14 колонок + `resolve_columns`/пресеты, XLSX/PDF/JSON экспортёры, `report_jobs` леджер + worker, `/analytics/overview|matrix`, импорт preview/mapping/validation/savepoint на строку/error-report XLSX.
- P5 baseline закрыт: secrets из env, CORS allowlist + prod fail-closed, `RequestSizeLimit + SecurityHeaders`, upload 50MB + sanitize + containment, ORM-only, `SensitiveFilter` в логах, pinned deps, `SECURITY_ALIGNMENT.md` (152-ФЗ/ФСТЭК, честный дисклеймер).

Основные проблемы:

- 2 CRITICAL в импорте: (1) `file_id` от клиента без валидации → path traversal за `STAGING_DIR` (`imports/service.py:_staged_path`); (2) `POST /import/preview` читает весь файл в RAM до проверки лимита (OOM при параллельных аплоадах).
- Долгая единая транзакция импорта (до 5000 строк × ~10 SELECT, один commit) + молчаливый truncate после 100 ошибок без флага `truncated`.
- Пост-коммит writers глотаются `except: pass` (`workflow_transitions/service.py`) → дрейф `health_score_current`/снапшотов vs API.
- Аудит молча no-op без `audit_context`, часть роутов на голом `get_db` (паспорта, скачивание файлов).
- Бизнес-логика и SQL в `GET /catalog/overview`, scope применяется не везде (глобальные счётчики для scoped-пользователя), scope-проверка после SELECT в detail (лишний SELECT + timing-oracle).
- Redis: коннект на импорте, глобалы, доступ к приватному `_memory`, `delete` без try. Параллельно живут две очереди: канонический `report_jobs` и мёртвый `task_queue` (O(N) dedup, 48-бит ID, без атомарности).
- Немало quarantine/mёртвого кода в образе (`programs/documents/identity/dashboard/reporting/workflow/*`, `teachers/router`, `limit(200)` без пагинации, `FileOut.storage_key` — утечка если смонтируют).
- Внешние интеграции P5-07/08/09 не реализованы (только стаб `integrations/router`): нет `LMSAdapter/WebsiteAdapter`, Mock/Http, `ImportNormalizer/WorkflowImporter`. Нет Keycloak Admin API клиента. Нет артефактов прогонов load/smoke/docker-верификации (только скрипты + Locust-файлы).

Подсчёт проблем: **CRITICAL — 2, HIGH — 8, MEDIUM — 10, LOW — 7**.

Выполнение задач backend (всего 129, фронтенд не учитывается): **DONE — 85, PARTIAL — 41, NOT DONE — 2, BLOCKED — 1** (P5-12-02 — чисто фронтенд-задача, исключена из backend-оценки; детали — разделы 3 и 15).

---

## 2. Project Overview

### Компоненты

```text
backend/app/main.py                  FastAPI, CORS allowlist, RequestSizeLimit+SecurityHeaders,
                                     request_log_middleware, register_error_handlers, custom_openapi
                                     (BearerAuth, теги, error-examples), /health, /ready
backend/app/api/router.py            агрегатор v1 (/api/v1), ~15 роутеров; порядок важен
                                     (health_router до catalog чтобы /health-score не съедался /{id})
backend/app/modules/*/              домены: router + service + repository + schemas (канон);
                                     часть — deferred/stub, НЕ смонтированы (quarantine guard)
backend/app/core/                    errors, exceptions, security (JWT), permissions (RBAC),
                                     policies (data-scope), logging (SensitiveFilter),
                                     middleware, pagination (dead)
backend/app/models/                  ORM на Base; DeferredBase для stub-моделей вне миграций
backend/app/schemas/                 контракт: common, catalog, university, teacher, licenses, errors
backend/app/db/                      session (engine/SessionLocal), seed, seed_workflow
backend/app/services/                чистые функции: cache, license_status, teacher_readiness
backend/app/infrastructure/          redis, storage (local/S3), http_client, task_queue (dead)
backend/app/workers|modules/analytics/report_worker.py  воркер отчётов (SKIP LOCKED, x3)
```

Активные домены: `auth`, `universities/passport`, `teachers/passport`, `catalog` (universities/directions/programs/products/vendors/responsibles + overview), `meetings`, `students`, `workflow_templates`, `workflow_instances`, `workflow_transitions`, `workflow_attachments`, `health_score` (health/ranking/attention/history/materialization), `analytics` (overview/matrix + reports: xlsx/pdf/json + jobs/worker), `imports` (preview/execute/jobs/report), `audit` (+relay/outbox).

### Технологии

- API: `FastAPI==0.116.1`, `uvicorn[standard]`, `Pydantic==2.11.7`, `pydantic-settings`, `python-multipart`.
- Auth: `Keycloak 26.7.4` (realm `rtk`, client `rtk-frontend`, PKCE), `python-jose[cryptography]`, RS256 JWKS, RBAC `admin/manager/curator/user`.
- DB: `PostgreSQL 16`, `SQLAlchemy==2.0.43`, `psycopg[binary]`, raw SQL миграции `000001..000023` + `schema_migrations`, Alembic только архив. `Redis==6.4.0`, `MinIO` (S3-seam, default local).
- Отчёты/импорт: `openpyxl`, `xlrd`, `reportlab` (+`fonts-dejavu-core`), `httpx`, `python-dateutil`.
- Тесты/линт: `pytest==9.0.3`, `ruff` (line-length 100), pure-unit без PG vs интеграция через `TEST_DATABASE_URL` (`DROP SCHEMA + up` изоляция в `conftest/db_helpers`).
- Инфра: `docker-compose.yml` (postgres, redis, keycloak:8081, backend, worker, frontend), `backend/Dockerfile` multistage (`appuser:10001`), `frontend` React 18 + Vite, nginx same-origin `/api/` прокси. CI `.github/workflows/backend.yml` (lint, unit, postgres, openapi, smoke).

### Точки входа / БД / внешние сервисы

- Entrypoint: `backend/entrypoint.sh` ждёт PG → `migrate.py baseline` (адопт legacy Alembic) → `up` → `verify` → `uvicorn app.main:app --proxy-headers`. Без `DATABASE_URL` — `exit 1`.
- БД: 21 таблица ядра P1 + 8 workflow + `report_jobs/import_jobs/job_attempts/audit_events(+p5)/health_score_current/health_score_snapshots/audit_outbox`. PK UUID генерит приложение, даты `timestamptz`.
- Внешние: живых LMS/Website нет (стаб deferred); S3 — реальный `S3StorageBackend`, default local `/app/storage`; Redis — кэш/health/ Bay; Keycloak — единственный IdP.

---

## 3. Tasks Review

| Priority | Task | Status | Evidence | Notes |
| -------- | ---- | ------ | -------- | ----- |
| P1 | P1-01-01 | DONE | `app/models/catalog.py`, `migrations/000001_core_catalog.up.sql`, `000002_contracts_licenses.up.sql` | 9 таблиц, именованные FK/unique/index, M2M без `responsible_id` |
| P1 | P1-01-02 | DONE | `app/models/teachers.py`, `migrations/000003_teachers.up.sql` | CASCADE qualifications/certificates, unique teacher_programs; program-side RESTRICT — правильно |
| P1 | P1-01-03 | DONE | `app/models/interactions.py`, `migrations/000004_students_links.up.sql`, `000005_interactions.up.sql` | 6 таблиц + meeting_documents, CHECK single-link, минимум ПДн |
| P1 | P1-01-04 | PARTIAL | `alembic/README_ARCHIVED.md`, `scripts/migrate.py`, `scripts/check_migrations.py` | Alembic архивирован сознательно; AC `alembic upgrade head` буквально не выполняется; эквивалент — raw SQL + guard |
| P1 | P1-01-05 | DONE | `app/models/mixins.py::TimestampMixin`, все модели наследуют | tz-aware, server_default func.now, без utcnow |
| P1 | P1-02-01 | DONE | `app/schemas/university.py`, `modules/universities/passport_schemas.py` | Нейминг-дрейф Read/List, набор полей эквивалентен |
| P1 | P1-02-02 | DONE | `app/schemas/catalog.py` | 4 каталога ×5 схем + Short + счётчики |
| P1 | P1-02-03 | DONE | `app/schemas/teacher.py`, `modules/teachers/passport_schemas.py`, `models/enums.py::TeacherReadiness` | `trainings` отсутствует — санкционировано MVP (нет таблицы) |
| P1 | P1-02-04 | DONE | `app/schemas/common.py`, `app/schemas/errors.py` | Все enum + аддитивный CURATOR |
| P1 | P1-02-05 | DONE | `app/main.py`, `app/api/router.py`; OpenAPI 56 paths строится | `check_openapi.py` нет, есть `test_p5_openapi_docs.py` |
| P1 | P1-03-01 | DONE | `modules/catalog/router.py`, `service.list_university_page`, `require_permission` + `apply_university_scope` | Legacy `modules/universities/router.py` не смонтирован — мёртвый код |
| P1 | P1-03-02 | DONE | catalog `/directions` ×5, `delete_direction` RESTRICT→409 | Полно |
| P1 | P1-03-03 | DONE | catalog `/programs` ×5, direction_id обязателен | Полно |
| P1 | P1-03-04 | DONE | catalog `/products` ×5, unique (vendor,name,version) | Полно |
| P1 | P1-03-05 | DONE | catalog `/vendors`×5 + `/responsibles`×5 | Полно |
| P1 | P1-03-06 | PARTIAL | `schemas/common.py::PaginationParams/PaginatedResponse/FilterBase` | Нет TeacherFilter/teacher-листа; meetings/students без фильтров |
| P1 | P1-04-01 | DONE | `modules/universities/passport_router.py`, `passport_service.py::get_passport` | Batched SELECT, N+1 нет по конструкции |
| P1 | P1-04-02 | DONE | `passport_service.py` (counts via GROUP BY, readiness общая функция) | Полно |
| P1 | P1-04-03 | DONE | `passport_service.py` + `services/license_status.py` | Полно |
| P1 | P1-04-04 | DONE | `passport_service.py` (docs 20, meetings 10, timeline) | Полно на чтение кода |
| P1 | P1-04-05 | DONE | `passport_service.py::parse_include`, `test_passport_include.py` | health +0 запросов, audit +1, graceful degradation |
| P1 | P1-04-06 | PARTIAL | `passport_service.py` docstring 8 statements, subresources, индексы | Runtime ≤8/<500ms только PG-gated, без живого PG не подтверждено — NEEDS VERIFICATION |
| P1 | P1-05-01 | DONE | `modules/teachers/passport_router.py` + service (4 SELECT, 404, RBAC) | Полно |
| P1 | P1-05-02 | PARTIAL | `passport_service.py::_load_*` | Сортировки не по спеке (по expires, не mandatory-first/obtained); trainings нет (MVP) |
| P1 | P1-05-03 | DONE | `services/teacher_readiness.py::compute_teacher_readiness` | Чистая функция; переиспользование P2 — через дублирование, единый источник под вопросом |
| P1 | P1-06-01 | DONE | `models/catalog.py::License/Contract` | Все поля ТЗ, вендор через product |
| P1 | P1-06-02 | DONE | `services/license_status.py`, `schemas/licenses.py`, `test_p1_derived_status.py` 10 passed | Contract expires_soon→active (спека разрешает); enum содержит EXPIRES_SOON, сервис не возвращает — расхождение |
| P1 | P1-07-01 | PARTIAL | `modules/meetings/*`, `models/interactions.py` | CRUD есть; нет фильтров type/date_from/date_to |
| P1 | P1-08-01 | PARTIAL | `models/interactions.py::Student`, `modules/students/*` | DELETE hard вместо soft expelled; лист без фильтров status/program |
| P1 | P1-09-01 | PARTIAL | `app/db/seed.py` (10 вузов, _get_or_create) | Распределение 3/4/3 не зафиксировано тестом; <30с NEEDS VERIFICATION |
| P1 | P1-09-02 | PARTIAL | `seed.py::LICENSE_EXPIRY`, `test_p1_seed_problem_zones.py` | Прогресс workflow не сидируется (вынесено в P2) |
| P1 | P1-09-03 | DONE | `seed.py::TEACHER_PLAN`, `test_p1_seed_teachers.py` | AC числа противоречивы (30 vs таблица 34); реализация 34 (18/5/11) зафиксирована |
| P1 | P1-10-01 | DONE | `migrations/*.up.sql` + `models/*.py` (MISSING 0) | Все индексы + композиты |
| P1 | P1-10-02 | PARTIAL | `scripts/explain_passport.py`, `check_explain.py`, `seed_performance.py` | Артефактов прогона нет; без PG недоказуемо |
| P1 | P1-11-01 | PARTIAL | `tests/test_p1_03*`, `test_p1_crud.py`, `test_p1_07_08*` | sqlite 19 passed, 152 skipped (PG-gated); покрытие >80% не измерено |
| P1 | P1-11-02 | PARTIAL | `test_p1_11_02*`, `test_p1_05*`, `test_passport_*` | Кейсы покрыты кодом тестов, без PG не исполнялись |
| P1 | P1-11-03 | PARTIAL | `test_p1_11_03_licenses_filters.py` | Часть фильтров pinned NOT IMPLEMENTED; dedicated license/contract CRUD нет |
| P1 | P1-12-01 | DONE | `docs/mocks/university-passport.json`, `teacher-passport.json`, `scripts/generate_mocks.py`, `test_p1_mocks.py` passed | health/workflow плейсхолдеры, задокументировано |
| P2 | P2-01-01 | PARTIAL | `migrations/000011_workflow_templates.up.sql` | Нет is_default/created_by; estimated→sla_days; имена не по ТЗ |
| P2 | P2-01-02 | PARTIAL | `000012+000013`, `workflow_instances/service.py:create_instance`, `overdue.py` | Нет partial unique active; нет template_version/created_by_sub; указатель вместо current_stage семантики |
| P2 | P2-01-03 | PARTIAL | `000012`, `000016`, `000017` | Переименованная схема (нет user_name/due_date/document_id); иммутабельность соглашением, без REVOKE/trigger |
| P2 | P2-01-04 | PARTIAL | `app/db/seed_workflow.py::STAGES_14` | Имена из README не из ТЗ; optional только этап 5 (надо 10,12); sla NULL; нет is_default |
| P2 | P2-02-01 | PARTIAL | `modules/workflow_templates/router.py` (admin-only, пагинация) | Нет логики is_default (нет колонки) |
| P2 | P2-02-02 | DONE | `workflow_templates/service.py` (сдвиг в транзакции, DEFERRABLE), `test_p2_11_04` | DELETE=retire via is_active |
| P2 | P2-02-03 | PARTIAL | `workflow_instances/service.py` | DTO без progress_percent/overdue_count/university/template_name; template_id обязателен (нет default fallback) |
| P2 | P2-02-04 | DONE | service + тесты rename/reorder/add/disable | Снапшоты старых инстансов не трогаются |
| P2 | P2-03-01 | DONE | `workflow_transitions/service.py:transition_instance`, router | Одна транзакция + audit; код WORKFLOW_INVALID_TRANSITION via handler |
| P2 | P2-03-02 | PARTIAL | `service.py:validate_transition` | Нет admin-override (осознанное отклонение, снапшотная модель) |
| P2 | P2-03-03 | PARTIAL | `WorkflowStageTransition` в той же транзакции | Нет user_name/due_date; transitioned_at=created_at; иммутабельность соглашением |
| P2 | P2-03-04 | DONE | `AuditService.enqueue_event(WORKFLOW_TRANSITION)` в той же транзакции, post-commit try/except | request_id via context_for |
| P2 | P2-04-01 | DONE | `workflow_transitions/service.py` (автор ≤15мин или admin, COMMENT_EDIT_WINDOW 900) | is_system→is_internal |
| P2 | P2-05-01 | PARTIAL | `workflow_attachments/service.py` (chunks 256KiB), `policy.py` 50MiB, sanitize, Local/S3 | Allowlist открыт по умолчанию (пусто=accept-all); зафиксировано тестом как PARTIAL |
| P2 | P2-05-02 | DONE | router+service open_download streaming, delete с правами + физическое удаление | 404/403/идемпотентный delete покрыты |
| P2 | P2-05-03 | DONE | `policy.py` (50MiB ровно OK/+1→413, sanitize ../../, NUL) | Имена env отличаются, поведение по ТЗ |
| P2 | P2-05-04 | DONE | `workflow_attachments/storage.py::StorageBackend` + Local + S3 + factory | S3 реален, не заглушка |
| P2 | P2-06-01 | DONE | `workflow_instances/overdue.py`, `service.stage_due_dates`, completed_at | Отклонение: поздно завершённый → (True,late), для S корректнее |
| P2 | P2-07-01 | DONE | `health_score/aggregate.py::WEIGHTS`, `aggregate_scores`, `test_p2_07_01` | Детерминировано, без ML |
| P2 | P2-07-02 | DONE | `health_score/tasks_score.py::calc_T`, `test_p2_07_02` | -8/-4, min 0, пусто→100 |
| P2 | P2-07-03 | DONE | `health_score/documents_score.py::calc_D` | Только обязательные типы из settings |
| P2 | P2-07-04 | DONE | `health_score/stages_score.py::calc_S` | Нет instance→100 |
| P2 | P2-07-05 | DONE | `health_score/educators_score.py::calc_E` via teacher_readiness | Только активные программы |
| P2 | P2-07-06 | DONE | `health_score/launch_score.py::calc_L` 100/70/40/0 | Среднее, пусто→100 |
| P2 | P2-07-07 | DONE | `health_score/status.py::get_health_status` ≥85/≥60 | Single source (используется и в PDF) |
| P2 | P2-07-08 | DONE | `health_score/health_service.py::calculate_health_score` | breakdown + 6 кодов reasons + counters + tz |
| P2 | P2-08-01 | DONE | `health_score/health_router.py GET /universities/{id}/health-score`, cache TTL 300, инвалидация | <200ms NEEDS VERIFICATION |
| P2 | P2-08-02 | DONE | `GET /universities/health-score?ids=` max50→422, порядок, per-item кэш | Последовательно вместо gather — обосновано (sync Session) |
| P2 | P2-08-03 | DONE | `health_score/ranking_router.py GET /health-score/ranking`, row_number, TTL 600 | Опциональная — реализована |
| P2 | P2-09-01 | PARTIAL | `000015_health_snapshots`, `GET .../history`, `snapshots.py`, `materialization.py` | Нет планировщика (только функция + pre-step worker); event только transition; нет ретенции |
| P2 | P2-10-01 | DONE | `health_score/attention.py::get_attention_items` 5 правил, severity, max20 | Правило 1 pending (current via указатель — корректно) |
| P2 | P2-10-02 | DONE | `GET /universities/{id}/attention-items`, кэш 300с | Тонкая обёртка |
| P2 | P2-11-01 | PARTIAL | `test_p2_11_01_transition.py` 15 passed | Нет 401/403/404/archived→409, пропуск-на-skipped в явном виде |
| P2 | P2-11-02 | PARTIAL | `test_p2_11_02_upload_overdue.py` | Тип-контракт PARTIAL by design; нет пустой файл/без расширения |
| P2 | P2-11-03 | DONE | `test_p2_11_03_edge.py` (границы, пусто→100, детерминизм 50 runs) | ТЗ просит 100 runs — сделано 50 |
| P2 | P2-11-04 | DONE | `test_p2_11_04_template_edit.py` (reorder/rollback/FOR UPDATE/parallel/RBAC) | Самая полная группа |
| P2 | P2-12-01 | PARTIAL | `scripts/generate_p2_mocks.py`, `backend/docs/mocks/workflow-instance.json+health-score.json`, `test_p2_12_01` pass | Лежат в backend/docs/mocks а не docs/mocks; instance 7 этапов не 14 |
| P4 | P4-01-01 | DONE | `analytics/filters.py::UnifiedFilter`, `filter_service.py`, `get_unified_filter`, `test_p4_01_01` | 8 измерений, date_from<=date_to→422 |
| P4 | P4-01-02 | DONE | `catalog/router+repository` на UnifiedFilterService, `report_request.filters`, `dev1_provider`, `analytics.py` | router идёт via FilterProvider.normalize — семантика та же |
| P4 | P4-02-01 | DONE | `analytics/columns.py::MANDATORY_COLUMNS` 14 шт, `dataset.py` (University×License + fallback, health из current) | Не SELECT *, JOIN только нужное |
| P4 | P4-02-02 | DONE | `columns.py::resolve_columns` + PRESETS MINIMAL/STANDARD/FULL; экспортёры уважают | Backend DONE; фронтенд чекбоксы/пресеты не учитываются |
| P4 | P4-03-01 | DONE | `analytics/reports_router.py POST →202`, `report_service.create_report_job`, `test_p4_03*` | persist→commit→реальный id |
| P4 | P4-03-02 | DONE | `analytics/xlsx.py` (2 листа, freeze A7, auto_filter, ширины, DD.MM.YYYY, atomic .part) | A7:X7 из ТЗ осознанно исправлено |
| P4 | P4-04-01 | DONE | `analytics/pdf.py::generate_pdf_report` ReportLab landscape A4 (титул/KPI/таблица/timestamp) | ReportLab вместо WeasyPrint — допустимо |
| P4 | P4-04-02 | DONE | `pdf.py::find_dejavu/ensure_pdf_fonts`, `backend/Dockerfile fonts-dejavu-core` | Без шрифта → PDFFontUnavailableError, не mojibake |
| P4 | P4-05-01 | DONE | `analytics/json_export.py` (metadata/filters/columns/rows/totals, ensure_ascii=False, ISO8601) | totals avg/by_health корректны |
| P4 | P4-06-01 | DONE | `analytics/report_jobs.py` (claim SKIP LOCKED, ретраи x3, cleanup 24ч, RBAC job_visible_to), `report_worker.py`, compose worker | BackgroundTasks запрещены — соблюдено |
| P4 | P4-06-02 | DONE | Backend: GET status + download FileResponse (409/410/403) | Backend DONE; фронтенд polling/кнопки не учитываются |
| P4 | P4-07-01 | DONE | `analytics/router.py GET /overview` Redis 60с, `service.build_overview` (KPI/5 бакетов/14 этапов/4 статуса/топ-10/trend) | health_avg=0 при пусто (не null) — мелкое расхождение |
| P4 | P4-08-01 | DONE | Overview отдаёт 4 набора; отдельных /charts/* не требуется по ТЗ | Backend DONE; клиентский рендер не учитывается |
| P4 | P4-09-01 | DONE | `router GET /matrix` guard 50k, `service.build_matrix` (status/risk/LEGEND) | Cross-join ограничен via selection |
| P4 | P4-09-02 | DONE | Cell содержит teacher_readiness/license_status/progress/overdue/next_milestone | Backend DONE; фронтенд рендер не учитывается |
| P4 | P4-10-01 | DONE | `imports/router POST /preview` (headers+10 строк+row_count), `service stage xlsx+xls` 10МБ/5000, TARGET_FIELDS mapping | Mapping UI — P3-11-01 по докстрингу |
| P4 | P4-10-02 | DONE | `service.execute_import` savepoint/skip-bad/codes REQUIRED../лимит 100, `write_error_report` XLSX, idempotency_key | Скачивание GET /import/jobs/{id}/report |
| P4 | P4-10-03 | DONE | `imports/schemas.EXAMPLE_MAPPING` 10 полей, default версия 1.0, split ;/,, parse_date, transfer enum | Вендор required только если продукт указан |
| P4 | P4-11-01 | DONE | Графики встроены в PDF (`pdf.py`); canvas-экспорт есть в `AnalyticsCharts.tsx` | Backend-часть DONE; клиентские кнопки не учитываются |
| P4 | P4-12-01 | PARTIAL | `tests/test_p4_golden_seed.py` (инвариант list==dataset==overview==xlsx/json/pdf) | Чисел ТЗ (10/67/156) нет — докстринг фиксирует противоречивость; PG-only → skipped |
| P4 | P4-13-01 | PARTIAL | `backend/docs/performance/*explain.txt`, индексы, очередь, пороги в HANDOFF | Замеров p50/p95 фильтра+аналитики+10 параллельных на demo нет |
| P4 | P4-14-01 | DONE | `docs/mocks/report-request.json`, `analytics-overview.json`, используются AnalyticsCharts | Валидны, соответствуют спекам |
| P5 | P5-01-01 | DONE | `docker-compose.yml` keycloak 26.7.4 start-dev --import-realm, `keycloak/realm-export.json` realm rtk, rtk-frontend PKCE, roles admin/manager/curator/user | Переименовано vs ТЗ (it-school→rtk, порт 8081, лишний curator, directGrants false) — функционально закрыто |
| P5 | P5-01-02 | DONE | `realm-export.json` 4 users *123, `.env.example`, `app/config.py` из env | JWT_SECRET отсутствует корректно (RS256); .env в gitignore |
| P5 | P5-02-01 | DONE | `app/core/security.py::_fetch_jwks/_get_jwks` TTL 600, kid-refresh, RS256, iss/aud/exp, fail-closed | urllib вместо httpx, TTL 10мин вместо 1ч — несущественно |
| P5 | P5-03-01 | DONE | `core/permissions.py::USER_PERMISSIONS`, `policies.py` scope, `test_p5_http_matrix_pg` own=200/чужой=403-404 | Полно |
| P5 | P5-03-02 | DONE | `permissions.py::MANAGER`, matrix scope patch=200/вне=404 | Scope только university_ids из JWT, региона нет (зафиксировано в ALIGNMENT) |
| P5 | P5-03-03 | PARTIAL | `permissions.ADMIN`, `require_role(admin)`, templates ADMIN_CONFIG | Keycloak Admin API клиент отсутствует — user-mgmt только консоль (ADMIN_GUIDE) |
| P5 | P5-03-04 | PARTIAL | `test_p5_http_matrix_pg.py`, `test_p5_rbac_policy.py` | Только universities/meetings/students; нет teachers/workflow/reports/analytics/templates строк |
| P5 | P5-04-01 | DONE | `core/policies.py::ScopeKind/get_data_scope/apply_university_scope/ensure_university_access`, `test_p5_scope_pg` | Missing claim → fail-closed пустой scope |
| P5 | P5-04-02 | DONE | Тот же policies + `auth/dependencies.require_permission/require_role`, `docs/SECURITY.md` | Используется catalog/workflow/reports/audit |
| P5 | P5-05-01 | DONE | `modules/audit/models.py::audit_events` + индексы, `service.log_event` без commit | Переименовано logs→events, timestamp→created_at, entity_id UUID |
| P5 | P5-05-02 | PARTIAL | Пишут catalog/meetings/students/comments/transition/reports/templates | Нет LOGIN/LOGOUT; import/report только при audit_context; нет теста ровно-1-событие |
| P5 | P5-05-03 | DONE | `modules/audit/router.py GET /audit/events` фильтры+пагинация+DESC+scope, `test_p5_audit_pg` | Чужой university_id→403 |
| P5 | P5-06-01 | DONE | `schemas/errors.py::ErrorResponse`, `core/errors.py` handlers + X-Request-ID, `test_p5_unified_errors` | Полно |
| P5 | P5-06-02 | DONE | `schemas/errors.py` все 10 кодов + extras, ERROR_STATUS_MAP, RU MESSAGES, `docs/contracts/security-errors.json` synced | OpenAPI error-схемы в main.py |
| P5 | P5-07-01 | PARTIAL | `modules/integrations/router.py::LMSAdapter.to_internal` (1 метод, unmounted) | Нет fetch_programs/students/training_results/test_connection, нет app/integrations/lms/ |
| P5 | P5-07-02 | NOT DONE | grep LMS_ADAPTER/MockLMS/HttpLMS — пусто | Нет factory/lifecycle/env; демо на seed |
| P5 | P5-08-01 | NOT DONE | Тот же стаб else ok True | Нет WebsiteAdapter/DTO/env |
| P5 | P5-08-02 | PARTIAL | Намерение закрыто иначе: внешних вызовов нет, демо на seed без сети | Требуемых Mock*/ADAPTER=mock/startup-check нет |
| P5 | P5-09-01 | PARTIAL | XLSX-импорт (staging, constraints uq_students_external_id) | Нет ImportNormalizer/WorkflowImporter/normalize_lms_*/(external_id,source) upsert |
| P5 | P5-10-01 | DONE | `docker-compose.yml` 6 сервисов + healthchecks + volumes + rtk-net, `.env.example` | PG/Redis expose internal; лишний worker — улучшение (SKIP LOCKED) |
| P5 | P5-10-02 | DONE | `scripts/verify-docker.sh` + wait-healthy + `docs/P5_10_02_UP_FROM_ZERO.md` | Артефакта замера <3мин в репо нет — NEEDS VERIFICATION |
| P5 | P5-11-01 | DONE | `app/main.py custom_openapi` BearerAuth/tags/summary/error-examples//api/v1, `test_p5_openapi_docs` ≥85 ops | Полно |
| P5 | P5-12-01 | DONE | `app/services/cache.py` TTL catalogs/HS 300, analytics/list 60, invalidate_* поверх infrastructure.redis | Приватное без scope не кэшируется (scope-ключи) |
| P5 | P5-12-02 | BLOCKED | Чисто фронтенд-задача (TanStack Query + zustand/persist) | Исключена из backend-оценки по указанию; backend-кэш — P5-12-01 DONE |
| P5 | P5-13-01 | DONE | `config` secrets+prod fail-closed, CORS allowlist, middleware headers+413, attachments 50MB/sanitize, ORM-only, SensitiveFilter, exact pins, `test_p5_security_baseline` | Все 9 мер |
| P5 | P5-13-02 | DONE | `docs/SECURITY_ALIGNMENT.md` дисклеймер НЕ сертифицирован, таблицы 152-ФЗ/ФСТЭК, gaps | Полно |
| P5 | P5-14-01 | PARTIAL | `backend/tests/load/locustfile.py` 4 сценария веса 10/5/5/3/2, `-u50 -r10 -t2m`, `docs/P5_14_LOAD.md` | Нет HTML-артефакта/метрик; auth только LOCUST_TOKEN |
| P5 | P5-14-02 | PARTIAL | `tests/load/locustfile_reports.py` 202→poll→download timeout 60с | Нет артефакта/топа медленных |
| P5 | P5-15-01 | DONE | `README.md` + `docs/{USER_GUIDE,ADMIN_GUIDE,INSTALL,ARCHITECTURE,SECURITY,API_INTEGRATION,DEPENDENCIES}.md` | Короткие стабы 1.6–3.5KB, без скриншотов, ER текстом, не встроены в /docs |
| P5 | P5-16-01 | DONE | `docs/archimate/architecture.archimate` + .png 61KB + render + README + Mermaid | 8 слоёв, worker выделен |
| P5 | P5-17-01 | DONE | `scripts/smoke_test.py` stdlib 7 проверок + `smoke.sh` + CI smoke | Нужен --token (без direct grants), transition только с --instance --stage |
| P5 | P5-18-01 | PARTIAL | `scripts/demo-setup.sh` + `docs/DEMO_OFFLINE.md` (после pull без сети), локальный Keycloak/seed/volumes | Нет ADAPTER=mock, нет demo-backup.mp4 |

### P1

P1 ядро закрыто (23 DONE / 15 PARTIAL). Архитектурное отклонение P1-01-04 (Alembic→raw SQL) задокументировано и покрыто guard-тестами. Главные гэпы: отсутствие фильтров meetings/students/teacher-листа (бьёт P1-03-06/07-01/08-01), hard-delete студентов вместо soft, сортировки teacher-passport не по спеке, перф-доказательства (N+1 ≤8, <500ms, EXPLAIN) только кодом без живого PG. Seed: числа P1-09-03 противоречивы в самой спеке (30 vs таблица 34) — реализация следует таблице (34) и зафиксирована тестами.

### P2

Workflow + Health Score закрыты (21 DONE / 16 PARTIAL). Формула T/D/S/E/L, пороги, breakdown/reasons/counters, endpoints + кэш, attention 5 правил — DONE. Системные гэпы: нет partial unique active instance (возможен 2-й active), нет admin-override в validate_transition (осознанно, снапшотная модель), иммутабельность transitions соглашением без DB-запрета, file-allowlist открыт по умолчанию, daily-cron только функцией (нет планировщика), event-снапшоты только transition, моки в backend/docs а не docs/mocks, seed-имена/сроки этапов не по ТЗ.

### P4

Backend P4 полностью готов по backend-критериям (20 DONE / 2 PARTIAL). Все экспортёры, jobs/worker, overview/matrix, импорт-валидация — DONE. Фронтенд-клиенты (чекбоксы, polling UI, Dashboard/матрица-рендер, PNG-кнопки) не учитываются. Остаточные PARTIAL — только backend: P4-12-01 (числа golden в ТЗ противоречивы, тест защищает инвариант структурно, PG-only) и P4-13-01 (нет зафиксированных p50/p95 на demo).

### P5

P5 закрыт кроме интеграций (20 DONE / 9 PARTIAL / 2 NOT DONE / 1 BLOCKED). Auth/RBAC/scope/policy/audit-read/errors/docker/openapi/cache-baseline/security-baseline/alignment/docs/archimate/smoke — DONE. P5-12-02 (фронтенд-кэш) исключена из оценки (BLOCKED, вне скоупа). PARTIAL: admin без Keycloak Admin API, 403-матрица только 3 домена, аудит без login/import-summary, frontend-кэш zero-dep эквивалент, load только Locust-файлы без артефактов, demo без mp4. NOT DONE: Mock/Http LMS + Website адаптеры и env (P5-07-02, P5-08-01) — только стаб; ImportNormalizer/WorkflowImporter для внешних источников отсутствует (XLSX-импорт каталогов есть, это другое).

---

## 4. Critical Issues

### C1. Path Traversal в import staging через `file_id`
- Location: `backend/app/modules/imports/service.py:152-165` (`_staged_path`), `backend/app/modules/imports/schemas.py::ImportExecuteRequest.file_id: str`, `backend/app/modules/imports/router.py:/execute`, `/jobs/{id}/report`.
- Проблема: `file_id` — plain `str` без pattern; `_staged_path` делает `os.path.join(STAGING_DIR, file_id)` + fallback «file_id уже с расширением» без `fullmatch`/`resolve().is_relative_to`. `stage_upload` возвращает `uuid4().hex`, но входящий не валидируется.
- Последствия: `file_id=../../...` выходит за staging; парсеры xls/xlsx открывают результат → произвольный file-read примитив + oracle существования.
- Рекомендация: `pattern="^[0-9a-f]{32}$"` в схеме + `fullmatch` в `_staged_path` + `Path.resolve().is_relative_to(STAGING_DIR)`; один канонический формат `<hex>.xlsx`.

### C2. `POST /import/preview` буферизует весь файл в RAM до лимита
- Location: `backend/app/modules/imports/router.py:133-134` (`content = file.file.read()`), `service.py:139` (`MAX_FILE_BYTES=10MB` проверяется после), `core/middleware.py:21` (51 MiB).
- Проблема: файл до 50МБ ложится в RAM воркера до отказа; параллельные аплоады → OOM. Attachments стримят чанками (`workflow_attachments/service.py:95-105`) — импорт исключение.
- Последствия: OOM/деградация под нагрузкой, обход дешёвой защиты дорогой ценой.
- Рекомендация: читать чанками с нарастающим счётчиком, 413 mid-stream как в attachments.

---

## 5. High Priority Issues

### H1. Долгая единая транзакция импорта
- Location: `backend/app/modules/imports/service.py:540-597` (`execute_import`, `apply_row`, `find_university 257-264`, `_get_or_create`, `commit 593`, `rollback 595`), cap `588-589`.
- Проблема: до 5000 строк × ~10 SELECT, один commit в конце; bloat/locks/snapshot; один медленный файл тормозит остальных; `len(errors)>=100: break` без флага `truncated` в `ImportSummary`.
- Рекомендация: bulk-предзагрузка справочников (IN), `bulk_insert_mappings`, батчевые commit/flush, явный `truncated + errors_total`.

### H2. Пост-коммит writers глотаются `except: pass` → дрейф SQL-проекции
- Location: `backend/app/modules/workflow_transitions/service.py:187-198` (invalidate + refresh + `db.commit()` в try, оба `except: pass`), лишний `return get_instance_or_404` после коммита; аналогично `workflow_attachments/service.py:142-145`.
- Проблема: API вернёт свежее, SQL-ридеры (`list_universities_health`) — старое (`health_score_current`/снапшот не записался) молча.
- Рекомендация: логи с exc_info, outbox/ретраи, метрика `health_materialization_failures_total`.

### H3. Аудит молча no-op без контекста
- Location: `backend/app/modules/catalog/repository.py:54-56` (`if audit_context not in db.info: return`), `students/service.py:94-95`, `meetings/service.py`; голый `get_db` в `universities/passport_router.py:42,59,76`, `workflow_attachments/router.py`, `health_score/*`; `audit/service.py:117` never-commits.
- Проблема: чувствительные чтения/скачивания тихо не аудитируются; владелец commit размазан.
- Рекомендация: единый dependency с audit_context, fail-closed тест «мутирующий роут обязан иметь контекст».

### H4. Бизнес-логика и SQL в `GET /catalog/overview` + scope-пробел
- Location: `backend/app/modules/catalog/router.py:739-848` (нарушает шапку файла «No SQL/business logic»), `826,828` (`directions/programs` без scope, остальное со scope), двойная загрузка вместо GROUP BY.
- Проблема: scoped-пользователь видит глобальные счётчики; когнитивная нагрузка; лишний SQL.
- Рекомендация: вынести в service/repository, scope везде, `GROUP BY direction_id`.

### H5. Проверка scope после загрузки (order)
- Location: `backend/app/modules/catalog/router.py:154-161` (detail SELECT → ensure_visible 404 потом) vs правильный порядок в students/meetings.
- Проблема: лишний SELECT + timing-oracle (время отличается для чужих). Тела утечки нет (404 перекрывает).
- Рекомендация: scope-предикат в SQL до COUNT/page как в `list_universities_health`.

### H6. Redis: коннект на импорте, глобалы, приватный доступ, delete без try
- Location: `backend/app/infrastructure/redis.py:14-26` (from_url+ping на импорте, `_memory/_client` глобалы, нет reconnect), `task_queue.py:26`, `health_score/cache.py:55` (`redis_infra._memory.pop`), `cache.py:42-55` delete без try.
- Проблема: cold start I/O, мульти-процесс расходится, смена реализации ломает инвалидацию, падение Redis роняет вызывающий поток (спасает только `except: pass` из H2).
- Рекомендация: ленивый синглтон + reconnect/backoff, инкапсулировать `invalidate()` внутрь infrastructure/redis.

### H7. Мёртвая `task_queue` — вторая очередь с багами
- Location: `backend/app/infrastructure/task_queue.py:53-130` (O(N) dedup via hvals+json на каждый enqueue, `uuid4().hex[:12]` 48 бит, dequeue без атомарности vs канонический `report_jobs.claim_next_job` SKIP LOCKED); держится на unmounted `reporting/router.py:38,45`.
- Проблема: легко реанимировать копипастой и получить дубли/потери.
- Рекомендация: удалить или депрекейтнуть; оставить один `report_jobs` леджер.

### H8. Quarantine/mёртвый код в образе
- Location: не смонтированы в `app/api/router.py:30-48`, но копируются `Dockerfile:34-36`: `programs/documents/identity/dashboard/reporting/teachers/workflow/*`, `universities/repository.py:27`, `documents/router.py:30-38` (`FileOut.storage_key` — утечка ключей), `reporting/router.py:27-36` (ссылки на `University.region/status` — упадёт если смонтировать), `identity/router.py:29` (фейк `admin@rtk.local`), `limit(200/100)` без пагинации.
- Проблема: мины при реактивации; шиппинг кода с известными багами.
- Рекомендация: вынести в `backend/legacy/` вне Docker-контекста или удалить; держать guard `check_legacy_quarantine.py`.

---

## 6. Medium Priority Issues

### M1. God-файлы
- Location: `universities/passport_service.py` 1394 строки (8-блочная SQL-карта в шапке), `catalog/router.py` 848, `catalog/repository.py` 644, `imports/service.py` 654, `db/seed.py` 628.
- Проблема: изменение тянет всю карту; риск регрессии. Частично оправдано перфом (8 SELECT).
- Рекомендация: разбить паспорт на `passport/{blocks,loaders,dto}.py`.

### M2. Copy-paste `get_instance_or_404`
- Location: `workflow_instances/service.py:56`, `workflow_transitions/service.py:75`, `workflow_attachments/service.py:49` (дрейф импортов NotFound).
- Рекомендация: вынести в `workflow_instances/service` или `core`.

### M3. Маппинг исключений по подстроке
- Location: `core/exceptions.py:17-22` (`if active in text...`).
- Проблема: смена текста меняет HTTP-код; контракт на строке (тесты держат, но хрупко).
- Рекомендация: явные подклассы/коды вместо парсинга текста.

### M4. Несогласованные ON DELETE
- Location: `000012:59` workflow CASCADE vs `000002:27,48`, `000003:27` каталог RESTRICT.
- Проблема: удаление вуза сносит workflow-историю, но упирается в каталог; семантика hard-delete частична.
- Рекомендация: единый policy-документ + тест удаления со всеми связями.

### M5. Нет пул-конфига/таймаутов БД — NEEDS VERIFICATION
- Location: `db/session.py:8-12` (`create_engine(pool_pre_ping=True)` без pool_size/max_overflow/timeout/statement_timeout).
- Проблема: дефолт QueuePool 5+10 × uvicorn workers + worker; под H1 пул saturate. Факт отсутствия настройки подтверждён, влияние — только под нагрузкой.
- Рекомендация: явные pool_size/max_overflow/pool_timeout + statement_timeout + метрики.

### M6. Мёртвый `core/pagination.py`
- Location: `core/pagination.py:15-17` (`query.count()` ломается на Select), нигде не импортируется; все дублируют COUNT+LIMIT/OFFSET.
- Рекомендация: удалить или использовать.

### M7. JWKS-кэш без лока + blocking I/O
- Location: `core/security.py:37,64-90` (глобальный dict без Lock; urllib 5s в request-path, TTL 600с).
- Проблема: гонка двойного refresh (низкий риск, GIL+idempotent); шторм Keycloak saturate threadpool. Таймаут уже есть.
- Рекомендация: `threading.Lock` + httpx/async или кэш-метрики.

### M8. Тесты: дорогая изоляция, слабые моки, покрытие-иллюзия
- Location: `tests/conftest.py:20-34`, `db_helpers.reset_test_db` (DROP SCHEMA+CREATE+23 миграции на фикстуру), `require_pg_engine` (без PG скипы), `test_p1_mocks.py`/`test_p5_mocks_coverage.py` (валидируют JSON, не поведение), `conftest.seeded_db` yield+rollback хрупко при commit.
- Проблема: сьют медленный; в CI без PG только unit; зелёные моки без покрытия логики.
- Рекомендация: транзакционные savepoints/шаблонная БД, разделение PG/unit в CI, behavior-тесты поверх фикстур.

### M9. `storage._cached_build` игнорирует смену кредов
- Location: `workflow_attachments/storage.py:282-291` (lru_cache по backend/root/endpoint/bucket, ключи из settings внутри).
- Проблема: ротация S3-кредов без рестарта не подхватится. LOW-MEDIUM (рестарт дёшев).
- Рекомендация: хеш кредов в ключе или без кэша для S3.

### M10. Нет rate limiting
- Location: `infrastructure/redis.py:1` обещает rate-limit, реализации нет (grep rate/throttle — только комменты); тяжёлые GET (`/catalog/overview` page_size≤500, `/analytics/matrix` 50k ячеек) без троттлинга.
- Проблема: DoS-вектор — NEEDS VERIFICATION, отсутствие механизма — факт.
- Рекомендация: token-bucket в Redis + 429 + тесты.

---

## 7. Low Priority Issues

- L1. `print()` в сидах: `db/seed.py:622-624`, `db/seed_workflow.py:120-122` → logging.
- L2. Magic numbers: `analytics/router.py:96` 50_000, `reporting/router` 5000/1000, TTL 300/600, `COMMENT_EDIT_WINDOW 15*60`; часть именована (`policy.py:17`, `cache.py:16`).
- L3. Хардкод localhost в дефолтах `config.py:20,28,32-33,51` — нормально для dev, прод перекрывает env (не баг).
- L4. `Content-Length` из БД при скачивании `workflow_attachments/router.py:143` — при рассинхроне врёт заголовок.
- L5. `custom_openapi` `main.py:63-166` — работает, покрыто `test_p5_openapi_docs.py`, но хрупко к обновлению FastAPI.
- L6. `audit/relay.py:37-38` SQLite-ветка без `on_conflict_do_nothing` — двойная доставка только в тестах.
- L7. Миграции без CHECK на статусы (`000001:15` No CHECK by design) — валидация только Python; дрейф прямой записью возможен.

Проверено и НЕ является проблемой: SQLi (bound params + `like_pattern/_escape_like`), auth bypass в compose (`AUTH_DEV_BYPASS=false`, fail-closed валидатор, `_dev_user` недостижим в проде), traversal в attachments (`_checked_key` + uuid-ключи + `os.replace` атомарно), CORS allowlist без wildcard в проде, миграции транзакционные (`migrate baseline→up→verify`, entrypoint `set -e`).

---

## 8. Code Smells and Workarounds

- `imports/service.py:152-165` → тройной fallback поиска staging + traversal (C1) → CRITICAL → один формат + строгая валидация.
- `imports/service.py:300-304` `_slug_code` → недетерминированный `dir-<rand>` → MEDIUM → требовать code/справочник синонимов, 409 с подсказкой.
- `imports/service.py:276` synthetic email `import-<rand>@example.local` → мусорные контакты → MEDIUM → nullable email или `source=import` + дедуп.
- `imports/service.py:97-109` `parse_date` год→Dec 31 → завышение сроков → MEDIUM → явный `expiry_granularity`.
- `imports/service.py:588-589` cap 100 ошибок без `truncated` → клиент думает видел всё → MEDIUM → `truncated + errors_total`.
- `catalog/router.py:116-131` `region` deprecated no-op → вводит в заблуждение (200 с полными) → LOW → 410 Gone или удалить.
- `main.py:63-166` `custom_openapi` пост-обработка → LOW → contract-first примеры в схемах.
- `workflow_transitions/service.py:187-198` двойной `except: pass` → скрытый дрейф → HIGH → outbox+метрики.
- `health_score/cache.py:55` `_memory.pop` через приватное поле → MEDIUM → метод `invalidate()`.
- `workflow_attachments/storage.py:282-307` `_cached_build` + alias `MinioStorageBackend` → stale/два имени → LOW → один импорт, ключ с хешем кредов.
- `infrastructure/task_queue.py` mirror+HVALS → O(N), расхождение → HIGH → удалить, оставить `report_jobs`.
- `audit/service.py:177-179` `uuid5` fallback для не-UUID → коллизии → LOW → строгий UUID, 422 иначе.
- `universities/passport_service.py:143-146` `_NULL_*` padding для UNION ALL → хрупко к типам → LOW → отдельные запросы/cast от колонки.
- `analytics/report_worker.py:80-96` `None` vs `[]` scope (None=global) → невидимый security-контракт → MEDIUM → ADT `Global|Ids`, None запретить.
- `core/middleware.py:17-21` `+1 MiB` allowance → дрейф от policy → LOW → один источник MAX_FILE_SIZE.
- `universities/repository.py:33`, `identity/router.py:27` `limit(200/100)` без пагинации → молча неполные → MEDIUM → PaginatedResponse.
- `core/pagination.py` dead `paginate` → вводит в заблуждение → LOW → удалить.
- `documents/router.py:30-38` `FileOut.storage_key` наружу → утечка если смонтируют → HIGH при монтировании → удалить из образа.

---

## 9. Architecture Review

Хорошо:

- Модульный монолит с единым v1-агрегатором, тонкие роутеры (канон: meetings/students/audit/auth/workflow_*), чистые функции формул в одном источнике, единый error/audit/scope фундамент, worker отдельно от API, Redis с fallback, fail-closed entrypoint/миграции.
- Паспорт: batched блоки + include-расширения без N+1; Health Score: детерминированные калькуляторы + materialization + snapshots + relay; P4: один фильтр везде + леджер jobs + SKIP LOCKED.

Проблемы:

- Separation of concerns: SQL + склейка в `catalog_overview` (H4), scope после SELECT (H5), аудит-контекст размазан (H3), Redis-приватное поле наружу (H6).
- Две очереди (`report_jobs` + `task_queue`), мёртвые модули в образе (H7/H8) — рост сложности при реактивации.
- God-файлы паспорта/каталога/импорта/сида (M1) — точка роста регрессий.
- Несогласованные ON DELETE (M4), отсутствие pool/rate-limit (M5/M10) — точки роста под нагрузкой.
- Внешние интеграции отсутствуют как слой (P5-07/08/09) — будущий рост потребует нового bounded context, не стаба.

---

## 10. Database Review

- Schema: ядро + workflow + jobs + audit/outbox + health_current/snapshots; именованные FK/unique/index, композиты (`ix_licenses_univ_expires`, `(is_mandatory,expires_at)`, `ix_meetings_univ_meeting_at`); CHECK single-link documents; осознанно без CHECK на статусы (валидация Python).
- Queries: паспорт 8 statements (batched, не selectinload-цепочка — ок); overview — двойная загрузка + scope-пробел (H4); импорт — десятки тысяч round-trip в одной транзакции (H1); ranking via `row_number()` по materialized — ок.
- Transactions: переход атомарен (close+skip+pointer+history+audit в одной) — хорошо; импорт один commit на 5000 — плохо; пост-коммит commit в try с глотанием — дрейф (H2); `migrate.py` транзакционен, baseline строгий, verify сверяет таблицы.
- Indexes: все по спеке P1-10-01 на месте (MISSING 0); EXPLAIN-инфраструктура есть (`explain_passport/check_explain/seed_performance`), артефактов без PG нет — NEEDS VERIFICATION.
- Connections: pool_pre_ping только; pool_size/timeout/statement_timeout не заданы (M5).
- Migrations: raw SQL единственный источник, Alembic архив; 23 пары up/down; entrypoint `baseline→up→verify` fail-closed.
- Consistency: partial unique active instance отсутствует (возможен дубль active); transitions иммутабельны соглашением; `health_score_current` может дрейфовать при H2; удаление вуза CASCADE workflow vs RESTRICT каталога (M4).

---

## 11. API Review

- Консистентность: префикс `/api/v1`, пагинация `page/page_size/total`, единый `ErrorResponse`, BearerAuth в OpenAPI, summary/tags/error-examples. Порядок роутеров важен и соблюдён.
- Методы/коды: CRUD + 404/409/403 корректно; batch `ids` max50→422, порядок сохранён; download 409/410/403; preview/execute 400/413/415; transition `WORKFLOW_INVALID_TRANSITION` via handler (не литерал в сервисе — ок, но хрупкий маппинг по подстроке M3).
- Валидация: `UnifiedFilter date_from<=date_to→422`, `resolve_columns unknown/[]→422`, comment обязателен, `order_index≥1`, `due_date` каскад; пробелы: `file_id` plain str (C1), `region` no-op (вводит в заблуждение), cap 100 без truncated (H1).
- DTO: Base/Create/Update/List/Detail/Short разделены; счётчики в сервисе; `computed_field` derived; `trainings` отсутствует санкционированно; `InstanceDetail` без progress/overdue counts из ТЗ.
- Утечки: канонический attachments скрывает storage_key; quarantine `documents FileOut.storage_key` — утечка если смонтируют (H8); overview отдаёт глобальные счётчики scoped-пользователю (H4).
- Pagination/filtering: каталоги/аудит/jobs — есть; meetings/students без фильтров; teacher-лист отсутствует; `limit(200/100)` в quarantine без пагинации.
- Идемпотентность: seed `_get_or_create`, workflow seed upsert, импорт natural keys + `idempotency_key`, snapshots `ON CONFLICT DO NOTHING`, jobs claim `WHERE queued+attempts<3`; `dry_run` rollback корректно но дорого.

---

## 12. Security Review

Подтверждено хорошо: JWKS RS256 + kid-refresh + iss/aud/exp + TTL 600 + fail-closed (`security.py`); `AUTH_DEV_BYPASS=false` в compose + prod fail-closed валидатор; RBAC permissions + scope SQL-предикат до COUNT; Policy 403 vs 404 разделены; CORS allowlist; SecurityHeaders + 413 (Content-Length+streaming); attachments 50MB/sanitize/containment/UUID-ключи/atomic replace; ORM-only + escape LIKE; SensitiveFilter; pinned deps; audit scope (чужой university→403).

Найдено:

- CRITICAL C1/C2 (импорт file_id traversal + preview RAM) — чинить первым.
- HIGH H4 (scope-пробел в overview счётчиках), H5 (timing-oracle порядка scope), H8 (quarantine утечки если смонтируют).
- MEDIUM: allowlist файлов открыт по умолчанию (P2-05-01 PARTIAL — осознанно, но 415 только при env), `None` vs `[]` scope в worker (невидимый контракт), нет rate-limit (M10), JWKS без лока (M7 низкий риск).
- NEEDS VERIFICATION: поведение под штормом Keycloak/Redis (saturate), удаление вуза со всеми связями, ретенция snapshots/outbox.

Не найдено (проверено): SQLi, обход auth в проде, traversal в attachments, CORS wildcard в проде, секреты в коде. Уязвимости не выдумывались; непроверяемое помечено NEEDS VERIFICATION.

---

## 13. Testing Review

- Покрытие: ~80 тестовых файлов (`test_p1_*`, `test_p2_*`, `test_p4_*`, `test_p5_*` + conftest/db_helpers/fixtures/load). P1 sqlite-подмножество проходит (19 passed в точечном прогоне); P4 unit 173 passed; P2 aggregate/transition/template edge проходят. PG-интеграция скипается без `TEST_DATABASE_URL` (152 skipped в P1-подмножестве, 121 skipped в P4) — железная изоляция (`DROP SCHEMA+CREATE+23 миграции` на фикстуру) ценой скорости.
- Качество: сильные группы — `test_p2_11_04_template_edit` (reorder/rollback/locks/parallel/RBAC), `test_p2_11_03_edge` (границы/детерминизм), `test_p5_security_*` (JWKS/RBAC/baseline), `test_p5_unified_errors`, `test_p4_golden_seed` (инвариант), upload/traversal/50MiB границы, passport readiness/reasons. Слабые — `test_p1_mocks`/`test_p5_mocks_coverage` (валидируют JSON, не поведение), часть P2-11 без 401/403/404/archived кейсов.
- Пробелы: перф-ассёрты (<500/<200/<150ms, ≤8 SQL, EXPLAIN Index Scan) только кодом тестов, без живого PG не исполнялись; нет артефактов load (Locust-файлы есть, HTML/метрик нет); нет теста «transition→ровно 1 audit событие»; нет теста удаления вуза; нет 403-матрицы teachers/workflow/reports/analytics/templates; coverage >80% не измерен.
- Изоляция: `reset_test_db` надёжна, но медленна; `seeded_db` yield+rollback хрупок при commit; `pytest-xdist` отсутствует (ок для serial).

---

## 14. Recommended Fix Order

1. C1 + C2 — валидация `file_id` (pattern + `is_relative_to`), стриминг preview с mid-stream 413.
2. H1 — батчинг импорта (предзагрузка IN, bulk insert, батчевые commit, `truncated` флаг).
3. H2 + H6 — убрать `except: pass`, логи exc_info, outbox для health-материализации, инкапсулировать Redis (reconnect, `invalidate()` внутри).
4. H4 + H5 + H3 — overview в service/repository + scope везде + GROUP BY; scope до SELECT; единый audit dependency + fail-closed тест.
5. H7 + H8 + M6 — удалить `task_queue`/quarantine из образа (или `legacy/` вне Docker), удалить dead `paginate`.
6. P2-01-02 partial unique active + P2-03-02 решение admin-override (документировать отклонение или реализовать) + DB-запрет UPDATE/DELETE transitions.
7. P5-07/08/09 интеграции (LMS/Website Mock/Http + normalizer/importer + `(external_id,source)` upsert) или честно заскейпить с ADR.
8. P5-03-03 Keycloak Admin API или зафиксировать «только консоль» в контракте; расширить 403-матрицу на все домены.
9. M4/M5/M10 — единый delete-policy + тест; pool/timeout конфиг; rate-limit (429) на тяжёлые GET.
10. Верификация на живом PG: EXPLAIN артефакты, N+1 ≤8, <500/<200ms, golden на числах, load p50/p95/p99 + HTML, smoke/docker `<3мин` артефакты; разбить god-файлы (M1), убрать copy-paste/magic (M2/L2).

---

## 15. Final Task Status

| Priority | Total | Done | Partial | Not Done | Blocked |
| -------- | ----: | ---: | ------: | -------: | ------: |
| P1       |    38 |   23 |      15 |        0 |       0 |
| P2       |    37 |   21 |      16 |        0 |       0 |
| P4       |    22 |   20 |       2 |        0 |       0 |
| P5       |    32 |   20 |       9 |        2 |       1 |
| Total    |   129 |   85 |      41 |        2 |       1 |

Фронтенд не учитывается: P4-02-02, P4-06-02, P4-08-01, P4-09-02, P4-11-01 признаны DONE по backend-части; P5-12-02 (чисто фронтенд) — BLOCKED/вне скоупа.

---

## 16. Conclusion

- Реализовано: ядро P1 (каталоги/паспорта/derived/seed/индексы/моки), движок workflow + Health Score + attention/ranking/history (P2), аналитика/отчёты/матрица/импорт каталогов (P4 backend DONE), auth/RBAC/scope/audit-read/errors/docker/openapi/cache/security-baseline/docs/archimate/smoke (P5). Фронтенд-задачи исключены из оценки. Backend собирается, OpenAPI валиден, unit-подмножество зелёное.
- Осталось: закрыть 2 CRITICAL импорта; батчинг + truncate-флаг; outbox/Redis/аудит/scope/overview hardening; удалить вторую очередь и quarantine из образа; partial unique active + admin-override решение; внешние LMS/Website адаптеры + нормалайзер (или ADR-скоуп); Keycloak Admin API; полная 403-матрица; pool/rate-limit; живые PG/нагрузочные артефакты (golden-числа, p50/p95).
- Наиболее существенны: C1/C2 (эксплойт-примитив/ OOM), H1 (перф/транзакции), H2 (дрейф данных), H3/H4/H5 (аудит/scope), H7/H8 (мёртвый код в образе).
- В первую очередь: пункт 1–5 из Recommended Fix Order, затем интеграции и верификация на живом стенде.

---

## 17. Fix Log (working tree, после ревью, каждый фикс подтверждён вопросом)

Проверено полным сьютом: **444 passed, 599 skipped (PG-gated), 1 failed** — единственное падение `test_mounted_routers_are_only_the_production_contract` предсуществует на чистом HEAD `9d6077a` (хелпер двоит префиксы вложенных роутеров, `git worktree` проверка), не вызвано правками. `check_legacy_quarantine.py: OK`.

- **C1** — `imports/service.py::_staged_path`: строгий `^[0-9a-f]{32}$` + `resolve().relative_to`, убран direct-fallback; `schemas.py::ImportExecuteRequest.file_id` с `pattern`. Traversal заблокирован (проверено перебором).
- **C2** — `imports/router.py::import_preview`: чтение чанками 256KiB с 413 mid-stream (`FILE_TOO_LARGE`), вместо `read()` целиком.
- **H1** — `imports/service.py::execute_import`: батч-коммиты по 500 (`IMPORT_COMMIT_BATCH`), `truncated/errors_total` в summary; `ImportSummary` + error-report расширены. Полный bulk-preload справочников — follow-up.
- **H2** — `workflow_transitions/service.py`: `logger.exception` + `rollback` вместо bare `pass` (инвалидация + материализация).
- **H3** — аудит: upload/delete attachments и create instance переведены на `get_audit_db` + пишут CREATE/DELETE-события (guard при отсутствии контекста); preview получил контекст; новый `tests/test_p5_audit_context_guard.py` (мутации без контекста падают). Guard заодно нашёл и закрыл `POST /workflow/instances` и `POST /import/preview`.
- **H4** — `catalog/router.py::catalog_overview` (110 строк SQL/склейки) переехал в `service.get_catalog_overview` + `repository.count_overview/page_overview_licenses/direction_program_counts` (GROUP BY вместо загрузки всех программ, счётчики в scope; справочник направлений глобальный). Заодно убраны N+1 на `product.vendor` и `link.responsible`.
- **H5** — `repository.get_university_scoped` (scope в SELECT) + `service.get_university_detail(..., user=...)`; роутер без второго запроса.
- **H6** — `infrastructure/redis.py`: ленивый коннект + cooldown-reconnect + guard на всех операциях + публичные `cache_delete/cache_delete_pattern`; `health_score/cache.py` и `services/cache.py` без приватного доступа и незащищённых delete.
- **H7** — удалены `infrastructure/task_queue.py`, `app/workers/reports.py`; quarantine-стабы `reporting`/`notifications` отвечают 410 GONE (импортируемость для `test_p0` сохранена).
- **H8** — `backend/Dockerfile` runtime вычищает 14 legacy endpoint-файлов (`rm` после COPY; test-стейдж не тронут).
- **M1** — `universities/passport_service.py` 1394 → `passport_loading.py` (SQL) + `passport_blocks.py` (DTO) + фасад 59 строк; публичный API стабилен (`__all__` без изменений).
- **M2** — одна `get_instance_or_404` в `workflow_instances/service.py`, остальные — re-export.
- **M3** — `BadTransition(detail, code=...)`: явный код вместо парсинга текста; call sites с `WORKFLOW_INSTANCE_NOT_ACTIVE`/`STAGE_ALREADY_COMPLETED`.
- **M4** — единый delete-policy: `repository.university_delete_blockers` (EXISTS по 11 связям) + `service.delete_university` → 409; DB-ограничения как backstop; `tests/test_p1_university_delete_policy_unit.py` (4 passed, sqlite).
- **M5** — `config.py`: `db_pool_size/max_overflow/pool_timeout/statement_timeout_ms`; `session.py`: QueuePool + `statement_timeout` для PG, sqlite без изменений; `.env.example` документирован.
- **M6** — удалён мёртвый `core/pagination.py` (импортов не было).
- **M7** — `_jwks_lock` в `core/security.py` (double-checked refresh).
- **M8** — ПРОПУЩЕН по решению (инвазивная перестройка изоляции тестов).
- **M9** — `storage._cached_build`: креды в ключе кэша, ротация без рестарта строит fresh backend (pinned тестом).
- **M10** — `core/rate_limit.py` (fixed-window, Redis+fallback, fail-open) + `RateLimitMiddleware` на 4 тяжёлых пути (120/мин, 429 `RATE_LIMITED` + `Retry-After`); `settings.rate_limit_per_minute`; `tests/test_p5_rate_limit_unit.py` (5 passed).
- **LOW** — L1: `print` → `logging` в `seed.py`/`seed_workflow.py` (заодно исправлен SyntaxError `import sysfrom datetime...` — `app.db.seed` вообще не импортировался, демо-сид был мёртв); L4: `StorageBackend.size()` (local stat / S3 stat_object), download отдаёт верифицированный размер или chunked без заголовка; L6: sqlite-ветка relay check-then-insert (идемпотентность без ON CONFLICT).

Остались открыты: M8 (отложен), P5-07/08/09 интеграции, Keycloak Admin API, partial-unique active instance, admin-override переходов, PG/нагрузочные артефакты.

# Аудит проекта CRM (ИТ Школа РТК, кейс 16)

> Дата: 2026-09-20. Рабочая ветка `raisw`, поверх `develop`. Проект в разработке — оценивается то, что есть, с прицелом на будущее.
> Стек: `Browser → React 18 → Keycloak 26 → FastAPI → PostgreSQL 16`. Стенд поднимается одной командой `docker compose up --build`.
> Предыдущий срез (`docs/AUDIT.md` от 2026-09-18) частично устарел: добавлен канонический runtime Б2 (`interaction_pipeline`) и миграция `000011_workflow_runtime`; legacy-модуль `app.modules.workflow` по-прежнему изолирован.

## 0. Статус исправлений P0/P1 (вечер 2026-09-18)

> Часть legacy-поведения зафиксирована тестами-пинами (не ломалась): `region`-игнор, TypeError legacy-create, отсутствие Teacher Passport, stock-формы 404/401/422/409. Исправления ниже это учитывают.

| Блокер | Что сделано | Проверка |
|---|---|---|
| Две вселенные схем | `app/modules/_deferred.py` — явный реестр deferred-модулей; legacy int-модели (`workflow/documents/health_score/identity`) изолированы на отдельном metadata; миграция `000010_audit_identity` — `audit.user_id/entity_id` INTEGER→TEXT; добавлен канонический UUID runtime Б2 в `app/models/workflow.py` + `app/modules/interaction_pipeline/`; старый `app.modules.workflow` не монтируется | `tests/test_p0_deferred_registry.py` фиксирует канон из 29 таблиц и `/api/v1/workflow` |
| Фронт только localhost | Runtime `/config.json` (entrypoint генерирует из env; build-ARG — только fallback); `apiUrl=""` = same-origin `/api/`-прокси в nginx (+ `/api/health`, gzip, security-headers, cache-policy); `KEYCLOAK_ISSUER` параметризован (`KEYCLOAK_EXTERNAL_URL`); `keycloak/render_realm.py` — точечная подмена origin в realm (3 строки, round-trip чистый) | Образ собран, smoke: `/health`→ok, `/config.json` из env; `docker compose config` валиден |
| apiFetch только GET | Переписан: `method/body/signal`, guard `Bearer`, 204/205 и не-JSON guards, 401 с одноразовым login (анти-loop флаг), `anonymous` для публичных проб | `tsc`, `vitest` 3/3, `vite build` |
| Импорт блокирует HTTP | Договор сохранён (sync 200 — пин теста), но: `job_failed` + `job_running` (нет вечных "queued"), `idempotency_key` (повторный POST не дублирует), Redis-персист с TTL 24ч + локальное зеркало, staging в volume (`import-staging`), payload worker-совместим + реализован `run_imports_once` | `test_p4_import` зелёный |
| Dockerfile ≠ pyproject | Все 13 runtime-зависимостей + `USER appuser` (10001); `HEALTHCHECK` уже был | `tests/test_p0_docker_deps.py` (superset-guard + non-root); образ собран и запущен (smoke `/health`, `/ready` fail-closed, 13 путей) |
| P1 backend | 500-envelope с `request_id` (404/422/401/409 не тронуты — пины); `request.state.request_id`; RBAC на `catalog` (`catalog.read`) и `import/*` (`import.write/read`), матрица расширена, `UserRole` +`curator`; `catalog/overview` — `page/page_size` (+deprecated `limit`); `except: pass` → `logger.warning` (redis/storage/queue); `get_engine(url)`; entrypoint: loud-warning вместо `|| true`, `--proxy-headers` | Сьют зелёный (обновлены 2 теста-контракта: curator-perms, head-chain → `000010`) |
| P1 фронт | `ErrorBoundary`, мини hash-роутер (`#/`, `#/catalog`), типы в `types.ts`, `AuthProvider`: ошибка init + ретрай + `onTokenExpired`, `UserCard` `?? []`, `aria-live`/`role=alert`, `:focus-visible`, брейкпоинт 640px, `typecheck`/`test` скрипты, `.dockerignore` починен, `nginx:1.27-alpine`, `HEALTHCHECK`, `vite server.proxy` | `typecheck` ✓, `vitest` ✓, `vite build` ✓ |
| P1 инфра | `redis:7-alpine` + `redisdata`; `networks: rtk-net`; `restart: unless-stopped` + `logging` лимиты везде; PG/redis — `expose` (публичны только 3000/8081/8000); `healthcheck` у frontend; `.env.example`: `KEYCLOAK_EXTERNAL_URL`, `KEYCLOAK_CLIENT_ID`, `FRONTEND_API_URL` | `docker compose config -q` OK |
| Остаток (не в скоупе) | 152-ФЗ фичи; react-router/query/form; `test_health_status_filter_not_implemented` падает на локальном Python 3.14 (на чистом дереве тоже; канон — 3.12); PG-интеграция требует живой БД | — |

### Отложенные модули (forward-заглушки следующих этапов)

Смонтировано только `auth / import / passport / catalog`. Остальное в `app.modules` — заглушки на будущее, частично написанные до P1 UUID-решения (отсюда int-ключи/поля). Не монтировать без чек-листа.

| Модуль | Почему отложен | Канон/замена сейчас |
|---|---|---|
| universities-CRUD | Роутер до P1-схемы (поля region/status); пин в тестах | `app.models.catalog.University` + passport |
| teachers-CRUD | int-id; Teacher Passport намеренно отсутствует (пин) | `app.models.teachers.*` |
| programs | int-id / таблица `programs`; в P1 — `it_programs` | `ITProgram` |
| workflow (legacy) | int PK/FK; изолирован на `DeferredBase` | Канонический `interaction_pipeline` (UUID) |
| documents | Второй реестр `files`; изолирован на `DeferredBase` | `models.interactions.Document` |
| health_score | int FK, таблицы нет в миграциях; изолирован | Чистый `compute_score()` |
| identity | Заменён Keycloak (`sub` → `responsibles`); изолирован | `app.core.security` |
| audit | `user_id/entity_id` → TEXT (миграция `000010`) | `AuditEvent` (SQL-управляемый) |
| dashboard | Агрегаты по отложенным таблицам | Будущие endpoints на каноне |
| reporting | Генерация XLSX/PDF вне P1 | Будущий `workers/reports.py` |
| reporting (P4-06-01, 2026-09-23) | Legacy demo stub `app/modules/reporting` (`POST /export` поверх in-memory очереди, поля `region/status` вне P1-схемы) остаётся НЕСМОНТИРОВАННЫМ/deprecated — не удалён, чтобы не ломать историю, но production-путём не является | Канон: `POST /api/v1/reports → 202 {job_id, queued}` + `GET /reports/{job_id}` + `GET /reports/{job_id}/download` (`app/modules/analytics/reports_router.py`, persistent `report_jobs`, миграция `000018_report_jobs`, worker `generate_report_task` на FastAPI BackgroundTasks). Guard: `tests/test_p0_deferred_registry.py::test_legacy_reporting_stub_stays_unmounted` |
| integrations | Интеграции LMS/сайт — стаб (требование кейса) | Будущий `workers/integrations` |
| notifications | Стаб рассылок | Будущая очередь + шаблоны |

Чек-лист реактивации модуля: 1) PK/FK → UUID; 2) `user_id` → `keycloak_sub: str`; 3) SQL-миграция + down; 4) монтирование + `require_permission`; 5) пагинация + `ErrorResponse`; 6) тесты (PG-путь). Для Б2 этот чек-лист выполнен отдельным каноническим модулем; legacy-пакет не включался. Guard: `tests/test_p0_deferred_registry.py` (канон ровно 29 таблиц, legacy-префиксы отсутствуют в API).

## 1. Резюме

| Блок | Состояние | Комментарий |
|---|---|---|
| Auth-стенд | 🟢 работает на localhost | JWT RS256 по JWKS, fail-closed, 4 demo-роли |
| P1-ядро БД | 🟢 сильное | 11 SQL-миграций, 29 канонических таблиц, UUID + timestamptz, вычисляемые статусы |
| Импорт XLSX/XLS | 🟡 работает, но синхронно | Лимиты 10МБ/5000 строк есть, воркера нет |
| Паспорт вуза / каталог | 🟡 частично | `passport`, `catalog` смонтированы; остальной домен — мертвый код |
| Frontend CRM | 🔴 заглушка | Один `App.tsx`, нет роутера/store/форм/тестов, недеплоябелен вне localhost |
| Инфра / деплой | 🟡 только localhost | `start-dev`, build-ARG, все порты наружу |
| 152-ФЗ / ФСТЭК-117 | 🔴 отсутствует | Требование кейса, пока ноль фич |
| Workflow 14 шагов / Б2 | 🟡 backend-скелет готов | Шаблоны, экземпляры, forward-only переходы с revision-lock, история, комментарии, задачи и привязка документов; UI и SLA-уведомления ещё не сделаны |

Вывод: фундамент (auth + схема + миграции + seed) заложен грамотно. Главный риск — **две вселенные кода**: каноническое P1-ядро (UUID) vs 11 несмонтированных legacy-модулей (int PK). Если их включать «как есть» — будет каскад 500-х. Второй риск — **демо только на localhost**: на стенде жюри по IP/hostname фронт не залогинится.

## 2. Что реально работает

* **Auth**: `backend/app/core/security.py:82-135` — RS256, проверка `iss/exp/aud` (явная проверка `aud`, т.к. python-jose её пропускает), `503` при недоступности JWKS. `AUTH_DEV_BYPASS=false` в compose — fail-closed. `backend/app/modules/auth/router.py` — `/auth/me`, `/test/*`. Фронт: `frontend/src/auth/keycloak.ts` — singleton, PKCE S256, токены в памяти (не localStorage — правильно).
* **RBAC-заготовка**: `backend/app/core/permissions.py:11-53` — матрица `admin/manager/curator/user`, `require_permission/require_role`. Реально используется только в `passport_router.py:46` и тестовых auth-эндпоинтах — образец для остальных.
* **Каноническая схема**: `backend/migrations/000001-000011` — единственный источник истины в проде (`entrypoint.sh` через `scripts/migrate.py`). P1 содержит 21 таблицу; Б2 добавляет 8 workflow-таблиц (`workflow_templates`, `workflow_stages`, `workflow_instances`, `instance_stages`, `transitions`, `comments`, `tasks`, `attachments`). Все доменные PK — UUID, даты — `timestamptz`, статусы лицензий/готовности и overdue-признаки вычисляются без второй схемы.
* **Импорт**: `backend/app/modules/imports/{router,service,schemas}.py` — `stage_upload/parse_preview/execute_import`, XLSX+XLS, лимиты 10МБ/5000 строк, cap 100 ошибок, `dry_run` через rollback, идемпотентность по natural keys.
* **Тесты**: `tests/test_auth.py` (13 тестов, RSA keypair + мок JWKS, без Keycloak), derived-статусы, OpenAPI-доки — зелёные. PG-интеграция честно скипается без `TEST_DATABASE_URL` (`tests/db_helpers.py:63-75`).
* **Инфра-порядок**: `depends_on service_healthy` у всех сервисов, `init-databases.sh` — least privilege (роль `keycloak` — owner только БД `keycloak`), CORS — allowlist, а не `*`.

## 3. P0 — блокирует развитие и демо

### 3.1. Две вселенные схем: канон (UUID) vs legacy (int)
* Канон: `app/models/*` (UUID). Legacy: `app/modules/{audit,documents,health_score,identity,workflow}/models.py` — `id/user_id/entity_id: Integer`, `health_score/models.py:12` — `FK("universities.id")` int против UUID-родителя. Схемы/роутеры тоже int: `modules/{programs,teachers,universities,workflow}/schemas.py` (`university_id: int`, `direction_id: str`).
* `app/api/router.py` монтирует production-контракт `auth, imports, passport, catalog` и новый канонический `interaction_pipeline`. Остальные legacy-модули (`audit, dashboard, documents, health_score, identity, integrations, notifications, programs, teachers, universities-CRUD, workflow`) остаются мертвым кодом, выглядящим готовым. Включение legacy без переписывания = 500/422 на типах FK.
* Бонус-расщепление: два файловых реестра (`modules/documents` пишет в `files`, паспорт читает `models/interactions.py:175 documents`); активный источник схемы — 11 SQL-миграций, а `alembic/versions/` остаётся read-only архивом.
* **Фикс до включения домена**: удалить legacy `modules/*/models.py + schemas.py`, переписать `router+service+repository` на `app.models + app.schemas` (UUID, `keycloak_sub: str` вместо `user_id: int`); `alembic/` — удалить или заморозить как read-only архив; добавить тесты «все PK — Uuid» и «все роутеры смонтированы».

### 3.2. Фронт недеплоябелен вне localhost
* `VITE_KEYCLOAK_URL / VITE_API_URL` запечены build-`ARG` (`docker-compose.yml:76-80`, `frontend/Dockerfile:11-15`). Рантайм-перенастройка невозможна; без `--build-arg` в бандле останется `localhost`.
* `KEYCLOAK_ISSUER=http://localhost:8081` (браузер) vs `JWKS=http://keycloak:8080` (сеть compose) — расхождение `iss`, любой gateway/proxy ломает валидацию (`security.py:98`). `realm-export.json:106-111` — `redirectUris/webOrigins` только `http://localhost:3000`. Итог: демо на `localhost:3000` пройдет, стенд жюри по IP/hostname — `invalid redirect_uri` / `invalid issuer`.
* Нет `/api`-прокси ни в `frontend/nginx.conf`, ни в `vite.config.ts` — фронт ходит в бэк напрямую, CORS load-bearing.
* **Фикс до демо на чужом хосте**: runtime `/config.json` + `envsubst` в entrypoint (убрать build-ARG); same-origin прокси `/api/ → backend:8000`; параметризовать realm (`${FRONTEND_ORIGIN}/*`); `KEYCLOAK_ISSUER` без литерала.

### 3.3. `apiFetch` и ErrorBoundary
* `frontend/src/api/client.ts:8` — только `GET`, нет `method/body/signal`. `POST/PUT/DELETE` для CRM невозможны без переписывания. `:24-28` — `resp.json()` без guards: `204 No Content` и HTML-ошибка nginx бросят `SyntaxError`. `:19` — `Bearer undefined` при вызове до `authenticated`. `:13` — failed `updateToken → login()` без флага — риск redirect-loop.
* `App.tsx:10-89` — god-component (auth-gate + `/me` + health-check + верстка), нет роутера, нет `ErrorBoundary` (`main.tsx:7-12`) — падение одного виджета роняет всё.
* **Фикс**: `RequestInit + signal`, guards `204/content-type`, ранний `401`, одноразовый login-редирект; разбить `App.tsx` (layout/pages, позже `react-router`), добавить `ErrorBoundary`.

### 3.4. Импорт блокирует HTTP + эфемерный staging
* `imports/router.py:83-92` — `execute_import` синхронно внутри POST; `task_queue` — in-memory стаб. 5000 строк = таймаут воркера uvicorn; повторный POST = повторная вставка (дедупликации по `file_id` нет).
* `STAGING_DIR=/tmp/rtk-imports` (`service.py:41`) — эфемерен в Docker, рестарт убивает `file_id` между preview→execute.
* **Фикс**: воркер (Redis list уже есть как заготовка) + staging в volume/S3 + `file_id` с TTL; нагрузочный тест импорта.

### 3.5. Dockerfile дрейфует от pyproject
* `backend/Dockerfile:4` ставит 11 пакетов вручную, пропущены из `pyproject.toml`: `pydantic-settings`, `python-jose`, `redis`, `minio`, `reportlab`, `python-dateutil`, `python-multipart` — прод-образ упадет на импорте. Нет `USER` (root), нет `--workers/--proxy-headers` в uvicorn.
* `frontend/.dockerignor` — опечатка (должен быть `.dockerignore`) → в контекст летят `node_modules/dist`. `FROM nginx:alpine` без пина.
* **Фикс**: `pip install -e . + USER app`, сверка Dockerfile ⊇ pyproject в CI; починить `.dockerignore`, пин `nginx:1.27-alpine`.

## 4. P1 — надежность, фронт-архитектура, инфра

* **Контракт ошибок/пагинация не соблюдаются**: в `main.py` только `IntegrityError→409` (`core/errors.py:16-20`), нет handlers `RequestValidationError/HTTPException→ErrorResponse+request_id` (`schemas/common.py:175` определен, но не используется). `core/pagination.py:paginate + PaginatedResponse` не используются — вместо них `.limit(200).all()` + фильтр в Python (`documents/router.py:28-35`, `audit/router.py:29-34`).
* **RBAC не включен**: `catalog` и все 3 `imports`-эндпоинта — только `get_current_user`; любой `user` может лить каталоги. Нужен `require_permission("import.write")` и т.д.
* **Fail-open места**: `task_queue.py:19-43`, `redis.py:18`, `storage.py:27-49` — `except Exception: pass` → тихий in-memory/local fallback; `entrypoint.sh:32` — `baseline || true` маскирует ошибку; `config.py:10 extra="ignore"` + скип миграций без `DATABASE_URL` («SQLite dev mode») — сервер стартует с расходящейся схемой.
* **Фронт-долги**: `AuthProvider.tsx:37-39` глотает ошибку `init` (экран «Войти» без диагностики); нет `onTokenExpired`/silent-refresh — долгоживущая страница упадет после idle; `keycloak.ts:8-9` hardcoded `realm/clientId`; `App.tsx:26-31` health-check в обход клиента; нет `test/lint/format` скриптов, нет `eslint/prettier/vitest`; нет `react-router/@tanstack/react-query/react-hook-form/zod` — текущий `useState + apiFetch` не масштабируется; `tsconfig` без `noUnusedLocals/noUncheckedIndexedAccess`; CSS — ноль `@media` (360px переполняется), нет `:focus-visible`, статусы только цветом, нет `aria-live`.
* **Инфра**: `keycloak: start-dev` (нужен `start --optimized` для продакшена-стенда); все порты наружу (`5433/8081/8000/3000`), нет `restart/networks/logging`; нет healthcheck у frontend, Keycloak-проба хрупкая (`bash /dev/tcp + grep " 200 "`, старт до ~6 мин); `nginx/nginx.conf` — orphan-gateway, не подключен к compose; `pgdata` — анонимный volume без бэкапа; `entrypoint` стартует uvicorn без `--proxy-headers`.

## 5. P2 — безопасность / 152-ФЗ + ФСТЭК-117 (требование кейса)

Сейчас — ноль фич, это минус на экспертизе:
* Нет согласия на ПДн / политики / чекбокса; нет маскирования email/ФИО по ролям (моки `docs/mocks/*.json` отдают ПДн открытым текстом без пометки «синтетика»); нет ЛК субъекта (скачать/удалить); нет SPA idle-локаута (только Keycloak `ssoIdle 1800s`); нет пользовательской видимости аудита.
* `change-me` везде (`.env.example`, compose `:-change-me`), секреты в `environment:` видны в `docker inspect`, нет CI-guard `grep change-me`, нет Secrets/vault.
* `allow_credentials=True + allow_methods/headers=["*"]` (`main.py:43`) — браузеры такую комбинацию режут; `FRONTEND_ORIGIN` — один origin, лечится same-origin прокси, а не `*`.
* Аудит несовместим с auth: `migrations/000006_audit.up.sql:19,21` — `user_id/entity_id INTEGER`, а `CurrentUser.id: str (sub)`. `fullScopeAllowed: true` в realm — избыточные права токенов.
* `docs/DEPENDENCIES.md` — только ручная таблица, нет `syft`/CycloneDX-артефакта; `.gitignore` — только `.env` (`.venv/.pytest_cache/*.xlsx` не покрыты, `.pytest_cache/` уже был закоммичен).

## 6. Разрыв с кейсом (14 шагов workflow)

Покрытие workflow «взаимодействие с вузом»:

| Шаги | Статус |
|---|---|
| 1–3. Поиск контактов, коммуникация, встречи | 🟡 канонические `responsibles`/`meetings` есть; workflow-instance и comments доступны через API, UI ещё нет |
| 4–6. Документы, подписание | 🟡 единый `documents` уже есть; Б2 добавляет attachment-связь, статусы подписания ещё впереди |
| 7–8. Материалы, лицензии, внедрение | 🟡 `licenses/contracts` + статусы и этапы workflow; предметные выдачи/внедрения ещё впереди |
| 9–13. Обучение преподавателей, программы, КПК | 🟡 канонические таблицы и этапы есть; специализированные связи и UI ещё впереди |
| 14. Контроль каждого этапа | 🟡 runtime Б2: этапы, переходы, optimistic revision, история, задачи; SLA-воркеры/напоминания и канбан ещё не сделаны |

Что заложено в Б2: **единая модель жизненного цикла** (`interaction_pipeline`: вуз × программа × продукт × этап × due date), все доменные PK — UUID, actor хранится как `keycloak_sub: str`, единый реестр `documents`, append-only история переходов и audit event в одной транзакции. Следующий слой — отдельная привязка ответственных, UI канбан/таймлайн, SLA-воркеры и уведомления.

## 7. Рекомендации по приоритету

**P0 — до демо на чужом хосте (1–2 дня):**
1. Runtime-конфиг фронта (`/config.json` + `envsubst`), убрать build-ARG; `KEYCLOAK_ISSUER` без литерала; realm `redirectUris` параметризовать.
2. Same-origin `/api/`-прокси (nginx + `vite server.proxy`), dev-проверка не через `localhost:8000` напрямую.
3. `apiFetch`: method/body/signal, 204/content-type guards, 401-ветка, guard `Bearer undefined`, анти-loop флаг; `ErrorBoundary` + экран ошибки Keycloak с ретраем; `onTokenExpired → updateToken(60)`.

**P0 — до включения домена (3–5 дней):**
4. Удалить legacy `modules/*/models.py + schemas.py`, переписать `router+service+repository` на `app.models + app.schemas` (UUID); `files → documents`; `audit user/entity → String/UUID`; `users → responsibles.keycloak_sub`; `alembic/` — удалить/заморозить, SQL — единственный источник + CI-gate `check_migrations.py`.
5. `Dockerfile → pip install -e . + USER app`; `session.py → get_engine(url)`; `entrypoint.sh` — падать при несхождении миграций, убрать `baseline || true` и «SQLite dev mode».
6. Везде `require_permission/require_role`; хендлеры `ValidationError/HTTPException → ErrorResponse + request_id`; `.limit(200)` → `PaginatedResponse`; `execute_import` в воркер (Redis-статус, staging в volume); `infrastructure/keycloak.py` удалить или сделать единственным источником (`python-jose → pyjwt`, он deprecated).

**P1 — до технической экспертизы:**
7. Раскиповать `test_mvp.py`; PG-интеграция в CI (`TEST_DATABASE_URL`); тесты «роутеры смонтированы», «Dockerfile ⊇ pyproject», нагрузочный тест импорта; `session` без engine на импорте.
8. Фронт-каркас: `react-router + react-query + hook-form/zod`, типы из `components/` в `types/`, `ErrorBoundary`, `aria-live`, `:focus-visible`, брейкпоинты; `lint/format/test` скрипты, `noUnusedLocals`, `HEALTHCHECK`, `gzip/headers/cache-policy` в nginx, пин `nginx:1.27-alpine`, починить `.dockerignore`.

**P2 — баллы 152-ФЗ/ФСТЭК и гигиена:**
9. Чекбокс согласия + политика, «Мои данные: скачать/удалить», маскирование `a***@` по ролям, idle-локаут SPA 15 мин, закрыть PG/Keycloak (`expose`), `restart/networks/logging`, CI-guard `grep change-me`, бэкап `pgdata`, `syft` SBOM, `SYNTHETIC-DATA.md` для моков, один `EXPIRY_WARNING_DAYS`, `curator` в `UserRole`.

## 8. Контрольный чек-лист перед сдачей

* [ ] Стенд по IP/hostname (не localhost): логин, `/me`, импорт, паспорт вуза.
* [ ] `docker compose up --build` с нуля + `migrate.py verify` + повторный `seed` без дубликатов.
* [ ] Все роутеры в OpenAPI; ни одного `int`-PK в домене; `ErrorResponse` и пагинация везде.
* [ ] Импорт 5000 строк не вешает HTTP; рестарт не теряет `file_id`.
* [ ] Нет `change-me` в образе; PG/Keycloak не торчат наружу; SBOM приложен.
* [ ] 152-ФЗ минимум: согласие, маскирование, «скачать/удалить», idle-локаут.
* [ ] Хотя бы скелет пайплайна 14 шагов виден в UI (канбан/таймлайн вуза).

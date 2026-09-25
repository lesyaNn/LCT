# Полное ревью бэкенда

Дата: 2026-09-25. Ветка `develop`, HEAD `9d6077a` + незакоммиченные изменения в рабочем дереве
(важно: часть находок `BACKEND_REVIEW.md` от 2026-09-24 в дереве уже исправлена — ниже
зафиксировано актуальное состояние именно рабочего дерева).
Метод: чтение кода всех слоёв (`app/core`, `app/models`, `app/modules/*`, `app/db`,
`app/infrastructure`, `migrations/`, `tests/`, `Dockerfile`, `entrypoint.sh`, `scripts/`,
`docker-compose.yml`, `.github/workflows`), три параллельных аудита (core/auth, домены,
БД/инфра/тесты) + точечная сверка ключевых мест (`imports`, `workflow_transitions`,
`report_jobs`, `catalog`). Живой стенд (Postgres/Redis/Keycloak), `docker compose up`
и нагрузочные прогоны не выполнялись — пункты, требующие живой БД, помечены
`NEEDS VERIFICATION`. Код не изменялся.

Связанные документы: `BACKEND_REVIEW.md` (ревью от 24.09, частично устарело —
C1/C2/H2/H6/H7/M6/M10 там уже закрыты в дереве), `REVIEW_REPORT_P1_P2_P4.md`
(соответствие задачам P1/P2/P4).

---

## 1. Executive Summary

Бэкенд — модульный монолит на FastAPI + SQLAlchemy 2.0 (sync) + PostgreSQL 16,
Keycloak JWT (RS256/JWKS), RBAC + data-scope политики, единый формат ошибок
`ErrorResponse`, аудит через `audit_events` + outbox-relay, worker для отчётов
(`SKIP LOCKED`, ретраи), Redis-кэш с in-memory fallback. Миграции — raw SQL
`backend/migrations/000001..000023` (источник истины), Alembic архивирован.
OpenAPI генерируется (`custom_openapi`, BearerAuth), CI
`.github/workflows/backend.yml` существует.

Что изменилось со вчерашнего ревью (незакоммиченные правки в дереве, проверено чтением кода):

- C1 (path traversal в импорте) — **исправлен**: `_FILE_ID_RE = ^[0-9a-f]{32}$` + `fullmatch`
  + `resolve()/relative_to` containment (`imports/service.py:54,163-178`).
- C2 (буферизация всего файла в RAM) — **исправлен**: чанки 256 KiB с mid-stream 413
  (`imports/router.py:137-147`), аналогично attachments.
- H2 (пост-коммит writers с `except: pass`) — **частично исправлен**: теперь
  `logger.exception` с `exc_info` + `rollback` (`workflow_transitions/service.py:194-212`).
  Дрейф стал видимым, но outbox-ретрая для health-materialization нет.
- H6 (Redis: I/O на импорте, приватный доступ) — **частично исправлен**: ленивый коннект,
  reconnect-cooldown, публичные `cache_delete/cache_delete_pattern`; остались глобалы
  `_memory` без лока и без eviction.
- H7 (мёртвая `task_queue`) — **исправлен**: `infrastructure/task_queue.py` удалён;
  единственная очередь — леджер `report_jobs`.
- M6 (мёртвый `core/pagination.py`) — **исправлен**: файл удалён, пагинация живёт в
  `schemas/common.py` + инлайн `Query(ge=1,le=100)`.
- M10 (нет rate limiting) — **исправлен на уровне механизма**: `RateLimitMiddleware`
  + `core/rate_limit.py` + `RATE_LIMITED_PATHS`; остались дефекты реализации
  (неатомарный инкремент, бакет по токену, unbounded локальный fallback) — см. M10 ниже.

Актуальный подсчёт проблем рабочего дерева: **CRITICAL — 0, HIGH — 5, MEDIUM — 12, LOW — 8**.
Закрытых вчерашних CRITICAL больше нет; новых CRITICAL чтением кода не выявлено
(подтверждение отсутствия SQLi/traversal/auth-bypass — раздел 9).

Главные оставшиеся риски:

1. Аудит тихо no-op без `audit_context` (HIGH) — записи через голый `get_db` (35 мест)
   теряют события без сигнала.
2. Несогласованные `ON DELETE`: `WorkflowInstance.university_id → CASCADE` сносит
   workflow-историю при удалении вуза, тогда как весь P1-каталог — `RESTRICT` (HIGH).
3. Rate-limit неатомарен + бакет по полному токену + unbounded локальный fallback (HIGH).
4. Scope-проверка после загрузки в teacher-passport и health-router ( timing-oracle,
   лишний SELECT) + `GET /catalog/overview` с `page_size ≤ 500` (HIGH/MEDIUM).
5. Outbox-relay никогда не пишет `failed`, ретрай без backoff — hot-loop (MEDIUM).
6. Двойная формула Health Score (взвешенная vs штрафная) + SQL в роутерах health/imports
   + unbounded `list_transitions` без пагинации (MEDIUM).

---

## 2. Project Overview

### Компоненты

```text
backend/app/main.py                  FastAPI, CORS allowlist, RequestSizeLimit +
                                     SecurityHeaders + RateLimit, request_log_middleware,
                                     register_error_handlers, custom_openapi (BearerAuth),
                                     /health, /ready (без раскрытия auth-конфига)
backend/app/api/router.py            агрегатор v1 (/api/v1), 15 роутеров; порядок важен
                                     (health_router до catalog: /health-score batch
                                     иначе перехватывается /{id})
backend/app/modules/*/              домены: router + service + repository + schemas (канон);
                                     часть — deferred/stub, НЕ смонтированы (quarantine guard)
backend/app/core/                    errors, exceptions, security (JWT), permissions (RBAC),
                                     policies (data-scope), logging (SensitiveFilter),
                                     middleware, rate_limit (новый)
backend/app/models/                  ORM на Base; DeferredBase для stub-моделей вне миграций
backend/app/schemas/                 контракт: common (пагинация), catalog, university,
                                     teacher, licenses, errors
backend/app/db/                      session (engine/SessionLocal, пул настроен),
                                     seed, seed_workflow, transaction-хелпер
backend/app/services/                чистые функции: cache, license_status, teacher_readiness
backend/app/infrastructure/          redis (lazy+fallback), storage (legacy, см. H5),
                                     http_client (глобальный AsyncClient)
backend/app/modules/analytics/report_worker.py  воркер отчётов (SKIP LOCKED, x3)
                                       + outbox-relay тик каждые ~2с
```

Активные домены: `auth`, `universities/passport`, `teachers/passport`, `catalog`
(universities/directions/programs/products/vendors/responsibles + overview), `meetings`,
`students`, `workflow_templates`, `workflow_instances`, `workflow_transitions`
(+comments), `workflow_attachments`, `health_score` (health/ranking/attention/history/
materialization), `analytics` (overview/matrix + reports xlsx/pdf/json + jobs/worker),
`imports` (preview/execute/jobs/report), `audit` (+relay/outbox).

### Технологии

- API: `FastAPI==0.116.1`, `uvicorn[standard]==0.35.0`, `Pydantic==2.11.7`,
  `pydantic-settings==2.10.1`, `python-multipart==0.0.32`.
- Auth: Keycloak 26.7.4 (realm `rtk`, client `rtk-frontend`, PKCE),
  `python-jose[cryptography]`, RS256 JWKS, RBAC `admin/manager/curator/user`.
- DB: PostgreSQL 16, `SQLAlchemy==2.0.43`, `psycopg[binary]==3.3.4`, raw SQL миграции
  `000001..000023` + `schema_migrations`; Alembic только архив. `Redis==6.4.0`,
  `MinIO==7.2.18` (S3-seam, default local).
- Отчёты/импорт: `openpyxl==3.1.5`, `xlrd==2.0.2`, `reportlab==4.4.9`, `httpx==0.28.1`,
  `python-dateutil`.
- Тесты/линт: `pytest==9.0.3`, `ruff` (line-length 100), pure-unit без PG vs интеграция
  через `TEST_DATABASE_URL` (`DROP SCHEMA + up` изоляция в `conftest/db_helpers`).
- Инфра: `docker-compose.yml` (postgres, redis, keycloak:8081, backend, worker, frontend),
  `backend/Dockerfile` multistage (`appuser:10001`), nginx same-origin `/api/` прокси.
  CI `.github/workflows/backend.yml` (lint, unit, postgres, openapi, smoke).

### Точки входа / БД / внешние сервисы

- Entrypoint: `backend/entrypoint.sh` ждёт PG → `migrate.py baseline` (адопт legacy Alembic)
  → `up` → `verify` → `uvicorn app.main:app --proxy-headers`. Без `DATABASE_URL` — `exit 1`.
- БД: 21 таблица ядра P1 + 8 workflow + `report_jobs/import_jobs/job_attempts/`
  `audit_events(+p5)/health_score_current/health_score_snapshots/audit_outbox`.
  PK UUID генерит приложение (`UUIDPKMixin`), даты `timestamptz`.
- Внешние: живых LMS/Website нет (стаб deferred, отвечает 410); S3 — реальный
  `S3StorageBackend`, default local `/app/storage`; Redis — кэш/health/rate-limit;
  Keycloak — единственный IdP.

---

## 3. Сквозные механизмы (core)

### 3.1. Auth: `core/security.py` — хорошо

- Fail-closed: подпись/`exp`/`iss`/`aud` обязательны (`validate_token:122-154`);
  ошибка сети/малформа JWKS → `EXTERNAL_SOURCE_UNAVAILABLE`, без trust-payload fallback.
- `alg` строго RS256, `kid` обязателен, refresh при unknown kid (`:108-118`).
- Явная проверка `aud` (компенсация `python-jose`), `sub` обязателен.
- JWKS-кэш с `threading.Lock`, TTL 600; санитизация ролей для лога.
- `auth_dev_bypass` только при отсутствии credentials + gate по env.
- Риски (LOW): `_fetch_jwks` через `urllib.urlopen(timeout=5)` без явного TLS-контекста;
  `https` для issuer в prod не enforced (см. 3.5); `_dev_user` — роль `admin` → при
  случайном включении bypass даёт полный доступ (митигировано валидатором конфига).

### 3.2. Data-scope: `core/policies.py` — хорошо, одна пометка

- Fail-closed: missing/empty `university_ids` → `DENY`/`where(false())`
  (`get_data_scope:37-55`, `apply_university_scope:63-64`); `allows` ловит
  `ValueError/TypeError → False`.
- `admin → ALL`, `curator` scope не расширяет — закрыт классический fail-open.
- Два уровня: `ensure_university_access` (403) vs `ensure_university_visible` (404,
  anti-enumeration).
- Пометка (INFO): `ScopeKind.GROUP` vs `OWN` дальше не различаются — оба фильтруются
  одинаково по `in_(ids)`. Сейчас `kind` только маркер; при появлении per-kind логики
  легко ошибиться.

### 3.3. RBAC: `core/permissions.py` — хорошо, мелочь

- `MappingProxyType` (immutable), `require_permission` fail-closed на
  незарегистрированное право (ошибка на старте), единый precedence
  `admin>manager>curator>user`.
- Мелочи (LOW): `require_role` с неявным admin-bypass расходится с именем декоратора
  (осознанно, но стоит комментарий в коде); `PUBLIC_ROLE_NAMES` нигде не используется;
  двойная семантика `"*"` у admin (содержит и `"*"`, и все конкретные права) — хрупко.

### 3.4. Ошибки: `core/errors.py + exceptions.py + schemas/errors.py` — отлично

- Единый envelope `ErrorResponse`, `X-Request-ID` везде, `WWW-Authenticate: Bearer`.
- `SecurityError` всегда с пустыми details; `_safe_details` режет
  `password|token|…`, DSN, `/tmp/`; `_validation_details` режет секреты в field/msg;
  `_conflict_details` отдаёт только имя колонки по allowlist/регексу.
- Код ошибки только из типированного значения (`_code_for_http`), никогда substring
  из текста — хрупкий маппинг по подстроке из старого ревью устранён.
- Риски (LOW): `BusinessException` кладёт исходный message в `args` — вне
  `SensitiveFilter` может утечь в чужие логи; `_integrity` логирует полный `exc_info`
  (SQL/значения драйвера, фильтр режет только секреты/URL).

### 3.5. Config/CORS: `app/config.py + main.py` — хорошо с оговоркой

- `auth_dev_bypass=False` + валидатор (только dev/test/local); prod запрещает CORS-`*`
  и требует S3-креды; демо-дефолты кредов убраны.
- CORS замкнут: методы `GET/POST/PATCH/PUT/DELETE/OPTIONS`, заголовки
  `Authorization/Content-Type/Accept/X-Request-ID`.
- Оговорка (MEDIUM, бывший H-риск частично жив): `allow_credentials=True` + wildcard
  запрещён только для prod; в `dev/staging` комбинация `["*"] + allow_credentials`
  возможна — лечить запретом `*` при `allow_credentials` во всех env. Плюс:
  нет требования `https` для issuer/JWKS в prod; дефолты localhost; `extra="ignore"`
  молча глотает опечатки в env; `settings = Settings()` на импорте.

### 3.6. Middleware: size-limits + security headers — хорошо; rate-limit — с дефектами

- `RequestSizeLimitMiddleware` ASGI-нативный (подсчёт тела, `Content-Length`-спуфинг
  и chunked не обходят); слоистые лимиты: фрейминг 51 MiB → сервис 50 MiB exact →
  импорт 10 MiB. CSP без wildcard, `frame-ancestors 'none'`.
- `RateLimitMiddleware` (новый): fail-open при падении кэша, identity хэшируется.
- Дефекты rate-limit (HIGH в совокупности, M10):
  1. Неатомарность: `GET → int → INCR` отдельными командами (`rate_limit.py:38-46`) —
     конкурентный burst проходит выше лимита. Нужен `INCR+EXPIRE`/Lua.
  2. Бакет по полному токену (`middleware.py:237` хэширует весь `Authorization`) —
     ротация JWT = новый бакет = обход. Правильно — стабильный claim (`sub`).
  3. Локальный fallback без eviction (`rate_limit.py:13,50-56`) — растёт бесконечно,
     TTL только ленивый.
  4. Точное совпадение пути (`:231`): trailing slash (`/catalog/overview/`) обходит лимитер.
  5. (LOW) `_too_large_response` отдаёт `limit_bytes` в details — мелкое раскрытие конфига.

### 3.7. Logging: `core/logging.py` — хорошо, мелочь

- Редакция Bearer/DSN/секретов, рекурсивный `_redact_value` с depth-cap, фильтр на
  root+uvicorn и на каждый запрос; `X-Request-ID` валидируется как UUID; логгер
  никогда не роняет запрос.
- Мелочи (LOW): `logging.basicConfig` на импорте перетирает конфигурацию хоста;
  `request.state.user_id` никто не ставит → в логах всегда `-`, привязка по логам не работает.

### 3.8. Auth-модуль и тестовые эндпоинты

- `modules/auth/` — тонкий (`/auth/me`, `/auth/test/*`), своей JWT-логики нет.
- Пометка (LOW): тестовые `test/authenticated|admin|workflow-change` смонтированы и в
  prod — поверхность для fingerprinting; лучше gate по env.

---

## 4. Аудит и кэш/инфраструктура

### H1. Аудит тихо no-op без контекста — HIGH (остаётся)

- Факт: `catalog/repository.py:58,636,648,670,680`, `meetings/service.py:53,83`,
  `students/service.py`, `workflow_instances/service.py:212-214`,
  `workflow_attachments/service.py:107-110`, `audit/service.py:231` — без
  `db.info["audit_context"]` событие молча пропускается. Воркеры/скрипты/прямые
  вызовы = дыры в ленте без сигнала.
- Дополнительно: `context_for` при отсутствии контекста фабрикует
  `AuditContext(actor,actor,"user")` — риск ложной атрибуции.
- Масштаб: голый `Depends(get_db)` — 35 вхождений (подсчитано grep). Для чистых чтений
  это норма (`audit/router.py:69` осознанно read-only под `require_permission`),
  но любое пишущее место через `get_db` вместо `get_audit_db` тихо теряет аудит.
- Сильные стороны механизма (сохранить): writer не коммитит, outbox санитизирует до
  durable-границы (cap 8 KB, режет секреты/JWT/bytes); read-роутер применяет scope
  до `count()`; relay идемпотентен (`ON CONFLICT DO NOTHING` / check-then-insert,
  `SKIP LOCKED`, `limit<1 → 0`).
- Рекомендация: `logger.warning` при пропуске + lint-gate «пишущий роут обязан
  `get_audit_db`»; убрать фабрикацию `context_for` или маркировать `role="system"`.

### Кэш/Redis — MEDIUM (улучшен, остались глобалы)

- Исправлено: никакого I/O на импорте, reconnect-cooldown 5с, все вызовы guarded с
  деградацией в память; инвалидация через публичные хелперы `cache_delete/
  cache_delete_pattern` (докстринг запрещает трогать `_memory`).
- Осталось: `_memory/_client/_client_broken_until` — module-глобалы; `_memory`
  читается/пишется в `cache_get/set/delete` без лока (лок только в
  `_connect/_mark_broken`); `_memory` unbounded, TTL-чистка только lazy в `cache_get`.
  Многопоточный uvicorn = потерянные записи + рост памяти.
- Мелочи (LOW): приватность `_memory` не enforced (`__all__` нет) — добавить;
  `md5` для ключа (не крипто, но лучше `sha256`); `@cached` кэширует по `args` включая
  `db`-сессию — ключ нестабилен; `cache_delete_pattern` делает `scan_iter +
  delete(*keys)` одним вызовом — на большом keyspace блокирует Redis.
- Health-кэш: `health_score:{id}` TTL 300, ranking TTL 600 с ключом без user/scope —
  чтение только при `global_scope` (верно, но хрупко); attention-ключ с inline `300`
  вместо константы; ranking-ключ не включает фильтры кроме status/limit/offset.

### Storage — канон силён; legacy traversal — H5 (HIGH, если модуль жив)

- Канонический путь (`workflow_attachments/{storage,policy,service,router}`) — образцовый:
  физ. имена `uuid.hex`, `original_filename` только метаданные; `_checked_key`
  отвергает `../ / \ :`; Local — `tmp + os.replace` атомарно; S3 — bounded tmp ≤50 MiB;
  `size()` сверяется с объектом, не с БД; `sanitize_filename` (NUL/CRLF/control/drive/
  traversal, cap 255); env-allowlist типов (иначе 415); `normalize_mime_type` без
  угадывания; `content_disposition` RFC 6266/5987; лимиты тройные (middleware 51 MiB →
  `_limited_chunks` 413 mid-stream → 50 MiB exact); цепочка `attachment→instance→
  university`, кросс-инстанс → 404; delete идемпотентен.
- Legacy `infrastructure/storage.py` — HIGH, если где-то используется:
  `save_file:36` (`uuid_filename` с несанитизированным именем → `open(join(LOCAL_DIR))`)
  и `read_file:45` (join без containment-check) — path traversal; плюс fail-open:
  любая ошибка MinIO → молчаливое локальное сохранение. Проверить отсутствие импортов
  и удалить модуль, если канон покрывает всё.
- `storage._cached_build` игнорирует смену S3-кредов (lru_cache без кредов в ключе) —
  LOW-MEDIUM, лечится хешем кредов в ключе.
- `http_client.py` — глобальный `AsyncClient` без `close()`/лимитов — LOW (висящие keep-alive).

### Очереди/воркеры — хорошо

- Мёртвая `task_queue` удалена; единый леджер `report_jobs` + `report_worker.py`
  (claim `FOR UPDATE SKIP LOCKED`, `queued→building→ready|failed`, max 3 попытки).
- HTTP только создаёт job (202), `BackgroundTasks` запрещены; воркер открывает свежий
  `SessionLocal` на job — request-сессия не утекает.
- `claim_next_job` — stale-recovery 30 мин, затем `SKIP LOCKED` только на PG, иначе
  атомарный `claim_job UPDATE WHERE queued+attempts<3` с проверкой rowcount — двойное
  исполнение исключено. `mark_building` (неатомарный read-modify-write) воркером не
  используется — ок.
- Legacy `notifications`/`reporting` importable, но отвечают `410 GONE` (fail-closed) —
  не маунтить, в идеале вынести из сборки.
- Outbox-relay дрейф (MEDIUM): SQL `CHECK status IN ('pending','published','failed')`,
  но relay на ошибке пишет `status='pending' + attempts+=1` — `failed` недостижим,
  ретрай без backoff (hot-loop каждые ~2с из `report_worker.main`). Добавить backoff и
  терминальное `failed` после N попыток.

---

## 5. Доменные модули

### 5.1. Catalog — эталон, minor-замечания (MEDIUM/LOW)

- Слоистость соблюдена: router тонкий (params→RBAC→service→DTO, SQL нет), service —
  маппинг+`NotFound`, repository — только SELECT/записи. Whitelist `ORDER BY` +
  tie-break id, `like_pattern` escape, `IntegrityError→409` центрально.
- N+1 нет: list — ровно COUNT+page; M:1 через JOIN; detail — 1–2 statement; overview —
  `selectinload`.
- Пагинация везде `page/page_size le=100`; исключение — `/catalog/overview`
  `page_size le=500` (осознанно, но тяжёлый эндпоинт + см. rate-limit).
- Scope: detail — scoped SELECT (404 и для missing, и для чужого — правильно); list —
  `UnifiedFilterService.apply_security_scope` на COUNT и page. Но `patch/delete/assign` —
  `ensure_university_visible` в роутере + unscoped `repo.get_university` в сервисе:
  TOCTOU и два запроса вместо одного scoped SELECT (MEDIUM, быстро чинится).
- Мёртвый код: `list_university_candidates` никем не вызывается (service перешёл на
  `list_universities_health`); deprecated `region` no-op вводит в заблуждение
  (200 с полной выборкой) — лучше 410 или удалить; `LEGACY_CATALOG_WRITE` пометить.
- `delete_university` pre-check 11 таблиц + 409 — хорошо.

### 5.2. Passport вузов — хорошо, god-файл (MEDIUM)

- Тонкий роутер (3 endpoint), фасад-реэкспорт, SQL в `passport_loading.py`, сборка в
  `passport_blocks.py` (951 строка — god-файл, кандидат на split
  `passport/{blocks,loaders,dto}.py`).
- N+1 нет по конструкции: ≤8 SELECT (UNION ALL блоки 6–7), subresources с SQL
  LIMIT/OFFSET+COUNT. Лимиты именованы (`DOCUMENTS 20, MEETINGS 10, TIMELINE 10, AUDIT 5`).
- `parse_include` — 422 на неизвестный include, graceful degradation health/audit.
- Дефекты (MEDIUM в совокупности): публичные `get_programs/get_teachers/get_documents`
  принимают только `(db, university_id)` без `user` — при переиспользовании scope
  обходится; `_optional_block_failed` глотает health/audit в `None/[]` (задокументировано,
  но тихий деград — добавить метрику); `assert` на readiness упадёт в проде при
  рассинхроне (заменить на ветвление); `literal(None, type_=Uuid())` — `Uuid` не
  импортирован (NameError на этом пути — проверить/покрыть тестом); `_load_program_rows`
  INNER JOIN direction роняет программы без direction (нужен LEFT JOIN).
- Dead stubs: `get_workflow_transitions_raw()->[]`, `get_workflow_summary()`-пустышка.
- Дубли `_ensure_tz` (passport_blocks ≈ teachers/passport_service + `_ensure_tz_aware` ×3
  в analytics) → вынести в `app.core.datetime_utils`.

### 5.3. Passport преподавателей — scope после загрузки (MEDIUM)

- Ровно 4 SELECT с JOIN, N+1 нет; read-only.
- Проблема: роутер требует только `university.read`, а `ensure_university_access`
  делается после загрузки строки (`passport_service.py:126-133`) — unscoped load +
  timing-oracle (чужой vs missing различимы). В catalog решено scoped SELECT —
  сделать так же.
- Legacy `teachers/router.py` — SQL в роутере, int PK, `limit(200)` без пагинации,
  только `get_current_user` без RBAC/scope; по собственному docstring UNMOUNTED —
  удалить или вынести из сборки (Dockerfile уже чистит часть quarantine — проверить,
  что этот файл в списке).

### 5.4. Meetings / Students — чисто, двойной запрос (LOW/MEDIUM)

- Тонкие роутеры, N+1 нет (COUNT+page), сортировки детерминированы, пагинация 20/100.
- Students: `_ensure_program_belongs_to_university` — 422 с `field_errors` (хорошо).
- Неэффективность (LOW): каждый list/create делает лишний `db.get(University)` +
  затем scoped check — два запроса вместо scoped SELECT; create студента — 3 SELECT
  подряд (можно одним). Copy-paste `_get_university_or_404` и `_snapshot/_audit`
  между meetings и students — вынести в общий хелпер.
- Фильтров/поиска нет (meetings без type/date_from/date_to, students без
  status/program) — если требуется спекой P1-03-06/07-01/08-01, это PARTIAL
  (см. REVIEW_REPORT_P1_P2_P4).

### 5.5. Workflow templates — лучшие транзакции, без замечаний уровня HIGH

- `SELECT...FOR UPDATE`, shift+insert атомарно (deferred UNIQUE), move без дыр,
  retire-guard `_ensure_no_active_current→409`. N+1 нет (`selectinload(stages)`).
- `ADMIN=require_role("admin")` на всех роутах — корректно для глобального конфига.
- Мелочи: нет list-фильтров (ок для конфига); repository-файла нет (SQL в сервисе —
  допустимо для P2, но непоследовательно с catalog).

### 5.6. Workflow instances — логика в роутере (MEDIUM)

- Создание атомарно (header+snapshot+pointers+transition, один commit), затем второй
  commit для аудита (осознанно: создание не откатится при падении аудита — см. H1).
- Нарушение: RBAC-ветвление в роутере (`router.py:50-55` — `user_permissions`,
  `roles.intersection(...)`, `SecurityError`) — должно жить в service/policy.
- Нет list-эндпоинта (только POST + GET by id) — усложняет UI; отсутствие списка —
  осознанное решение или gap — зафиксировать.
- Кэш: своей нет, инвалидация из transitions — правильно.

### 5.7. Workflow transitions/comments — god-файл + unbounded history (MEDIUM)

- `service.py` 374 строки (transitions+comments+validate) — кандидат на split.
- Двойная загрузка: роутер `get_instance_or_404+authorize_scope`, затем сервис снова
  `SELECT...FOR UPDATE` — 2 SELECT инстанса на запрос (объединить).
- **`list_transitions` возвращает весь список без пагинации** — риск при длинной
  истории (добавить COUNT+page как у comments).
- Пост-коммит health-каскад теперь с `logger.exception+rollback` (исправление H2
  подтверждено) — дрейф видим; следующий шаг — outbox/ретраи + метрика
  `health_materialization_failures_total`.
- Транзакция transition — один commit (закрытие+skip+указатели+history+audit enqueue) +
  `with_for_update`. Авторское окно 15 мин именовано, 409 — корректно.
- Copy-paste `get_instance_or_404` ×3 (instances/transitions/attachments) — вынести в core.

### 5.8. Workflow attachments — хорошо, утечки политики в роутер (LOW/MEDIUM)

- См. раздел 4 (storage образцовый). Транзакции: upload — storage write затем DB commit,
  при исключении `rollback+storage.delete`; delete идемпотентен
  (`StorageObjectNotFound→pass`, `StorageError→500` без false-204).
- Нарушения слоистости (LOW): author-or-admin check inline в роутере (`:178-182` +
  локальный import SecurityError — вынести в service); роутер делает `storage.size()`
  и ручной `opener.__exit__` в генераторе — хрупко при обрыве стрима (обернуть
  try/finally или отдать в service).
- `except Exception: verified_size=None` (`router.py:149`) — тихий fallback на chunked;
  добавить лог.

### 5.9. Health Score — самый фрагментированный (MEDIUM)

- Формулы компонент T/D/S/E/L детерминированы, веса `0.25/0.20/0.20/0.20/0.15`,
  пороги 85/60 — single source (`status.py` используется и в PDF). Breakdown + reasons +
  counters + tz — хорошо.
- **Две формулы (MEDIUM)**: `aggregate.WEIGHTS` (взвешенная) vs legacy
  `service.PENALTIES` (100-minus-penalties на `db.query(Task)` с `university_id: int`,
  несовместим с UUID-схемой) + паспорт использует штрафную `compute_score`.
  Три источника истины — оставить один, legacy `router.py/service.py` (int PK, только
  `get_current_user`, без RBAC/scope) удалить как unmounted dead.
- **SQL в роутерах (MEDIUM)**: `health_router.py:90-95,128-130,162-164,205-207,213-222`,
  `ranking_router.py:66-83` (join+window+count) — вынести в repository/service.
- **Scope после загрузки (MEDIUM)**: existence-check до scope (`:128-133,162-167,205-210` —
  unscoped `select(University.id)` → 404, затем `ensure_university_visible` → 403;
  чужой vs missing различимы). Batch делает правильно (scoped `IN`) — распространить.
- Batch считает последовательно в цикле (N×5 запросов, `BATCH_MAX_IDS=50`) —
  обосновано (sync Session нельзя делить), лимит держит.
- `materialization.refresh_health_score` — caller owns tx, upsert current + snapshot
  first-write-wins; `backfill_*` коммитят батчами keyset; advisory lock magic `24110901`
  — вынести в константу. `snapshots.write_transition_snapshot` — `except: return False`
  без лога (тихий swallow — добавить `logger.exception`, возврат bool смягчает).
- Кэш см. раздел 4.

### 5.10. Analytics — хорошо, god-файлы экспорта (LOW/MEDIUM)

- Тонкий роутер, batch-load repository (`raiseload("*")`, `joinedload`), чистые агрегации
  в service; горячий путь без N+1 (~12 SELECT независимо от размера); циклы matrix —
  по уже загруженным коллекциям.
- Scope до чтения кэша/БД, ключ включает user/roles/scope/provider/day — правильно;
  `select_scoped` else `EXTERNAL_SOURCE_UNAVAILABLE`; read/write кэша обёрнуты
  `try/except→logger.warning` (outage кэша не роняет БД).
- Matrix-guard `50_000 → 422`, фильтры через strict `FILTER_KEYS`, `CACHE_TTL=60`.
- К разделению: `dataset.py` 620, `pdf.py` 569, `report_jobs.py` 520 строк — кандидаты
  на split; `_ensure_tz_aware` ×3 → общий хелпер; `BUCKETS/LEGEND/PROGRAM_STATUSES`
  именованы — хорошо.
- Отчёты (`reports_router`, `report_service`, `xlsx/pdf/json_export`) — 202 + реальный id,
  XLSX 2 листа/freeze/filter/sanitize от формул-инъекций, PDF DejaVu без mojibake,
  JSON `ensure_ascii=False` + ISO-даты. Повторный `POST /reports` плодит jobs —
  idempotency-ключа нет (в отличие от импорта) — LOW/MEDIUM, добавить по аналогии.

### 5.11. Imports — исправлен, осталась производительность (MEDIUM)

- Подтверждено исправление C1 (hex32 + containment) и C2 (чанки 256 KiB, mid-stream 413).
  `_escape_like` закрывает LIKE-инъекцию. Все лимиты именованы (`MAX_FILE_BYTES 10 MB`,
  `MAX_ROWS 5000`, `MAX_ROW_ERRORS 100`, `IMPORT_COMMIT_BATCH 500`, `STAGING_DIR`,
  `TARGET_FIELDS`, `TRANSFER_STATUSES`).
- Scope хороший: `import.write/import.read` + `job_visible_to` own-vs-admin;
  idempotency `sha256(file+mapping+options)`, reuse live `queued/building/ready`;
  partial unique `uq_report_jobs_idempotency WHERE key IS NOT NULL`.
- Транзакции хорошие: per-row `begin_nested`, batch commit 500, `dry_run→rollback`,
  outer rollback on fatal; cap ошибок с `truncated/errors_total` — хвост не молча.
- Оставшееся (MEDIUM): построчные лукапы — N строк × ~8 SELECT (≈40k запросов на
  5000 строк); смягчено savepoint/batch, но bulk-предзагрузка справочников (IN) +
  `bulk_insert_mappings` всё ещё рекомендуются. Роутер буферизует `b"".join(chunks)`
  до ~10.25 MiB в памяти на запрос (ок, но без cap числа параллельных — см. rate-limit).
- Слоистость (LOW): роутер делает `db.execute(select(ReportJob))` в `_get_or_create_job` —
  вынести в ledger/service. `STAGING_DIR=/tmp/...` — артефакты в world-readable tmp
  (детали ошибок туда не текут, но проверить umask). Synthetic email
  `import-<rand>@example.local` и `_slug_code dir-<rand>` и `parse_date` год→Dec 31 —
  известные MEDIUM-костыли из прошлого ревью, живы — решить политикой (nullable email,
  требование code, `expiry_granularity`).

---

## 6. Модели, миграции, сессия, сиды

### Модели (`app/models/`) — хорошо, две аномалии

- `Base` + naming-конвенция (`ix/uq/ck/fk/pk`); `DeferredBase` изолирует stub-модели —
  правильно. `UUIDPKMixin` (client-side `uuid4`, консистентно с SQL без
  `DEFAULT gen_random_uuid()`); `TimestampMixin` (tz-aware, server defaults).
- Статусы — `str,Enum` + plain `VARCHAR` без `CHECK` by design (коммент в `enums.py:3-6`,
  TODO в `000002/000005` «DATA INTEGRITY HARDENING») — валидация только в Python;
  прямая запись в БД может задрейфовать. Осознанный риск, зафиксировать как решение.
- **Аномалия 1 (HIGH, H2-новый)**: `WorkflowInstance.university_id → CASCADE`
  (`workflow_instances.py:60-67`) — удаление вуза сносит всю workflow-историю
  (transitions/comments/attachments/tasks/instance_stages тоже CASCADE), тогда как
  весь P1-каталог (licenses/contracts/students/teachers) — `RESTRICT`. Не
  задокументировано. Плюс ORM `University.relationships cascade="all, delete-orphan"`
  шире DB (через ORM удаление потянет meetings/documents/programs/products, через SQL —
  упрётся в RESTRICT) — два разных поведения удаления. Нужен единый policy-документ +
  тест удаления со всеми связями.
- Аномалия 2 (LOW): `HealthScoreCurrent` без миксинов, PK=`university_id`, FK без имени
  и без `ondelete` в ORM (в SQL `ON DELETE CASCADE`) — на DDL не влияет (SQL источник),
  но `alembic autogenerate` даст ложный diff. `ReportJob.idempotency_key` без unique в
  ORM (уникальность только partial index в SQL) — ORM допустит дубли, ловит только БД.
  `AuditOutbox.status` без CHECK в ORM; `HealthScoreSnapshot` — ок (uq+ix).

### Миграции — отлично с мелочью

- 23 пары up/down (`000001..000023`), missing-down нет; каждый `up` — одна транзакция,
  `INSERT schema_migrations` в той же транзакции, failure → rollback; идемпотентность
  через таблицу версий, не `IF NOT EXISTS` (намеренно).
- `EXPECTED_TABLES` — 32 таблицы, `verify` требует `applied==available` строго по
  порядку + subset таблиц. Stale-коммент «000011-000021» (список уже включает 000022/23) —
  обновить.
- `ON DELETE` сводка: CASCADE — university→meetings/documents/notes/snapshots/current,
  instance→всё, teacher→quals/certs/programs-link, template→stages, M:N; RESTRICT —
  catalog + template→instances + transitions.from/to (после `000014`); SET NULL —
  contract/product/license/program/direction/responsible/stage-якоря. Консистентно с
  моделями, кроме H2-аномалии выше.
- Индексы: 82× `CREATE INDEX` — все FK + `univ_expires/univ_created/teacher_expires/
  instance_created/actor_sub/status/created/expires` + outbox claim-индекс. Хорошо.
- `baseline`: `LEGACY_ALEMBIC_HEAD` + строгая проверка (1 row + 21 legacy-таблица).
  Двойной префикс `ck_documents_ck_...` — quirk сохранён намеренно.

### Сессия — хорошо (исправлено)

- Вчерашний M5 («нет пул-конфига») в дереве закрыт: `pool_size=5 / max_overflow=10 /
  pool_timeout=30 / statement_timeout=30000`, `pool_pre_ping=True`, SQLite —
  драйверные дефолты. Ок.
- Осталось (LOW): `engine = get_engine()` + `SessionLocal` на импорте с дефолтом
  `sqlite:///./dev.db` — импорт без `DATABASE_URL` привязывает процесс к SQLite;
  fail-closed только в entrypoint (`exit 1` без `DATABASE_URL`); `docker run` без него
  стартует на `dev.db` — перенести fail-closed в `config.py`/фабрику engine.

### Сиды — хорошо, мелочь

- Идемпотентный `get_or_create` по натуральным ключам, даты от `date.today()`,
  10 вузов, `TEACHER_PLAN`, `LICENSE_EXPIRY`, студенты bulk, `seed_workflow_templates`;
  `skip_universities` via arg/env; не запускаются на старте (только вручную);
  `seed_performance` аддитивен (`Random(42)`, `PERF-` префикс). Хорошо.
- Мелочь (LOW): `print()` вместо логгера в сидах → logging.

---

## 7. Тесты, CI, Docker, доки

### Тесты — 80 файлов, архитектура без маркеров (MEDIUM)

- 80 `test_*.py`: 9 `*_pg.py`, 8 `*_unit.py`, ~63 смешанных (pure-unit + PG-gated через
  runtime-skip `require_pg_engine`, а не маркеры). `grep pytestmark/mark.pg` — пусто,
  `[tool.pytest]` нет; `Dockerfile CMD ["pytest","tests","-m","not pg"]` — селектор
  ничему не соответствует (все стартуют, PG-gated скипаются внутри). CI гоняет один и
  тот же `pytest tests -q` дважды (без/с `TEST_DATABASE_URL`).
- Изоляция: `reset_test_db` — `DROP SCHEMA public CASCADE + CREATE + migrate up`,
  охрана `assert_dedicated_test_db` (имя обязано содержать `test`) + отказ на не-PG.
  Дорого (каждый PG-тест платит полный up 23 миграций), но изолированно; пин —
  `test_p5_test_isolation_guard.py`. Слабость: `conftest.seeded_db` держит одну сессию
  на тест + `rollback` на teardown — при забытом `commit` возможны протечки; `xdist` нет.
- Слабые моки: `test_p1_mocks` monkeypatch'ит приватные `_derive_license_status` с
  замороженной датой (тест мока, не логики); `test_p5_mocks_coverage/test_p2_12_01_mocks` —
  только `model_validate` JSON-эталонов (валидация JSON, не поведения). Heavy-логика
  (claim/relay) покрыта PG-интеграционными — плюс.
- Рекомендация (MEDIUM): ввести маркеры `pg/unit`, разделить джобы осмысленно
  (`-m "not pg"` заработает), транзакционные savepoints/шаблонную БД для скорости,
  behavior-тесты поверх фикстур вместо валидации эталонов; замер покрытия
  (`pytest-cov`, пороги >80/95% по P1-11-01/P2-11-01).

### Dockerfile/entrypoint/migrate — хорошо с двумя пометками

- Multistage `base/test/runtime`, версии только из `pyproject.toml`; `test`-стейдж ставит
  dev-зависимости, `runtime` — нет. `RUN rm -rf` 14 карантинных файлов + проверка
  `check_legacy_quarantine.py` + `test_p0_deferred_registry`. Риск: удаление на уровне
  файлов — если канон импортирует удалённое, образ упадёт только в рантайме
  (CI runtime-образ не тестируется, только `test`-стейдж) — добавить импорт-дым в CI
  на runtime-стейдже.
- Entrypoint: socket-wait 60с, `baseline` (неудача → warning, continue — верно для fresh
  DB), затем `up` + `verify`, без `DATABASE_URL` → `exit 1` fail-closed.
- Пометка (LOW/MEDIUM): «single backend replica» ничем не enforced — при `replicas>1`
  два `up` конкурентно (спасает одна транзакция на файл + PK на `schema_migrations`,
  но `cmd_up` без `ON CONFLICT` даст `FAILED`+rollback вместо идемпотентного ретрая).
  Добавить advisory lock или документировать single-migrator.

### Compose/workflows/docs — хорошо, мелочь

- Compose: `postgres:16-alpine` (internal expose, `pg_isready`), `redis:7-alpine`,
  `keycloak:26.7.4 start-dev --import-realm`, backend через entrypoint
  (`AUTH_DEV_BYPASS=false`, разделение external/internal issuer/JWKS), worker
  (`python -m app.modules.analytics.report_worker`), frontend same-origin `/api/`.
  Volumes персистентны. Секреты `change-me` — демо-дефолты (не прод).
- Workflows (`backend.yml`): lint (ruff + quarantine), unit, postgres, openapi, smoke.
  Минусы: unit vs postgres дублируют команду; `check_migrations.py`, `migrate.py verify`,
  runtime-образ в CI не гоняются — добавить.
- Docs: `backend/docs/` + корень `docs/` (ARCHITECTURE, SECURITY, ADMIN/USER_GUIDE,
  contracts, mocks) — покрытие есть; карта «какой док — источник» только в шапках
  тестов — добавить индекс. `test_docs_and_redoc_served` требует `cdn.jsdelivr.net` —
  офлайн Swagger UI сломается (зафиксировать как известное ограничение).
- Alembic-каталог архивирован, но `alembic.ini/env.py` жив и импортирует `app.models` —
  ловушка для `alembic revision --autogenerate` (двойной источник схемы). Удалить или
  явно запретить guard'ом.

---

## 8. Полный перечень находок (актуальный)

### HIGH (5)

| ID | Находка | Локация | Рекомендация |
|----|---------|---------|--------------|
| H1 | Аудит тихо no-op без `audit_context`; пишущие места на голом `get_db` (35 шт.) | `catalog/repository.py:58,636,648,670,680`, `meetings/service.py:53,83`, `students/service.py`, `workflow_instances/service.py:212-214`, `workflow_attachments/service.py:107-110`, `audit/service.py:207-208,231` | warning при пропуске + lint-gate «write ⇒ `get_audit_db`»; убрать фабрикацию `context_for` |
| H2 | `WorkflowInstance.university_id → CASCADE` сносит историю; ORM-каскад шире DB | `models/workflow_instances.py:60-67`, `models/catalog.py:52-70` | единый policy-документ (CASCADE vs RESTRICT vs SET NULL) + тест удаления со всеми связями |
| H3 | Rate-limit неатомарен (GET→INCR раздельно) | `core/rate_limit.py:38-46` | `INCR+EXPIRE`/Lua, тест конкурентным burst |
| H4 | Бакет лимита по полному токену + обход trailing slash + unbounded локальный fallback | `core/middleware.py:237,231`, `core/rate_limit.py:13,50-56` | бакет по `sub`, нормализация пути, bounded LRU + TTL-sweep |
| H5 | Legacy `infrastructure/storage.py`: traversal + fail-open в local (если модуль импортируется) | `infrastructure/storage.py:31-45` | grep импортов; санитизировать/удалить, оставить канон |

### MEDIUM (12)

| ID | Находка | Локация |
|----|---------|---------|
| M1 | Scope-проверка после загрузки: teacher-passport, health-router (лишний SELECT + timing-oracle) | `teachers/passport_service.py:126-133`, `health_score/health_router.py:128-133,162-167,205-210` |
| M2 | SQL/бизнес-логика в роутерах: health, ranking, imports `_get_or_create_job`, RBAC-ветвление в instances, author-check в attachments | `health_router.py`, `ranking_router.py:66-83`, `imports/router.py:77-86`, `workflow_instances/router.py:50-55`, `workflow_attachments/router.py:178-182` |
| M3 | Двойная формула Health Score (взвешенная vs штрафная) + legacy int-PK сервис | `health_score/aggregate.py:25-31` vs `health_score/service.py:10-17` vs `passport_blocks.py:691-726` |
| M4 | `list_transitions` без пагинации (unbounded history) | `workflow_transitions/service.py:216-230` |
| M5 | Импорт: N строк × ~8 SELECT построчно (до ~40k запросов на файл) | `imports/service.py:270-277,416-452,471-503,536-546` |
| M6 | Outbox-relay: `failed` недостижим, ретрай без backoff (hot-loop ~2с) | `modules/audit/relay.py:71-75`, `report_worker.py:243-246` |
| M7 | CORS `*` + `allow_credentials` возможен в dev/staging; нет `https`-enforce для issuer в prod | `config.py:87-89`, `main.py:54-61` |
| M8 | Тесты без маркеров (`-m "not pg"` холостой), дорогая изоляция, слабые моки, нет замера покрытия | `tests/`, `Dockerfile:31`, `pyproject.toml` |
| M9 | God-файлы: `passport_blocks` 951, `catalog/router` 747, `imports/service` 691, `dataset` 620, `pdf` 569, `report_jobs` 520, `transitions/service` 374 | см. раздел 5 |
| M10 | Copy-paste: `_ensure_tz*` ×5, `_get_university_or_404` ×2, `get_instance_or_404` ×3, COUNT+page ×15+ | см. раздел 5 |
| M11 | `patch/delete/assign` вуза: scope-check в роутере + unscoped load в сервисе (TOCTOU, 2 запроса) | `catalog/service.py:142,158,539` |
| M12 | Отчёты без idempotency-ключа (импорт — с ключом); `HEALTH`/`mark_building` неатомарности вне критического пути | `analytics/reports_router.py`, `report_jobs.py:268-292` |

### LOW (8)

| ID | Находка | Локация |
|----|---------|---------|
| L1 | JWKS через `urllib` без TLS-контекста; `_dev_user` admin-ALL при bypass | `core/security.py:70-71,183-186` |
| L2 | `require_role` с неявным admin-bypass; мёртвый `PUBLIC_ROLE_NAMES`; двойная семантика `"*"` | `core/permissions.py:11,29,35,69` |
| L3 | `request.state.user_id` никто не ставит (логи `-`); `basicConfig` на импорте | `core/logging.py:13,114` |
| L4 | Тестовые `/auth/test/*` смонтированы в prod; `limit_bytes` в 413-details | `modules/auth/router.py:39-66`, `core/middleware.py:61` |
| L5 | `HealthScoreCurrent` FK без имени/`ondelete` в ORM; `idempotency_key` без unique в ORM; `outbox.status` без CHECK в ORM | `models/health_score.py:109-111`, `models/report_job.py:85-87`, `models/audit_outbox.py:19` |
| L6 | Magic: advisory lock `24110901`, inline `300` в health-router, `print` в сидах, `_too_large` детали | `materialization.py:140`, `health_router.py:176`, `db/seed*.py` |
| L7 | `custom_openapi` пост-обработка хрупка к обновлению FastAPI; Swagger требует CDN (офлайн-демо) | `main.py:73-179` |
| L8 | Дефолт SQLite + engine на импорте; конкурентный `migrate up` при replicas>1; `alembic/`-ловушка; CI не гоняет runtime-образ/verify | `db/session.py:34-35`, `config.py:31`, `scripts/migrate.py`, `Dockerfile` |

---

## 9. Проверено и НЕ является проблемой

- SQLi: bound params везде + `_escape_like`/`like_pattern` (импорт, каталог) — wildcard-инъекция закрыта.
- Auth bypass в compose: `AUTH_DEV_BYPASS=false`, fail-closed валидатор, `_dev_user`
  недостижим в проде.
- Traversal в attachments: `_checked_key` + uuid-ключи + `os.replace` атомарно.
- Traversal в imports (бывший C1): hex32 + containment — исправлено, перепроверено чтением.
- OOM в preview (бывший C2): чанки 256 KiB + mid-stream 413 — исправлено, перепроверено.
- CORS: allowlist без wildcard в проде; методы/заголовки замкнуты (оговорка только
  про dev/staging + `allow_credentials`, M7).
- Миграции транзакционные (`baseline→up→verify`, entrypoint `set -e`); missing-down нет.
- `task_queue` (бывший H7): удалён, вторая очередь отсутствует.
- `core/pagination.py` (бывший M6): удалён.
- Пул БД/таймауты (бывший M5): настроены (`5/10/30s/30s`, `pre_ping`, statement_timeout).
- H2-писатели: теперь с `logger.exception + rollback` (дрейф видим).
- Пагинация канона: `le=100` везде кроме overview (`le=500` — осознанно).
- `apply_university_scope` перед `count()` в audit-read; rank-кэш только при global_scope.
- `create_all` в прод-коде отсутствует (только тестовые/скриптовые места — quarantine guard следит).

---

## 10. Приоритет исправлений

1. **H1 (аудит)**: warning при no-op + lint-gate `get_audit_db` для пишущих роутов; убрать
   фабрикацию контекста. Иначе лента аудита неполна молча.
2. **H2 (каскады)**: policy-документ удаления + миграция/код под единый стандарт +
   тест удаления вуза со всеми связями. Иначе риск потери workflow-истории.
3. **H3–H4 (rate-limit)**: атомарный инкремент, бакет по `sub`, нормализация пути,
   bounded fallback. Иначе лимиты обходятся.
4. **H5 (legacy storage)**: доказать неиспользуемость grep'ом по импортам и удалить;
   иначе traversal + fail-open живы.
5. **M1–M2 (scope/order/слоистость)**: scoped SELECT в teacher-passport и health-router;
   вынести SQL и RBAC-ветвления из роутеров в service/repository; пагинация
   `list_transitions`. Дешёвые правки с высоким эффектом на консистентность.
6. **M3 (две формулы HS)**: оставить один источник (взвешенную), legacy int-PK удалить.
7. **M5–M6 (импорт/relay)**: bulk-предзагрузка справочников; backoff + терминальное
   `failed` в relay.
8. **M7–M8 (config/тесты)**: `*` + credentials запретить везде, `https`-enforce в prod;
   маркеры `pg/unit`, осмысленные CI-джобы, `pytest-cov` с порогами, runtime smoke в CI.
9. **M9–M12, L-серия**: split god-файлов, общие хелперы (`datetime_utils`, scoped loaders,
   COUNT+page), именованные константы, idempotency для отчётов — плановый рефакторинг.

---

## 11. Как проверено (воспроизводимость)

- `git log --oneline -5` → HEAD `9d6077a`; `git status --short` → ~20 изменённых/
  удалённых файлов в дереве (security, middleware, config, session, redis, imports,
  catalog, health cache, relay, Dockerfile и др.); ветка `develop`.
- `ls backend/migrations` → 23 пары up/down (`000001..000023`).
- `ls backend/app/core/` → errors, exceptions, logging, middleware, permissions,
  policies, rate_limit, security (без pagination); `infrastructure/` → http_client,
  redis, storage (без task_queue).
- `grep _FILE_ID_RE / _staged_path` → hex32 + containment (C1 закрыт);
  `imports/router.py:137-147` → чанки + mid-stream 413 (C2 закрыт).
- `grep "except Exception"` → все с обработкой (`logger.exception/warning`, rollback,
  ветвления); bare `pass` только `storage.py:198` (идемпотентный delete — ок);
  тихие `return False` — `health_score/snapshots.py:33,52` (зафиксировано).
- `grep -c "Depends(get_db)"` → 35 (масштаб H1).
- `grep "SKIP LOCKED|claim_next_job|claim_job"` → `report_jobs.py:337,378-425`
  (атомарный claim, stale-recovery).
- `ls backend/tests/test_*.py | wc -l` → 80; `grep pytestmark/mark.pg` → пусто
  (маркеров нет — M8).
- Три subagent-аудита (core/auth, домены, БД/инфра/тесты) + сверка с
  `BACKEND_REVIEW.md` и `REVIEW_REPORT_P1_P2_P4.md`.

---

*Конец ревью. Следующий шаг — разнести H1–H5 и M1–M8 в задачи; L-серию — в бэклог
рефакторинга. Перед релизом прогнать на живом стенде: PG-сьют (`TEST_DATABASE_URL`),
`verify-docker.sh`, smoke с реальным Keycloak, Locust-прогоны (p50/p95) — NEEDS VERIFICATION.*

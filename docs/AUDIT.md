# Аудит проекта CRM (ИТ Школа РТК)

> Дата: 2026-09-18. Срез `develop`. Проект в разработке — оценивается то, что есть, с учетом развития.
> Стенд: `Browser → React → Keycloak → FastAPI (JWT+RBAC)`, P1-схема БД, XLSX-импорт.

## Что реально работает

* Auth-стенд: `frontend/src/auth/keycloak.ts`, `AuthProvider.tsx`, `backend/app/core/security.py` (RS256 по JWKS, проверка `iss/exp/aud`, fail-closed), `backend/app/modules/auth/router.py` (`/auth/me`, `/test/*`).
* P1-схема: `backend/app/models/` — 20 таблиц (universities, it_directions, it_programs, vendors, it_products, contracts, licenses, responsibles, university_responsibles, teachers, teacher_qualifications, teacher_certificates, teacher_programs, students, university_programs, university_products, meetings, meeting_documents, documents, interaction_notes). UUID PK, `timestamptz`, вычисляемые `@property` статусов. Миграции `alembic/versions/`: `...01_p1_catalog → ...02_p1_teachers → ...03_p1_interactions`, один head.
* Импорт: `backend/app/modules/imports/{router,service,schemas}.py` — `stage_upload/parse_preview/execute_import`, лимиты 10МБ/5000 строк, построчные ошибки, idempotency по natural keys.
* Инфра: `docker-compose.yml` — `postgres:16-alpine` (5433→5432), `keycloak:26.7.4` (8081→8080, `--import-realm`), `backend:8000`, `frontend:3000→80`.

## P0 — блокирует развитие

### 1. Две вселенные схем (backend)
* Канон: `app/models/* + app/schemas/*` (UUID, P1-контракт).
* Legacy: `app/modules/*/models.py + schemas.py` (`Integer` PK, выдуманные поля).
* Конкретно:
  * `app/modules/universities/repository.py:28,31`, `schemas.py:4-15`, `router.py:41-46` — `University.region/status/address/responsible_person_id`. У `app/models/catalog.py:40 University` есть только `name/city`. Вызов = `AttributeError/TypeError`.
  * `app/modules/dashboard/router.py:19-27`, `app/modules/reporting/router.py:25-28` — `University.region/city/status`, `Program.status/university_id`. Полей нет в `ITProgram/University`.
  * `app/modules/workflow/models.py`, `documents/models.py (FileMeta→files)`, `audit/models.py (AuditEvent)`, `health_score/models.py`, `identity/models.py (User)` — все `Integer` + `FK("universities.id")`. На Postgres несовместимо с UUID; `alembic upgrade head` создает только P1-таблицы → legacy упадет `no such table`.
  * `app/modules/documents/router.py` пишет в `files`, а паспорт читает `app/models/interactions.py:175 documents` — два файловых реестра.
  * `app/modules/teachers/schemas.py:6-13`, `router.py:13,24`, `app/modules/programs/schemas.py:6-13` — `university_id: int`, `competencies`, `direction_id: str` — не соответствуют моделям (UUID).
* `app/api/router.py` монтирует только `auth + imports`. Остальные 12 модулей — мертвый код, выглядящий готовым.
* Риск: новый разработчик возьмет не тот импорт; включение роутера без переписывания = 500-е.

### 2. Фронт недеплоябелен вне localhost
* `docker-compose.yml:76-80` + `frontend/Dockerfile:11-15` — `VITE_KEYCLOAK_URL/VITE_API_URL` запечены в `ARG` на build. Рантайм-перенастройка невозможна.
* `docker-compose.yml:63` — `KEYCLOAK_ISSUER: http://localhost:8081/...` (для браузера) vs `KEYCLOAK_JWKS_URL: http://keycloak:8080/...` (для сети compose). Расхождение `iss` — источник `invalid issuer` вне localhost.
* `keycloak/realm-export.json` — `redirectUris: ["http://localhost:3000/*"]`, `webOrigins: ["http://localhost:3000"]`. Каждый стенд требует правки JSON.
* Итог: демо на `localhost:3000` пройдет, стенд жюри по IP/hostname — нет.

### 3. Dockerfile дрейфует от pyproject
* `backend/Dockerfile:4` ставит списком без `redis/minio/reportlab/python-dateutil`, а `backend/pyproject.toml:10-24` их требует.
* `app/infrastructure/storage.py:14 import minio` уходит в `except` → тихий локальный fallback вместо S3; `reportlab` для PDF отсутствует вовсе.
* Нет non-root user, `COPY pyproject.toml + pip install` вручную вместо `pip install -e .`.

### 4. RBAC и типы user-id отсутствуют
* `app/core/permissions.py` (матрица `admin/manager/curator/user`) существует, но ни один доменный роутер его не использует — только `Depends(get_current_user)`.
* `core/security.py:33 CurrentUser.id: str (sub)`, но `audit/models.py:16 user_id: int`, `documents/models.py:20 uploaded_by: int`, `audit/service.py:12 log(user_id: int)`. На PG — ошибка типа.

### 5. Контракт ошибок и пагинация не соблюдаются
* `app/main.py` — нет глобальных `exception_handler`. `schemas/common.py:175 ErrorResponse{code,message,request_id}` определен, но роутеры кидают `HTTPException(404, "строка")` (`teachers/router.py:36`, `reporting/router.py:48`, `imports/router.py:35 → 400`).
* `core/pagination.py:paginate()` + `schemas/common.py:157 PaginatedResponse` не используются. Вместо них `query.limit(200).all()` + фильтр в Python (`documents/router.py:28-35`, `audit/router.py:29-34`).

### 6. Импорт блокирует HTTP + in-memory очередь
* `imports/router.py:66-73` — `enqueue → execute_import(синхронно) → job_done` в пределах запроса. Большой XLSX заблокирует воркер uvicorn.
* `infrastructure/task_queue.py:4 _local_jobs` — dict в памяти, теряется при рестарте; Redis-ветка пишет, но `job_status/job_done` читают только локально. `workers/reports.py: run_imports_once/run_integrations_once → return 0`.

## P1 — надежность / инфра / фронт

* Архитектура фронта: `frontend/src/App.tsx:9-87` — вся CRM в одном компоненте, нет `react-router`, store, форм, тестов. `api/client.ts:8` — только `apiFetch<T>(path)`, без `method/body/signal`; `:19` шлет `Bearer undefined` без токена; `:28 await resp.json()` без `try/catch` (204/HTML уронит дерево); `:10-15 updateToken fail → login()` — риск redirect-loop. `App.tsx:15-23` глотает ошибку `/me`, нет `loading/error`; `:79 key={i}`, массив `checks` растет без лимита; нет `ErrorBoundary` (`main.tsx`).
* Auth: `AuthProvider.tsx:25-43 init().catch(()=>setReady(true))` — ошибка Keycloak превращается в экран «Войти» без диагностики; нет `onTokenExpired`/silent-refresh, нет разбора `?error=`. `keycloak.ts:6-10 realm/clientId` захардкожены. `UserCard.tsx:21,27 me.roles.map` без `?? []`, только `as Me` без `zod`.
* Docker: `keycloak: start-dev --import-realm (docker-compose.yml:27)` — dev-режим, для прод нужен `start --optimized`. `frontend/.dockerignor` — опечатка, должен быть `.dockerignore` → в контекст летят `node_modules/dist`. `frontend/Dockerfile:20 FROM nginx:alpine` без пина. `frontend/nginx.conf:1-15` — нет `gzip/expires/security-headers//api-прокси` → фронт ходит в бэк напрямую, CORS load-bearing. `nginx/nginx.conf` — gateway с `upstream backend/frontend` не подключен к compose, нет `X-Forwarded-*`, `rate-limit/TLS`. У `frontend` нет `healthcheck`; Keycloak healthcheck — хрупкий `bash /dev/tcp + grep " 200 "` (старт до ~6 мин). Все порты наружу (`5433/8081/8000/3000`), нет `restart/networks/logging`. `vite.config.ts` — нет `server.proxy /api`.
* Конфиг/БД: `app/config.py:10 extra="ignore" + entrypoint.sh:7` — без `DATABASE_URL` миграции скипаются («SQLite dev mode»), сервер стартует с расходящейся схемой (fail-open). `app/db/session.py:7-8` — engine на импорте, нельзя держать два DSN; тесты мутят глобальный `settings` (`test_auth.py`) — хрупко к порядку. `infrastructure/keycloak.py` — мертвый дубликат JWT-проверки (реальная в `core/security.py` на `urllib+jose`); `python-jose` deprecated. Дубли `EXPIRY_WARNING_DAYS` (`models/enums.py:89` vs `schemas/common.py:25`); `UserRole` без `curator` vs `KNOWN_ROLES` с ним. `tests/api/test_mvp.py:8` — скипнут целиком. `.gitignore` — нет `.venv/.pytest_cache/*.xlsx` (а `.pytest_cache/` уже закоммичен). `tsconfig.json` — нет `noUnusedLocals`, нет eslint/prettier. `index.css` — один глобальный файл, `max-width:720px`, нет брейкпоинтов/`:focus-visible`/`aria`.

## P2 — безопасность / 152-ФЗ + ФСТЭК-117

Кейс требует прямо. Сейчас:
* Нет согласия на обработку ПДн, политики/оферты, маскирования email/ФИО по ролям, ЛК субъекта (скачать/удалить), idle-локаута SPA (только Keycloak 30 мин), аудит-видимости для пользователя.
* Токены в памяти — плюс, но `change-me` везде (`.env.example`, `compose :-change-me`), нет CI-guard от дефолтных секретов, секреты видны в `docker inspect`.
* `FRONTEND_ORIGIN` — один origin (`backend/app/main.py:39-40`); второй origin (gateway/preview) даст CORS-ошибку. Лечится same-origin прокси, а не `*`.
* `pgdata` — анонимный volume без бэкапа/шифрования/гео (РФ) описания. `docs/DEPENDENCIES.md` — ручной SBOM; `docs/mocks/*.json` без пометки «синтетика».

## Рекомендации по приоритету

**P0 — до демо на чужом хосте:**
1. `frontend/src/config.ts` (`/config.json` + `envsubst` в `entrypoint.sh`), убрать build-`ARG`; `KEYCLOAK_ISSUER=${...}` без литерала; `realm-export.json` параметризовать (`${FRONTEND_ORIGIN}/*`).
2. Same-origin: прокси `/api/` в `frontend/nginx.conf` (`proxy_pass http://backend:8000`) или сервис `gateway` из `nginx/nginx.conf` + относительный `/api`; dev — `vite server.proxy /api → :8000`.
3. Экран ошибки Keycloak в `AuthProvider` + ретрай, `onTokenExpired → updateToken(60)`.

**P0 — до включения домена:**
4. Удалить legacy `modules/*/models.py + schemas.py`, переписать `router+service+repository` на `app.models + app.schemas` (UUID); `files → documents`, `audit user/entity → String/UUID`, `health_score_history → UUID FK`, `users → responsibles.keycloak_sub`.
5. `Dockerfile → pip install -e . + USER appuser`; `session.py → get_engine(url)` + `dependency_overrides[get_db]`; `entrypoint.sh` — падать при несхождении миграций.
6. Везде `require_permission/require_role`, `keycloak_sub: str`; хендлеры `ValidationError/HTTPException → ErrorResponse + request_id`; заменить `.limit(200)` на `PaginatedResponse`; вынести `execute_import` в воркер с Redis-статусом; удалить `infrastructure/keycloak.py` или сделать единственным источником (замена `python-jose → pyjwt`).

**P2 — гигиена/баллы:**
7. Один `EXPIRY_WARNING_DAYS`, `curator` в `UserRole`; раскиповать `test_mvp.py` после переписывания; `.gitignore + .dockerignore` починить, удалить `.pytest_cache`; пин `nginx:1.27-alpine`, `gzip/headers/HEALTHCHECK`.
8. 152-ФЗ: чекбокс согласия + политика, «Мои данные: скачать/удалить», маскирование `a***@`, idle-локаут 15 мин, закрыть PG/Keycloak (`expose`), `restart/networks`, `grep change-me` CI-guard, бэкап `pgdata`, `syft` SBOM, `SYNTHETIC-DATA.md`.

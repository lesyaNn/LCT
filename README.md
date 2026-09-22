# Кейс 16 · CRM взаимодействия с учебными заведениями (ИТ Школа РТК)

> Хакатон «Лидеры цифровой трансформации» (ЛЦТ) 2026 — конкурс Мэра Москвы для лучших ИТ-специалистов мира.

&nbsp;
## 📋 Общая информация

| Параметр | Значение |
|---|---|
| **Номинация** | Наука |
| **Заказчик** | ИТ Школа РТК, ООО «Ростелеком Информационные Технологии» |
| **Ссылка на задачу** | [i.moscow/hackaton/lct/179b401bb27649418735ecafbd037e1b](https://i.moscow/hackaton/lct/179b401bb27649418735ecafbd037e1b) |
| **Формат продукта** | Программный продукт (CRM-система) |

&nbsp;
## 🏆 Призовой фонд

| Место | Сумма |
|---|---|
| 🥇 1 место | 1 000 000 ₽ |
| 🥈 2 место | 600 000 ₽ |
| 🥉 3 место | 400 000 ₽ |

&nbsp;
## 🎯 Актуальность

В соответствии с реализацией поручений Правительства РФ по развитию кадрового потенциала в сфере информационных технологий, а также во исполнение задач федеральных проектов, ведётся работа по формированию системы контроля за подготовкой квалифицированных ИТ-специалистов среди студентов вузов и обучающихся школ.

Для объективного ранжирования образовательных программ по ИТ-направлениям необходимо создать систему по контролю за подготовкой кадрового резерва. Ранжирование происходит на основе востребованности программы, которая становится очевидной по статистическим данным: заявки на обучение, количество обучающихся, количество параллельных потоков.

CRM позволит контролировать взаимодействие с учебными заведениями для приобретения навыков работы с востребованными на рынке цифровыми инструментами. На их основе обучающиеся смогут получить актуальные компетенции по различным ИТ-направлениям. Решение автоматизирует процесс взаимодействия с каждым вузом по разным образовательным программам, что позволит учебным заведениям получать конечный результат быстрее.

&nbsp;
## 🧩 Описание задачи

Разработать систему контроля взаимодействия с учебными заведениями, которая позволит:

- **визуализировать цикл взаимодействия** с каждым вузом;
- **контролировать путь жизненного цикла** каждого взаимодействия с вузом по всем ИТ-программам и ИТ-продуктам.

Задача сервиса — сокращение трудозатрат сотрудников ИТ Школы РТК на взаимодействие с вузами за счёт автоматизации всего пути взаимодействия.

### Текущий workflow взаимодействия с вузом (14 шагов)

1. Поиск контактов ответственного в вузе;
2. Коммуникация с ним и уточнение актуальности программ по ИТ-направлениям;
3. Организация встречи с представителями вуза;
4. Обмен необходимым пакетом документов для подписания;
5. Опционально: скорректировать документы перед подписанием;
6. Подписание документов;
7. Передача обучающих материалов по ИТ-направлению, лицензии ИТ-продукта и его документации в вуз;
8. Сопровождение внедрения ИТ-продуктов в вузе;
9. Обучение преподавателей;
10. Актуализация учебной программы по ИТ-направлению с учётом обучения преподавателя и добавления ИТ-продукта;
11. Ведение занятий;
12. Актуализация документации по продукту и обучающим материалам;
13. Повышение квалификации преподавателей;
14. Контроль за исполнением каждого этапа.

### Требования к системе

- Автоматизация процесса взаимодействия с вузом;
- Интеграция по API со сторонними системами заказчика (LMS и сайт);
- Соответствие требованиям безопасности **152-ФЗ «О персональных данных»** и приказу **ФСТЭК № 117**.

&nbsp;
## 📦 Ресурсы

- Массив статистических данных.

&nbsp;
## 🚀 Описание итогового продукта

Программный продукт (система) — CRM контроля взаимодействия с учебными заведениями.

&nbsp;
## 👥 Рекомендуемые роли в команде

- Менеджер проекта
- Специалисты по работе с данными
- Бэкенд-разработчик
- Фронтенд-разработчик
- Разработчик полного цикла

&nbsp;
&nbsp;
## 💬 Контакты и поддержка

- Телеграм: [@help_lct](https://t.me/help_lct)
- Почта: info.leaders@develop.mos.ru
- Модератор задачи: **Малярчук Ярослава** — [@yarochkamal](https://t.me/yarochkamal)

&nbsp;
## 🗓️ Ключевые этапы конкурса

| Этап | Сроки | Формат |
|---|---|---|
| Приём заявок | до 14 сентября | онлайн |
| Разработка решений | 15–29 сентября | онлайн |
| Техническая экспертиза | 30 сентября – 14 октября | онлайн |
| Презентация проектов | 23 октября | онлайн |
| Церемония награждения | 30 октября | офлайн в Москве |

&nbsp;
## 🚀 Quick Start — Minimal Auth Stack

Этап 1: рабочий стенд авторизации `Browser → React → Keycloak → FastAPI (JWT + RBAC)`.
Запуск одной командой:

```bash
cp .env.example .env
docker compose up --build
```

После запуска:

| Сервис   | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3000        |
| Backend  | http://localhost:8000        |
| Swagger  | http://localhost:8000/docs   |
| Keycloak | http://localhost:8081        |

Сценарий: открыть Frontend → **Войти** → логин на странице Keycloak →
возврат в React → профиль + роль + кнопки **Проверить Backend** / **Проверить Admin доступ**.

### 👥 Demo-пользователи (DEMO ONLY, не для production)

| Username  | Email                 | Пароль     | Роль    |
|-----------|-----------------------|------------|---------|
| `admin`   | admin@example.local   | `admin123` | admin   |
| `manager` | manager@example.local | `manager123` | manager |
| `curator` | curator@example.local | `curator123` | curator |
| `user`    | user@example.local    | `user123`  | user    |

Realm `rtk` импортируется автоматически из `keycloak/realm-export.json`
при первом старте (`start-dev --import-realm`). Access token содержит `aud=rtk-api`
через client scope `rtk-api-audience`; Backend проверяет signature/exp/iss/aud
по JWKS (`AUTH_DEV_BYPASS=false` в compose — fail closed).

### ♻️ Полный пересброс dev-Keycloak

Импорт выполняется только на пустых данных. Для пересоздания с нуля:

```bash
docker compose down
docker compose up --build keycloak   # ждём healthy, затем остальное
docker compose up --build
```

### 🧪 Backend-тесты (без реального Keycloak, JWKS мокируется)

```bash
cd backend
PYTHONPATH=. python -m pytest tests/ -q   # pure-unit; DB-интеграция скипается без PG
# Полная интеграция (схема только из SQL-миграций):
TEST_DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk_p1_test \
  PYTHONPATH=. python -m pytest tests/ -q
```

### 🗄️ P1 — ядро схемы БД (PostgreSQL + SQL migrations + seed)

SQL-файлы `backend/migrations/` — **единственный источник истины схемы**
(8 версий: `000001_core_catalog` … `000008_readiness_perf_indexes`).
Python ORM (`backend/app/models/` + `audit_events`) — только runtime-описание,
схемой не управляет (`create_all`/`drop_all`/Alembic DDL удалены из активных
путей; история Alembic лежит в `backend/alembic/` как read-only архив).
21 таблица: universities, it_directions, it_programs, vendors, it_products,
contracts, licenses, responsibles, university_responsibles, teachers,
teacher_qualifications, teacher_certificates, teacher_programs, students,
university_programs, university_products, meetings, meeting_documents,
documents, interaction_notes, audit_events. Все PK — UUID (генерирует
приложение, без `gen_random_uuid()`), все даты — `timestamptz`,
статусы лицензий/договоров/готовности — вычисляемые `@property`.

```bash
# 1. Поднять инфраструктуру (postgres healthy -> backend сам применит миграции)
cp .env.example .env
docker compose up -d --build

# 2. Локально (без compose): создать БД и применить миграции
cd backend
DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk \
  python scripts/migrate.py up

# 3. Проверить версию (latest: 000008_readiness_perf_indexes)
DATABASE_URL=... python scripts/migrate.py status
DATABASE_URL=... python scripts/migrate.py verify

# 4. Загрузить демо-данные (идемпотентно, повтор безопасен; только ПОСЛЕ migrate)
DATABASE_URL=... python -m app.db.seed
# или:  DATABASE_URL=... python scripts/seed_demo.py
# perf-нагрузка (тоже только после migrate, таблицы не создаёт):
#   DATABASE_URL=... python scripts/seed_performance.py

# 5. Инспекция схемы (таблицы, FK, индексы, timestamptz, версия миграций)
DATABASE_URL=... python scripts/db_inspect.py

# 6. EXPLAIN по ключевым запросам (паспорт, преподаватели, лицензии, встречи)
DATABASE_URL=... python scripts/check_explain.py

# 7. Тесты: без PG — только pure-unit (DB-тесты скипаются, никакого SQLite DDL);
#    полная интеграция — через TEST_DATABASE_URL (схема только из SQL-миграций)
python -m pytest tests/ -q
TEST_DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk_p1_test \
  python -m pytest tests/ -q
TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:55433/rtk_p1_test \
  python -m pytest tests/test_p1_schema.py -q
```

Откат и пересоздание схемы с нуля:

```bash
cd backend
DATABASE_URL=... python scripts/migrate.py down --to base --yes  # чистит схему P1 полностью
DATABASE_URL=... python scripts/migrate.py up                     # создаёт заново без ошибок
# Частичный откат: DATABASE_URL=... python scripts/migrate.py down --to 000007_passport_perf_indexes --yes
```

Переход существующей БД со старого Alembic-head (`7f3a1c9e2b06`):

```bash
cd backend
DATABASE_URL=... python scripts/migrate.py baseline  # строгая проверка + mark applied, данные целы
DATABASE_URL=... python scripts/migrate.py verify
```

Проверка seed: повторный `python -m app.db.seed` печатает те же счётчики
(10 вузов, 34 преподавателя, 750 студентов, …) — дубликатов нет.

Проверка эквивалентности старой и новой схемы (каталог + pg_dump):

```bash
cd backend
python scripts/check_migrations.py \
  --source postgresql://rtk:change-me@localhost:5433/rtk_schema_source \
  --target postgresql://rtk:change-me@localhost:5433/rtk_schema_target
# -> SCHEMA EQUIVALENCE: PASS (21 tables, 173 columns)
```

### 🗄️ PostgreSQL: две базы — `rtk` (приложение) и `keycloak` (авторизация)

Один PostgreSQL service, две изолированные databases:

```text
PostgreSQL
├── rtk      — application database, managed by SQL migrations (scripts/migrate.py)
│   ├── universities, teachers, students, licenses, contracts, ...
│   └── schema_migrations (+ legacy alembic_version row on adopted DBs)
└── keycloak — authentication database, managed by Keycloak (Liquibase)
    ├── KEYCLOAK INTERNAL TABLES (realm, client, user_entity, ...)
    └── realm `rtk` + client `rtk-frontend` (import из keycloak/realm-export.json)
```

* Backend работает только с `rtk` (`DATABASE_URL=...@postgres:5432/rtk`), к таблицам
  Keycloak не обращается — только JWT/OIDC по JWKS.
* Keycloak работает только с `keycloak` (`KC_DB=postgres`,
  `KC_DB_URL=jdbc:postgresql://postgres:5432/keycloak`). SQL-миграции таблиц Keycloak
  не создают; Keycloak не трогает таблицы `rtk`.
* Bootstrap обеих БД на чистом pgdata: `docker/postgres/init-databases.sh`
  (монтируется в `/docker-entrypoint-initdb.d/` сервиса `postgres`).
  Переменные: `KEYCLOAK_DB` / `KEYCLOAK_DB_USER` / `KEYCLOAK_DB_PASSWORD`
  (см. `.env.example`). Для уже существующего volume скрипт не выполняется
  (особенность postgres image) — одноразово выполнить SQL из README ниже.
* `start-dev --import-realm` сохранён; повторный импорт безопасен
  (стратегия `IGNORE_EXISTING`: «Realm already exists. Import skipped»).

```bash
# Проверка изоляции
docker compose exec postgres psql -U rtk -d rtk -c "\l"            # есть rtk и keycloak
docker compose exec postgres psql -U rtk -d rtk -c "\dt"           # только P1 + schema_migrations
docker compose exec postgres psql -U rtk -d keycloak -t \
  -c "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN ('universities','teachers','students','licenses','schema_migrations','alembic_version');"
# -> 0 (P1-таблиц в keycloak нет)

# Одноразовый bootstrap keycloak-БД на СУЩЕСТВУЮЩЕМ volume (на fresh pgdata не нужен):
docker compose exec postgres psql -U rtk -d rtk -v ON_ERROR_STOP=1 <<'EOSQL'
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak') THEN
CREATE ROLE keycloak WITH LOGIN PASSWORD 'change-me';
ELSE ALTER ROLE keycloak WITH LOGIN PASSWORD 'change-me'; END IF; END $$;
SELECT 'CREATE DATABASE "keycloak" OWNER "keycloak"'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak')\gexec
GRANT ALL PRIVILEGES ON DATABASE "keycloak" TO "keycloak";
EOSQL
```

### 🖥️ Frontend P3-01-01

Ветка `feature/p3-01-01` содержит единый frontend на **Next.js App Router + React + TypeScript**.
App Shell (Sidebar, Topbar, Breadcrumbs, User Menu и адаптивная навигация) находится в
`frontend/widgets/` и использует локальные CSS Modules с семантическими токенами Rostelecom
Design System Gen2. В этой задаче авторизация остаётся mock-реализацией; существующий backend,
Keycloak и инфраструктура репозитория сохранены без переписывания.

Локальный запуск frontend:

```bash
cd frontend
npm install
npm run dev
```

Проверки frontend: `npm run lint`, `npm run typecheck`, `npm run build`.
Официальные UI-источники: [Design System Gen2](https://design.rt.ru/gen2/designsystem/gettingStarted/intro)
и [React Storybook](https://design.rt.ru/gen2/react-storybook/?path=/docs/welcome-introduction--docs&globals=cssVariables:Rostelecom+Light+Theme).

### ⏭️ Следующий этап

STOP. Далее — проектирование и реализация PostgreSQL-схемы предметной области
(universities/teachers/programs/workflow/…). Доменные модули лежат в
`backend/app/modules/` и в auth-стенде не монтируются.

# Методы обработки данных

Как данные проходят через систему: от миграций и seed до API, фоновых заданий,
интеграций и аудита.

## 1. Схема и миграции

Единственный источник схемы — SQL-миграции в `backend/migrations/`
(`000001_*.up.sql` …). При старте backend `entrypoint.sh` выполняет
`scripts/migrate.py baseline` (подхват legacy-БД) → `up` → `verify`.
Проверка вручную:

```bash
docker compose exec backend python scripts/migrate.py status
docker compose exec backend python scripts/migrate.py verify
```

## 2. Демонстрационные данные (seed)

Канонический seed — `python -m app.scripts.seed_demo` (только с
`SEED_DEMO_DATA=true`), идемпотентен: поиск по естественным ключам
(`name`, `email`, номера договоров/лицензий), повторный запуск ничего не
дублирует и не перезаписывает. Относительные даты (`today ± N дней`)
вычисляются только при первом создании. Перемещения Workflow идут через
канонический сервис `transition_instance`, а не прямой записью
`current_stage_id`. Детали и состав — в [DEMO_SEED.md](DEMO_SEED.md).

## 3. API: валидация, доступ, чтение

- Валидация входных DTO — Pydantic (backend) и Zod (frontend); ошибки — единый
  `ErrorResponse`, 422 при невалидных данных.
- Авторизация: Keycloak JWT (issuer/JWKS/audience), RBAC `user/manager/admin`
  плюс university data scope — чужие вузы отрезаются на уровне запросов.
- Списки — пагинация `page` (1-based) + `page_size`; аналитика и отчёты
  используют единый `UnifiedFilter` (`date_from/date_to`, `university_ids`,
  `direction_ids`, `program_ids`, `product_ids`, `responsible_ids`,
  `workflow_statuses`).
- Health Score считается батчами не более 50 вузов за запрос.

## 4. Импорт из Excel

Двухфазный: upload → staging → preview → execute.

1. Файл (`pdf,png,jpg,jpeg,doc,docx,xls,xlsx,zip,gz,gzip,rar`, лимит
   `MAX_UPLOAD_MB=50`) складывается в staging-каталог (`IMPORT_STAGING_DIR`,
   том `import-staging`, переживает рестарты backend).
2. `preview_sheet` показывает заголовки и первые строки без записи в БД.
3. Execute выполняет worker (см. ниже); структуры листов фиксированы.

## 5. Отчёты и фоновые задания

В API нет BackgroundTasks. Долгие операции (отчёты XLSX/PDF/JSON, исполнение
импорта) — это задания в очереди PostgreSQL: `POST /reports` возвращает 202,
worker (`app.modules.analytics.report_worker`, отдельный контейнер) забирает
задание атомарным claim (`SELECT ... FOR UPDATE SKIP LOCKED`), исполняет и
переводит в `ready`; при исчерпании попыток (максимум 3) — в `failed`.
Готовый файл забирается через `GET /reports/{job}/download`, хранится в томе
`reports-storage`. Статус опрашивается через `GET /reports/{job}`.

## 6. Внешние данные (LMS и сайт)

По умолчанию `EXTERNAL_ADAPTER_MODE=disabled`: стенд работает без внешних
систем, external endpoints отвечают 503 (`EXTERNAL_SOURCE_UNAVAILABLE`), данные
моками не подменяются. При настроенном адаптере приём идёт через ingest
(`POST /api/v1/integrations/lms/ingest`, `.../website/ingest`): снимки LMS
заменяют счётчики той же программы/источника, заявки сайта дедуплицируются по
`(source, external_id)`, батч ограничен 1000 элементами, запись — одна
транзакция. Провайдер ходит во внешний API с таймаутом (по умолчанию 10 с).
Полный контракт — в [EXTERNAL_EDUCATION_CONTRACTS.md](EXTERNAL_EDUCATION_CONTRACTS.md).
Заявки из XLSX (`catalog_type=applications`) доступны как `mode=import` и могут
создавать Workflow без live-адаптера; создание идемпотентно.

## 7. Аудит

CRUD, Workflow, отчёты, импорт и admin-действия пишутся в транзакционный
append-only журнал через `AuditService` (публичных update/delete маршрутов нет).
Seed своих событий не создаёт (сессия без `audit_context`; переходы Workflow
кладут по одной строке в outbox только при фактическом перемещении).
Workflow-переходы seed и outbox relay выполняются каноническими сервисами со
своими транзакциями после коммита ORM-части. Ограничения журнала — в
[SECURITY_ALIGNMENT.md](SECURITY_ALIGNMENT.md) (нет LOGIN/LOGOUT событий,
нет криптографической неизменяемости).

## 8. Файлы и кэш

- Вложения Workflow и импорты: `STORAGE_BACKEND=local|s3|minio` (по умолчанию
  local, тома `workflow-storage`, `import-staging`), проверка расширений и
  containment путей, метаданные (имя, размер, MIME, автор) — в БД.
- KeyDB (Redis-совместимый): кэш и лёгкие очереди; персистентное состояние —
  только в PostgreSQL.

# Установка

## Требования

- Docker + Docker Compose v2, 4 ГБ RAM, ~10 ГБ диска.
- Порты наружу: `3000` (CRM), `8000` (backend API), `8081` (Keycloak).
  PostgreSQL и KeyDB наружу не публикуются (internal only) — доступ через
  `docker compose exec`.

## Запуск (сборка и установка)

```bash
cp .env.example .env
docker compose up -d --build
./scripts/wait-healthy.sh
```

`up --build` собирает образы backend (Python 3.12, FastAPI) и frontend
(Next.js, production build) и стартует весь стек: `postgres`, `keydb`,
`keycloak`, `backend`, `worker`, `frontend`. При старте backend автоматически
применяет SQL-миграции (`scripts/migrate.py up` + `verify`).

Проверка:

```bash
docker compose ps
curl -sf http://localhost:8000/health
curl -sf http://localhost:8081/realms/rtk
```

## Демо-данные

Только после healthy-старта, идемпотентно (повторный запуск безопасен):

```bash
docker compose exec -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo
```

Полный маршрут Workflow на 14 этапов (опционально):

```bash
docker compose exec backend python scripts/create_workflow_template.py
```

Всё сразу одной командой (локальное демо без внешнего интернета):

```bash
./scripts/demo-setup.sh
```

Состав seed — в [DEMO_SEED.md](DEMO_SEED.md).

## Обновление

```bash
docker compose pull
docker compose up -d --build
```

## Бэкап

- Тома: `pgdata` (БД), `keydbdata` (кэш), `workflow-storage` (файлы),
  `reports-storage` (отчёты), `import-staging` (staging импорта).
- БД: `docker compose exec postgres pg_dump -U rtk -d rtk > backup.sql`.

## Секреты

Значения `change-me` в `.env.example` — **только для локального
хакатон-стенда**. Для любого общего стенда сгенерируйте по 32+ символов
энтропии на секрет:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Замените `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD`,
`KEYCLOAK_ADMIN_PASSWORD` (и при наличии — `S3_*` ключи) в `.env`;
`.env` не коммитится (`.gitignore`).

## Troubleshooting

- Keycloak не healthy: ждите 60–90 с (первый старт + импорт realm).
- Повторный импорт realm пропускается (`Realm already exists. Import skipped`);
  для полного сброса Keycloak нужен чистый volume (`docker compose down -v`).
- Backend ждёт `postgres` + `keydb` + `keycloak` (depends_on healthy).
- Миграции: `docker compose exec backend python scripts/migrate.py status`.
- `docker compose down` сохраняет данные; `docker compose down -v` удаляет
  базы, файлы и отчёты без восстановления.

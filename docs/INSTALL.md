# Установка

## Требования
- Docker + Docker Compose v2, 4GB RAM, 10GB диска.
- Порты: `3000` (frontend), `8000` (backend), `8081` (Keycloak).
  PostgreSQL/Redis наружу не публикуются (internal only).

## Запуск
```bash
cp .env.example .env
docker compose up -d --build
./scripts/wait-healthy.sh
```

Проверка:
```bash
curl -sf http://localhost:8000/health
curl -sf http://localhost:3000/health
curl -sf http://localhost:8081/realms/rtk
```

Демо-данные (идемпотентно, после миграций):
```bash
docker compose exec -T backend python -m app.db.seed
```
Или всё сразу: `./scripts/demo-setup.sh`.

## Обновление
```bash
docker compose pull
docker compose up -d --build
```

## Бэкап
- Volumes: `pgdata` (БД), `redisdata`, `workflow-storage`, `reports-storage`,
  `import-staging`.
- БД: `docker compose exec postgres pg_dump -U rtk -d rtk > backup.sql`.

## Секреты

Значения `change-me` в `.env.example` / `docker-compose.yml` (`:-change-me`) —
**только для локального хакатон-стенда**. Для любого общего/прод-стенда:

```bash
# 32+ символов энтропии на каждый секрет:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Замените `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD`,
`KEYCLOAK_ADMIN_PASSWORD` (и при наличии — `MINIO`/`S3` ключи) в `.env`;
`.env` не коммитится (`.gitignore`). `validate_security_baseline`
слабые пароли не проверяет — это ручной шаг чеклиста выше.

## Troubleshooting
- Keycloak не healthy: ждите 60–90с (первый старт + импорт realm).
- Повторный импорт realm пропускается (`Realm already exists. Import skipped`);
  для полного сброса Keycloak нужен чистый volume (`docker compose down -v`).
- Backend ждёт `postgres` + `redis` + `keycloak` (depends_on healthy).
- Миграции: `docker compose exec -T backend python scripts/migrate.py status`.

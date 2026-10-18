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

## Swagger и вход через Keycloak

[Пошаговый гайд со скриншотами](SWAGGER_AUTH_GUIDE.md): вход, выполнение запроса, выход и проверка ролей.

Откройте `http://localhost:8000/docs`, нажмите **Authorize** и выберите
**KeycloakLogin** (вход через Keycloak с PKCE, `client_secret` пустой) либо
**HTTPBearer** (готовый `access_token`, без слова `Bearer`). Достаточно одного
способа. Проверить вход можно запросом `GET /api/v1/auth/me` через **Try it out**.
После перезагрузки Swagger авторизуйтесь снова: токены не сохраняются в localStorage.

Перед первым запуском удалённого стенда задайте реальные публичные адреса:

```bash
FRONTEND_ORIGIN=https://crm.example.org \
SWAGGER_PUBLIC_URL=https://api.example.org python3 keycloak/render_realm.py
```

Если Swagger открыт через прокси с префиксом, укажите его в `SWAGGER_PUBLIC_URL`,
например `https://crm.example.org/backend`, и задайте backend соответствующий
ASGI `root_path`. `KEYCLOAK_EXTERNAL_URL` должен быть доступен браузеру, а не
указывать на внутреннее имя контейнера.

Для уже существующего realm повторный импорт не применяется. В Keycloak,
**Clients → rtk-frontend**, обновите **Valid Redirect URIs**: адрес CRM с `/*`
и точный публичный URL `/docs/oauth2-redirect.html`; в **Web Origins** укажите
оба origin (схема, хост, порт, без пути). Сохраните публичный тип клиента,
**Standard flow** и **PKCE S256**. Не удаляйте тома ради обновления этих настроек.
При другом OAuth-клиенте задайте `SWAGGER_OAUTH_CLIENT_ID` и настройте его аналогично.

Браузерная проверка обоих способов входа (нужны frontend-зависимости и Chromium
Playwright): `node scripts/check-swagger-auth.cjs`. По умолчанию используются
локальный backend и демо-администратор. Для другого стенда задайте
`SWAGGER_BASE_URL`, `E2E_ADMIN_USERNAME` и `E2E_ADMIN_PASSWORD`. Проверка вызывает
только `/auth/me` и проверяет сброс токена при перезагрузке страницы.

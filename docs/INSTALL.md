# Установка и обновление

Инструкция сверена с Compose и кодом на 20.10.2026. Команды выполняются из корня репозитория. Нужны Docker и Docker Compose v2. Python на хосте нужен только для вспомогательных Python-скриптов. Для Bash-скриптов на Windows используйте WSL или Git Bash; основные команды Compose работают в PowerShell.

## Первый запуск

Скопируйте `.env.example` в `.env`, если своего файла ещё нет. Задайте пароли `POSTGRES_PASSWORD`, `KEYCLOAK_DB_PASSWORD` и `KEYCLOAK_ADMIN_PASSWORD`. Не заменяйте уже настроенный `.env` шаблоном при обновлении.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Запускаются PostgreSQL 16, Redis 7 под именем `keydb`, Keycloak, backend, worker и frontend. Обычный запуск не включает модель ИИ и SMTP-сервер. Первое скачивание образов и сборка требуют сети; срок готовности зависит от компьютера.

Backend выполняет `baseline`, затем SQL-миграции `up` и `verify`. Worker использует тот же образ с другой командой запуска и ждёт готовности backend. Данные приложения и Keycloak находятся в разных базах одного PostgreSQL.

| Сервис | Локальный адрес |
|---|---|
| CRM | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Keycloak | http://localhost:8081 |

PostgreSQL и Redis не имеют опубликованных портов. Для SQL-консоли при стандартном пользователе и имени базы:

```bash
docker compose exec postgres psql -U rtk -d rtk
```

Проверка API в Bash:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
```

В Windows PowerShell используйте `curl.exe` либо `Invoke-RestMethod`. Эти два маршрута не проверяют доступность модели, SMTP или выполнение фоновых заданий. Проверяйте также `docker compose ps` и логи нужного сервиса.

## Демо

```bash
docker compose exec -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo
docker compose exec -e DEMO_MODE=true backend python -m app.scripts.provision_demo_scope
docker compose exec backend python scripts/create_workflow_template.py
```

Seed добавляет пять демонстрационных вузов и связанные каталоги. Скрипт scope назначает `manager` три демо-вуза, `user` один; после него нужен повторный вход. Отдельная команда создаёт стандартный шаблон на 14 этапов. Экземпляр Workflow затем запускается из интерфейса. Автоматического создания пятиэтапного шаблона и Workflow в текущем seed нет.

Демо-логины realm `rtk`: `admin/admin123`, `manager/manager123`, `user/user123`. Они импортируются только при создании realm. Консоль Keycloak использует пароль `KEYCLOAK_ADMIN_PASSWORD`, а не пароль демо-пользователя приложения. [Подробности seed](DEMO_SEED.md).

## Помощник

```bash
python backend/scripts/start_assistant.py
```

Скрипт подключает дополнительный Compose-файл, запускает Ollama, скачивает модели и готовит индекс. Модель устанавливается в контейнере. При обновлениях сохраняйте тот же набор Compose-файлов:

```bash
docker compose -f docker-compose.yml -f docker-compose.assistant.yml --profile assistant up -d --build
docker compose -f docker-compose.yml -f docker-compose.assistant.yml exec -T backend python -m scripts.assistant check
```

Без дополнительного файла backend снова получит стандартную настройку с выключенным помощником. Одного добавления `ASSISTANT_ENABLED=true` в корневой `.env` недостаточно: базовый Compose не передаёт эту переменную. [Полная инструкция](ASSISTANT.md).

## Публичные адреса и Swagger

Задайте `KEYCLOAK_EXTERNAL_URL`, `FRONTEND_ORIGIN` и `SWAGGER_PUBLIC_URL` для своего стенда. Адрес Keycloak должен открываться браузером, а не указывать на внутреннее имя контейнера. Перед импортом нового realm подготовьте callback и web origins. Скрипт читает переменные процесса, не корневой `.env`.

Bash:

```bash
FRONTEND_ORIGIN=https://crm.example.org SWAGGER_PUBLIC_URL=https://api.example.org python3 keycloak/render_realm.py
```

PowerShell:

```powershell
$env:FRONTEND_ORIGIN = 'https://crm.example.org'
$env:SWAGGER_PUBLIC_URL = 'https://api.example.org'
python keycloak/render_realm.py
```

Это примеры адресов, замените их своими. Скрипт изменяет файл импорта realm. Для существующего realm импорт пропускается: обновите `Clients / rtk-frontend` вручную. В Valid Redirect URIs нужны адрес CRM с `/*` и точный адрес backend `/docs/oauth2-redirect.html`; Web Origins содержит origin каждого сервиса без пути. Префикс прокси учитывается в `SWAGGER_PUBLIC_URL` и ASGI `root_path`.

Публичные параметры frontend собираются в JavaScript. После изменения адресов пересоберите frontend. Корневой `.env` не передаётся всем контейнерам целиком: проверяйте `environment` и `build.args` в Compose. Для новых backend-параметров при необходимости добавьте отдельный Compose override.

В Swagger нажмите Authorize и используйте один способ: KeycloakLogin с PKCE либо HTTPBearer с готовым access token без слова Bearer. Проверьте `GET /api/v1/auth/me`. [Гайд со скриншотами](SWAGGER_AUTH_GUIDE.md).

## Обновление

Сначала сделайте резервную копию. Затем из нужной ветки:

```bash
git pull --ff-only
docker compose up -d --build
docker compose exec backend python scripts/migrate.py status
docker compose exec backend python scripts/migrate.py verify
docker compose logs --tail 100 backend worker
```

Если помощник включён, замените команду `up` вариантом с двумя Compose-файлами. После обновления проверьте вход, доступ назначенного пользователя, открытие паспорта и выполнение тестового отчёта на своём стенде. Keycloak не обновляет существующий realm повторным импортом; изменение пароля в `.env` также не меняет пароль уже созданной роли PostgreSQL.

## Резервная копия

Нужны обе базы PostgreSQL и файловые тома. Для выгрузки баз не используйте перенаправление бинарного dump через старый Windows PowerShell. Создайте отдельный каталог `backups`, затем сформируйте файлы внутри контейнера:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/crm.dump'
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$KEYCLOAK_DB" -Fc -f /tmp/keycloak.dump'
docker compose cp postgres:/tmp/crm.dump ./backups/crm.dump
docker compose cp postgres:/tmp/keycloak.dump ./backups/keycloak.dump
```

Файловые тома: `workflow-storage`, `reports-storage`, `import-staging`. Для помощника дополнительно `assistant-models` и `assistant-index`. Архивируйте файлы согласованно с базой, при остановленной записи, и проверяйте восстановление в отдельном окружении. Физические имена томов зависят от имени Compose-проекта, по умолчанию `team26`. Резервная копия Git не заменяет эту копию данных.

`docker compose down` сохраняет тома. Флаг `-v` удаляет базы и файлы и не нужен для обновления или исправления настроек входа.

## Диагностика

| Симптом | Что проверить |
|---|---|
| Нет вузов у пользователя | Назначения `university_ids`, затем новый вход для обновления токена |
| Помощник выключен | Дополнительный Compose-файл и `scripts.assistant check` |
| Отчёт остаётся в очереди | Состояние и логи worker, общие тома отчётов и импорта |
| Письма не уходят | SMTP и `EMAIL_NOTIFICATIONS_ENABLED`; встроенное уведомление не означает доставку письма |
| Swagger не завершает вход | Публичный callback, Web Origins, issuer и audience |
| Backend не стартует | Логи применения SQL-миграций и подключение к PostgreSQL |

Базовый Compose использует Keycloak `start-dev` и локальные пароли-примеры. Публикация стенда требует отдельной настройки TLS, секретов, адресов и резервирования. Состояние проверки репозитория: [аудит](PROJECT_AUDIT_2026-10-20.md).

# Перечень библиотек и компонентов

> Снимок на develop. Версии backend — замерены в собранном образе
> (`python -c "from importlib.metadata import distributions"`),
> frontend — из `frontend/package.json`, инфраструктура — из
> `Dockerfile`/`docker-compose.yml`. Лицензии — по метаданным пакетов
> и PyPI; перед релизом сверять с первоисточником.

Интерактивная документация API: `http://localhost:8000/docs` (Swagger UI),
`http://localhost:8000/redoc`, машиночитаемая спека — `/openapi.json`.

## Backend (`backend/`, Python 3.12, FastAPI)

| Пакет | Версия | Лицензия | Назначение |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | HTTP API, валидация, OpenAPI |
| uvicorn | 0.53.0 | BSD-3-Clause | ASGI-сервер |
| starlette | 1.6.0 | BSD-3-Clause | HTTP-ядро FastAPI |
| pydantic | 2.13.5 | MIT | DTO/схемы |
| pydantic-settings | 2.15.0 | MIT | Конфигурация |
| sqlalchemy | 2.0.54 | MIT | ORM |
| alembic | 1.20.0 | MIT | Миграции БД |
| psycopg (+binary) | 3.3.5 | LGPL-3.0-or-later | Драйвер PostgreSQL |
| python-jose | 3.5.0 | MIT | Проверка Keycloak JWT |
| cryptography | 50.0.1 | Apache-2.0 AND BSD | Криптобэкенд jose |
| python-multipart | 0.0.32 | Apache-2.0 | multipart/XLSX upload |
| openpyxl | 3.1.5 | MIT | Парсинг XLSX импорта |
| httpx | 0.28.1 | BSD-3-Clause | HTTP-клиент |
| pytest | 9.1.1 | MIT | Тесты |

В `pyproject.toml` дополнительно задекларированы (для следующих этапов,
в runtime-образ пока не входят): `redis`, `minio`, `openpyxl` ✓,
`reportlab`, `python-dateutil`. Код, их использующий
(`app/infrastructure/*`), работает с guarded-импортами и fallback
на in-memory/local — приложение стартует без них.

## Frontend (`frontend/`, Next.js App Router + React + TypeScript)

| Пакет | Версия | Лицензия | Назначение |
|---|---|---|---|
| next | ^16.3.5 | MIT | App Router, SSR/static build |
| react / react-dom | ^19.1.1 | MIT | UI |
| keycloak-js | ^26.0.0 | Apache-2.0 | Keycloak login |
| typescript | ^5.9.2 | Apache-2.0 | Типизация |
| eslint / eslint-config-next | ^9.36.0 / ^16.3.5 | MIT | Lint |
| @types/react, @types/react-dom | ^19.1.x | MIT | Типы |

## Инфраструктура (Docker Compose)

| Образ | Тег | Лицензия | Сервис |
|---|---|---|---|
| postgres | 16-alpine | PostgreSQL Licence | БД `rtk` + `keycloak` (порт хоста 5433) |
| quay.io/keycloak/keycloak | 26.7.4 | Apache-2.0 | Keycloak, realm `rtk` (порт 8081) |
| python (база backend) | 3.12-slim | PSF | Образ backend (`:8000`) |
| node (сборка и рантайм frontend) | 22-alpine | OpenJS Foundation | Next standalone (`:3000`) |

## Порты и точки входа

| Компонент | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend Swagger UI | http://localhost:8000/docs |
| Backend ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| Keycloak | http://localhost:8081 (realm `rtk`) |
| PostgreSQL | localhost:5433, user `rtk`, db `rtk` |

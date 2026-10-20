# Зависимости и образы

Сверено с манифестами `main` на 20.10.2026. Это версии из репозитория, а не замер установленных пакетов на внешнем стенде. Backend фиксирует зависимости в `backend/pyproject.toml`, frontend устанавливается через `npm ci` по `frontend/package-lock.json`.

## Backend

Контейнер использует Python 3.12. Манифест допускает Python начиная с 3.11.

| Пакет | Версия в pyproject.toml |
|---|---|
| FastAPI | 0.116.1 |
| Uvicorn | 0.35.0 |
| SQLAlchemy | 2.0.43 |
| Pydantic | 2.11.7 |
| pydantic-settings | 2.10.1 |
| psycopg | 3.3.4 |
| python-jose | 3.5.0 |
| httpx | 0.28.1 |
| redis | 6.4.0 |
| minio | 7.2.18 |
| openpyxl | 3.1.5 |
| xlrd | 2.0.2 |
| xlwt | 1.3.0 |
| ReportLab | 4.4.9 |
| pypdfium2 | 5.14.0 |
| rarfile | 4.2 |
| python-multipart | 0.0.32 |
| python-dateutil | 2.9.0.post0 |
| email-validator | 2.3.0 |
| Alembic | 1.16.5 |

Эти зависимости устанавливаются в runtime-образ, а не оставлены для будущих этапов. Alembic остаётся в зависимостях для совместимости; действующая схема управляется SQL-миграциями и `scripts/migrate.py`, не Alembic upgrade.

Дополнение `[dev]`: pytest 9.0.3, httpx 0.28.1, Ruff 0.15.13 и pypdf 6.10.0. PDF-генерация использует системные DejaVu-шрифты из Dockerfile.

## Frontend

| Пакет | Версия в package-lock.json |
|---|---|
| Next.js | 16.3.5 |
| React | 19.3.0 |
| TypeScript | 5.9.3 |
| Tiptap React | 3.32.0 |

В интерфейсе также используются TanStack Query и Table, React Hook Form, Zod, Recharts, dnd-kit, keycloak-js, react-markdown, jsPDF и html-to-image. Версии с `^` в package.json являются диапазонами; для воспроизводимой установки нужен lock-файл. Docker и SourceCraft CI используют Node.js 22.

## Docker Compose

| Сервис | Образ |
|---|---|
| postgres | `postgres:16-alpine` |
| keydb | `redis:7-alpine` |
| keycloak | `quay.io/keycloak/keycloak:26.7.4` |
| backend и worker | Сборка из `python:3.12-slim` |
| frontend | Сборка и runtime из `node:22-alpine` |
| ollama, дополнительный профиль | `ollama/ollama:0.13.5` |

Опубликованы порты 3000, 8000 и 8081. PostgreSQL и Redis доступны только во внутренней сети Compose. Точные версии, которые фактически запущены на конкретном сервере, проверяются в его образах отдельно.

# Интеграция по API (P5-15-01)

- **Base URL**: `http://localhost:8000/api/v1` (через frontend — same-origin `/api/v1`).
- **Спека**: `/openapi.json`, Swagger `/docs`, ReDoc `/redoc`. Схема Bearer
  называется `BearerAuth` (Keycloak JWT, realm `rtk`).
- **Аутентификация**: Authorization: `Bearer <Keycloak access token>`.
  Проверка: `GET /api/v1/auth/me`. 401 — `AUTH_REQUIRED`, 403 — `FORBIDDEN`.
- **Пагинация**: `page` (1-based) + `page_size` (есть в паспортных и list endpoints).
- **Фильтрация**: UnifiedFilter (`date_from/date_to`, `university_ids`,
  `direction_ids`, `program_ids`, `product_ids`, `responsible_ids`,
  `workflow_statuses`) — единая семантика для аналитики и отчётов.
- **Ошибки**: единый `ErrorResponse` (`detail` + код); 422 — валидация.

## Основные группы
| Группа | Примеры |
|---|---|
| Universities | `GET /universities`, `GET /universities/{id}/passport?include=health_score,audit` |
| Health Score | `GET /universities/health-score?ids=a,b` (batch ≤50), `GET /universities/{id}/health-score` |
| Workflow | `POST /workflow/instances`, `GET /workflow/instances/{id}`, `POST .../transition`, `.../comments`, `.../tasks`, attachments |
| Teachers/Students | `GET /teachers/...`, `GET /universities/{id}/students` (через students-модуль) |
| Catalog | `/directions /programs /products /vendors /responsibles` |
| Analytics/Reports | `GET /analytics/...`, `POST /reports` (202) → `GET /reports/{job}` → `GET /reports/{job}/download` |
| Import | `POST /import/...` (staging + worker) |

## Пример (Python, stdlib)
```python
import json, urllib.request
token = "<access token>"
req = urllib.request.Request(
  "http://localhost:8000/api/v1/universities",
  headers={"Authorization": f"Bearer {token}"},
)
print(json.load(urllib.request.urlopen(req))[0]["id"])
```

## Webhooks / Rate limiting
Не реализованы (deferred). Внешних LMS/сайта нет — интеграции отсутствуют.

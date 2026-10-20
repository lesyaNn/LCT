# API сервиса

Основной путь `/api/v1`. При обращении из frontend используется прокси того же origin. Для локального прямого обращения: `http://localhost:8000/api/v1`.

Полная схема формируется из подключённых маршрутов: `/openapi.json` на backend. Swagger находится в `/docs`, ReDoc в `/redoc`. Внутри CRM есть отдельная страница `/api` с фильтрами методов, схемами, правами и примерами. `GET /api/v1/service-api` и `GET /api/v1/openapi.json` требуют JWT.

## Вход

Используется Keycloak access token с проверкой RS256, issuer, audience и срока действия. В запросе нужен `Authorization: Bearer <access_token>`. Swagger предлагает альтернативные схемы HTTPBearer и KeycloakLogin с PKCE; достаточно одной. ID token не заменяет access token. [Настройка Swagger](SWAGGER_AUTH_GUIDE.md).

Роль задаёт разрешённые действия, а назначения вузов задают область данных. Администратор каталогов и руководитель имеют разные права. Публичная проверка лицензии `/api/v1/public/licenses/{license_id}/verification` является отдельным явно открытым методом; остальные бизнес-методы проверяют авторизацию.

## Основные группы

Все пути таблицы указаны относительно `/api/v1`. Поддерживаемые методы, поля и условия доступа смотрите в актуальном OpenAPI.

| Группа | Точки входа |
|---|---|
| Вузы | `/universities`, `/universities/map`, `/universities/{university_id}/passport` |
| История и оценка | `/universities/{university_id}/history`, `/universities/{university_id}/health-score` |
| Справочники | `/directions`, `/programs`, `/products`, `/vendors`, `/responsibles`, `/contracts`, `/licenses` |
| Workflow | `/workflow/templates`, `/workflow/instances`, переходы, задачи, комментарии и вложения |
| Отчёты | `/reports`, `/reports/preview`, `/reports/statistics`, `/reports/templates` |
| Импорт | `/import/upload`, `/import/sheets/preview`, `/import/execute`, `/import/jobs` |
| Обучение | `/universities/{university_id}/education-statistics`, `/universities/{university_id}/teachers` |
| Заметки | `/notes`, `/notes/mentions`, `/notes/export/pdf` |
| Помощник | `/assistant/chat`, `/assistant/quick-replies`, `/assistant/conversations` |
| Прочее | `/search`, `/notifications`, `/audit`, `/admin/users`, `/integrations` |

Для паспорта поддерживается дополнительный блок `?include=audit`. Health Score имеет отдельный маршрут; `include=health_score` не является допустимым значением. Старые несмонтированные роутеры не входят в поставляемый API, даже если их файлы остались в репозитории.

Большинство списков используют `page` и `page_size`. Например, ответ списка вузов содержит `items`, `total`, `page` и `page_size`. Заметки используют `offset` и `limit`. Не считайте способ пагинации универсальным для всех методов.

## Пример чтения

```python
import json
import urllib.request

request = urllib.request.Request(
    "http://localhost:8000/api/v1/universities?page=1&page_size=20",
    headers={"Authorization": "Bearer <access_token>"},
)
with urllib.request.urlopen(request) as response:
    result = json.load(response)
for university in result["items"]:
    print(university["id"], university["name"])
```

## Ошибки и задания

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Проверьте правильность заполнения полей.",
    "request_id": "00000000-0000-4000-8000-000000000000",
    "details": {}
  }
}
```

401 означает отсутствие или проблему токена, 403 отсутствие права, 404 отсутствие либо недоступность объекта, 409 конфликт данных или версии, 422 ошибку валидации. У конкретных маршрутов есть дополнительные коды. При превышении лимита возвращается 429.

Создание отчёта возвращает 202 и задание. Проверяйте `/reports/{job_id}` до готовности, затем скачивайте `/reports/{job_id}/download`. Поддерживаются XLS, XLSX, PDF и JSON. Файловый ответ нужно читать как бинарные данные, а не JSON. Для обработки заданий должен работать worker.

Полный контракт, примеры фильтров, экспортов и сервисного клиента: [инструкция API](../frontend/public/docs/api/integration.md). Внешние LMS и сайт по умолчанию отключены; их контракты описаны отдельно в [EXTERNAL_EDUCATION_CONTRACTS.md](EXTERNAL_EDUCATION_CONTRACTS.md). Модуль тендеров не реализован.

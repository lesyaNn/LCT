# P5-18: offline-демо (без сети) + видеобекап

## Офлайн-прогон

```bash
./scripts/demo-setup.sh   # .env → up --build → wait-healthy → seed (идемпотентно)
```

Всё локально: PostgreSQL/Redis/Keycloak (realm `rtk`, импорт из
`keycloak/realm-export.json`), seed 10 вузов, файлы — локальные volumes.
Внешних LMS/сайта нет (стаб `modules/integrations` не смонтирован, демо на
seed — mock-адаптеры P5-08-02 отсутствуют и здесь не требуются).

Единственное сетевое требование — Docker-образы (`postgres:16-alpine`,
`redis:7-alpine`, `keycloak:26.7.4`, `python:3.12-slim`): скачайте заранее
(`docker compose pull`) — дальше стенд работает без интернета.

Проверка после `demo-setup.sh`:

```bash
curl -sf http://localhost:8000/health && curl -sf http://localhost:3000/health
SMOKE_TOKEN=<токен-из-браузера> ./scripts/smoke.sh
```

## Видеобекап (`demo-backup.mp4`)

MP4 в репозитории не хранится (бинарник). Порядок записи: поднять стенд по
разделу выше → записать скринкаст (заявка → паспорт вуза → отчёты) →
положить файл рядом с релиз-заметкой / в shared-диск команды и указать
ссылку здесь:

- `demo-backup.mp4`: _ссылка заполняется исполнителем_

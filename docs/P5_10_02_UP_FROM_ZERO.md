# P5-10-02: прогон с нуля (up-from-zero) + артефакты

## Процедура (критерий: `down -v → up --build → smoke < 3 мин`)

```bash
docker compose down -v
time ./scripts/verify-docker.sh   # build+up, healthchecks, миграции, smoke
# smoke-тест API (токен — из браузера, Keycloak direct grants у rtk-frontend нет):
SMOKE_TOKEN=<Keycloak-access-token> python3 scripts/smoke_test.py
# быстрый smoke без токена:
./scripts/smoke.sh
```

Что проверяет `verify-docker.sh` (5 шагов): build+up → `wait-healthy.sh 300` →
HTTP `/health` backend/frontend + realm Keycloak → `migrate.py status` в
контейнере → smoke (skip с подсказкой без `SMOKE_TOKEN`).

## Артефакты прогона

| Дата | Коммит | `up --build` | healthy, с | smoke | Примечание |
| --- | --- | --- | --- | --- | --- |
| _заполняется исполнителем_ | | | | `<3 мин` / нет | приложить `docker compose logs backend` при FAIL |

Артефакты хранить: вывод `verify-docker.sh` + время `time`, скрин `/docs`
при необходимости — в релиз-заметке, не в репозитории (бинарники не трекаем).

# Руководство пользователя — CRM ИТ-Школа Ростелеком (P5-15-01)

## 1. Вход в систему
- Откройте `http://localhost:3000` → **Войти**.
- Логин проходит через Keycloak (realm `rtk`): введите логин/пароль
  демо-пользователя (`admin/admin123`, `manager/manager123`,
  `user/user123`).
- После возврата в React доступны профиль, роль и кнопки
  **Проверить Backend** / **Проверить Admin доступ**.

## 2. Дашборд
- KPI: число вузов, средний Health Score, просроченные этапы.
- Batch Health Score грузится одним запросом
  `GET /api/v1/universities/health-score?ids=...` (до 50 за раз).

## 3. Список вузов
- `GET /api/v1/universities` (фильтры `q`, `region`).
- Фильтры страницы сохраняются в sessionStorage и восстанавливаются
  при возврате (см. `frontend/src/stores/filters.ts`).

## 4. Паспорт вуза
- `GET /api/v1/universities/{id}/passport?include=health_score,audit`:
  программы, продукты, лицензии, встречи, документы, Health Score с breakdown.
- Вкладки программ/преподавателей — пагинированные endpoints
  `/passport/programs`, `/passport/teachers`.

## 5. Паспорт преподавателя
- Готовность, сертификаты, программы. Просроченные сертификаты подсвечиваются.

## 6. Workflow
- Создание инстанса, чтение, переход вперёд
  (`POST /api/v1/workflow/instances/{id}/transition`,
  поля `target_instance_stage_id`, `comment` — комментарий обязателен),
  комментарии, задачи, вложения.
- Переход требует права `workflow.change_status` и проверки university scope.

## 7. Отчёты
- Создание: `POST /api/v1/reports` (формат `xlsx|pdf|json`, фильтры
  UnifiedFilter, колонки из реестра) → `202` + `job_id`.
- Статус: `GET /api/v1/reports/{job_id}` (poll до `ready`).
- Скачивание: `GET /api/v1/reports/{job_id}/download`.
- Исполняет отдельный `worker`-контейнер; API только создаёт jobs.

## 8. Аудит
- Отдельного UI для `/audit` нет (endpoint deferred, в prod не смонтирован).
  История изменений видна в паспорте (`include=audit`) и истории переходов
  workflow (`GET /api/v1/workflow/instances/{id}/transitions`).

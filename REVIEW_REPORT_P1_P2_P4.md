# Ревью проекта — соответствие задачам P1 / P2 / P4 + проблемные места

**Дата:** 23.09.2026
**Скоуп:** `hackathon_rostelecom_tasks/tasks/p1/` (38), `p2/` (37), `p4/` (22) vs `backend/`, `frontend/`, `docker-compose.yml`, `README.md`
**Метод:** чтение всех файлов задач + grep/read кода, прогон `pytest`/`vitest`, `git status/log`. Статусы: ✅ выполнено / ⚠️ частично / ❌ не выполнено.

## 0. Прогресс доделок (ветка `fix/backend-review-p1p2p4`)

- [x] P1-07-01 / P1-08-01: полный CRUD встреч и студентов — `app/modules/meetings/`, `app/modules/students/` (POST/GET на `/universities/{id}/…`, GET/PATCH/DELETE на `/meetings|students/{id}`, пагинация, RBAC `university.read/edit`, scope 403, 201/204/404/409/422). Тесты `tests/test_p1_07_08_crud_api.py` (8 passed на PG).
- [x] P1-03-01: `health_status`-фильтр + `sort_by=health_score` в `GET /universities` — расчёт в Python на странице через кэш 5 мин, total после фильтра, `UniversityRead.health_score/health_status`. Тесты `tests/test_p1_03_health_filter.py`.
- [x] P1-05-02: зафиксировано — отдельной таблицы trainings нет (MVP), задокументировано в обеих TeacherPassport-схемах.
- [x] P1-01-04: отклонение «SQL вместо Alembic» уже задокументировано в `backend/alembic/README_ARCHIVED.md` — дополнительно ничего не требуется.
- [x] P2-05-02: отсутствие файла теперь 404 вместо 500 (+ обновлены 2 пина).
- [x] P2-08-01: `transition_instance` инвалидирует health-кэш (best-effort).
- Сьют: SQLite `354 passed, 0 failed`; PG-таргет `216 passed` по затронутым файлам. Полный PG-прогон: 7 падений предсуществуют на чистом дереве (report_jobs/import/migrate-cycle), не связаны с этими изменениями.

## 0.1. Прогресс P2 (та же ветка, решения: точечно без ломки / env-allowlist / хук snapshots)

- [x] P2-05-01: allowlist через `UPLOAD_ALLOWED_EXTENSIONS` (пусто = открыто как раньше; задано = 415). Тесты-пины обновлены.
- [x] P2-09-01 (WRITE): `write_transition_snapshot` — один snapshot `transition` на вуз/день (first wins), best-effort, переход не роняет. Тесты `tests/test_p2_09_01_transition_snapshots.py` (4 passed на PG).
- [x] P2-05-02: `GET /instances/{id}/attachments` — пагинированный список метаданных.
- [x] P2-04-01: `DELETE /comments/{id}` (author-in-window/admin, scope до удаления) + пагинация списка комментариев (PaginatedResponse). Тесты `tests/test_p2_04_02_crud_gaps.py` (5 passed на PG).
- [x] P2-02-04: guard — disable этапа, current в активном инстансе, даёт 409; retire-путь (увести инстансы → disable → 200) покрыт обновлённым `test_p2_11_04_template_edit.py`.
- Отложено сознательно: переименования таблиц/контрактов, admin-override, audit fire-and-forget, seed-имена, cron-daily (нужны спека/миграции/фронт).
- Сьют: SQLite `354 passed, 0 failed`; PG по всем затронутым P2-файлам зелёный.

## 0.2. Остаток — не сделано (фиксация)

### P1 (backend, мелочь)
- [ ] P1-03-06: `*Filter.apply()`-классы вместо инлайн-фильтров в роутерах (работает, рефактор-чистота).
- [ ] Дубль `UniversityPassport` (`app/schemas/university.py` vs `app/modules/universities/passport_schemas.py`): снести нельзя — ломает `docs/mocks` для P3. Только синхрон при изменениях (пометка уже в коде).

### P2 (backend — нужны спека/решение, не выдумывалось)
- [ ] P2-01-01/02/04: `is_default`, `created_by`, partial-unique active-инстанса, `template_version`; seed 14 этапов к именам/optional/SLA из ТЗ (риск: ломает моки/тесты на README-именах).
- [ ] P2-01-03: FK `attachments→documents`, `is_system`/`user_name` в комментариях, статусы tasks (`open/done` vs ТЗ).
- [ ] P2-02-01/03: `is_default`/`stages_count`/фильтр active; автовыбор default-шаблона; поля progress/health/comments в `InstanceDetail`.
- [ ] P2-03-01/03: контракт transition (`due_date` в request, response `{prev,new}`, коды ошибок ТЗ); `user_name`/`due_date` в истории.
- [ ] P2-03-02: admin-override переходов (политика: да/нет).
- [ ] P2-03-04: audit fire-and-forget + `request_id` (сейчас синхронно в транзакции — редизайн).
- [ ] P2-09-01 (остаток): daily-cron snapshots (есть только transition-hook) + `document_update`-писатели.
- [ ] P2-12-01: моки в `backend/docs/mocks/` вместо `docs/mocks/` из ТЗ (фронт их не импортирует).
- [ ] P2-11-01/02 + P4-12-01/13-01: PG-покрытие, golden на 3 фильтрах, `benchmark_p4_dev2.py` с фиксацией p50/p95.

### P4 (backend)
- [ ] P4-06-01/10-02: `POST /import/execute` в worker (сейчас sync в request); проверить savepoint-per-row.
- [ ] P4-10-03: `Версия ПО` + `Email менеджера` в `EXAMPLE_MAPPING`.
- [ ] P4-05-01/07-01: унифицировать `totals`/`average` при пустой выборке (строки vs вузы, 0 vs None).
- [ ] P4-09-01: зафиксировать 6-й статус `archived` в спеке матрицы.

### Фронт (другой программист, не трогалось)
- [ ] P2: kanban workflow, health-виджет, attention-items.
- [ ] P4: Reports UI (колонки/пресеты/submit/polling/download), живые графики из `overview`, матрица с tooltip, mapping UI импорта, PNG на живых данных.

### Предсуществующие падения на PG (вне скоупа P1/P2/P4, проверено на чистом дереве)
- [ ] `test_p1_schema::test_sql_migrate_upgrade_downgrade_cycle`, 3× `test_p4_06_report_jobs_pg`, 2× `test_p4_import` — падают и без наших изменений.

## 1. Executive Summary

| Блок | ✅ | ⚠️ | ❌ | Оценка готовности |
|---|---|---|---|---|
| P1 (ядро: схема, DTO, CRUD, паспорта, seed, индексы) | 30 | 7 | 1* | ~85% — ядро готово, нет standalone CRUD встреч/студентов |
| P2 (workflow, Health Score, файлы, история) | 15 | 21 | 1 (frontend P2 целиком) | ~65% backend силён, frontend P2 = 0 |
| P4 (аналитика, отчёты xlsx/pdf/json, import, jobs) | 7 | 15 | 0 (но frontend P4 почти пуст) | ~70% backend, frontend на моках |
| *P1-04-06 засчитан в ✅; ни одна P1 не провалена полностью, но P1-07-01/P1-08-01 API отсутствуют. | | | | |

**Главный вывод:** backend закрывает большую часть P1/P2/P4-логики. Главные риски для демо и приёмки — **(1) отсутствие P2/P4 UI во frontend, (2) красный тестовый сьют, (3) расхождения контрактов (имена таблиц, DTO, фильтры), (4) security/dev-швы и legacy-мёртвый код.**

## 2. P1 — детально (38 задач)

### P1-01 схема/миграции
| ID | Суть | Статус | Доказательства / замечания |
|---|---|---|---|
| P1-01-01 | 9 таблиц каталогов, FK/unique/индексы, без `universities.responsible_id` | ✅ | `models/catalog.py`, `migrations/000001_core_catalog`, `000002_contracts_licenses` |
| P1-01-02 | 4 таблицы преподавателей, CASCADE, unique | ✅ | `models/teachers.py`, `000003_teachers`. Отклонение: `teacher_programs.program_id` RESTRICT вместо CASCADE — задокументировано, обоснованно (защита каталога, P1-11-03) |
| P1-01-03 | 6 таблиц студенты/связи/история, timeline | ✅ | `models/interactions.py` (+бонус `MeetingDocument`), `000004/000005`, `passport_service.py` UNION ALL |
| P1-01-04 | Alembic upgrade/downgrade/autogenerate | ⚠️ | Архитектурное отклонение: активный путь `scripts/migrate.py` + `migrations/*.up/down.sql` (20 версий 000001–000020), `alembic/` — read-only архив. Функциональный эквивалент есть, но AC в лоб не выполняется — зафиксировать как deviation |
| P1-01-05 | created_at/updated_at tz-aware | ✅ | `models/mixins.py` TimestampMixin, везде TIMESTAMPTZ |

### P1-02 DTO
| ID | Статус | Замечания |
|---|---|---|
| P1-02-01 University DTO (6 схем) | ✅ | `schemas/university.py`. Дубль `UniversityPassport` в `modules/universities/passport_schemas.py` (канон — модульный) — риск рассинхрона |
| P1-02-02 Direction/Program/Product/Vendor DTO | ✅ | `schemas/catalog.py`, используется в `catalog/router.py` |
| P1-02-03 Teacher DTO + readiness | ✅ | `schemas/teacher.py`, `modules/teachers/passport_*`, `services/teacher_readiness.py` |
| P1-02-04 Общие enum в одном модуле | ✅ | `schemas/common.py`. Minor: `PaginationParams.page_size le=200` vs контракт 100; дубль enum в `models/enums.py` (осознанное разделение DB/API) |
| P1-02-05 OpenAPI без ошибок, BearerAuth | ✅ | `main.py` custom_openapi → BearerAuth. Скрипта `check_openapi.py` нет, эквивалент — `test_p5_openapi_docs.py` |

### P1-03 CRUD
| ID | Статус | Замечания |
|---|---|---|
| P1-03-01 Universities CRUD + фильтры/сортировка | ⚠️ | Есть пагинация/поиск/404/409/RBAC (`catalog/router.py`). **Нет `health_status`-фильтра и `sort_by=health_score`** |
| P1-03-02 Directions CRUD | ✅ | unique code, RESTRICT при удалении с программами |
| P1-03-03 Programs CRUD | ✅ | `direction_id` обязателен, фильтр `direction_id` |
| P1-03-04 Products CRUD | ✅ | unique (vendor,name,version), фильтр `vendor_id` |
| P1-03-05 Vendors/Responsibles CRUD | ✅ | Отклонение: удаление responsible — CASCADE связок, а не запрет (зафиксировано в роутере) |
| P1-03-06 Унифицированные pagination/search | ⚠️ | Есть `PaginationParams/FilterBase`, ILIKE, whitelist. Но `le=200` vs 100, нет `*Filter.apply()`-классов, фильтры инлайн в роутерах |

### P1-04 Паспорт вуза
| ID | Статус |
|---|---|
| P1-04-01 `GET /universities/{id}/passport` | ✅ `universities/passport_router.py`, `passport_service.get_passport`, без N+1, workflow_summary есть |
| P1-04-02 программы/преподаватели/студенты + readiness | ✅ блоки 2–4 сервиса |
| P1-04-03 продукты/лицензии/договоры, derived status | ✅ блоки 5–6, единый источник `license_status.py` |
| P1-04-04 документы/встречи/ответственные/timeline, лимиты 20/10/10 | ✅ блок 7–8, timestamptz |
| P1-04-05 `?include=health_score,audit`, graceful degradation | ✅ `parse_include()`, 400 на неизвестные, fallback `recent_audit=[]`, тест `test_passport_include.py` |
| P1-04-06 N+1 ≤8 запросов, <500ms, subresources | ✅ 8 SELECT (было 17), subresources с пагинацией, `test_passport_performance.py`. Метрики прод — только на PG-стенде |

### P1-05 Паспорт преподавателя / P1-06 Лицензии / P1-07/08 Встречи/Студенты
| ID | Статус | Замечания |
|---|---|---|
| P1-05-01 `GET /teachers/{id}/passport` | ✅ | Legacy int-PK `teachers/router.py` не смонтирован — удалить/пометить deprecated |
| P1-05-02 квалификации/обучения/сертификаты | ✅ с оговоркой | Нет таблицы `teacher_trainings` — `trainings: []`. Допустимо для MVP, но AC формально не закрыт данными |
| P1-05-03 `compute_teacher_readiness` чистая функция | ✅ | `services/teacher_readiness.py`, переиспользуется Health Score E |
| P1-06-01 модель лицензий/договоров | ✅ | Все поля ТЗ, без `contracts.vendor_id`, `000009_license_row_links` |
| P1-06-02 derived status @property | ✅ | `ContractStatus` без `expires_soon` (маппится в active + days_to_expiry) — зафиксировать для P3 |
| P1-07-01 встречи + meeting_documents M:N + CRUD | ⚠️ | Модель ✅, **CRUD endpoints ❌** — только чтение внутри паспорта. Блокер если P2/P3 ждут `/meetings` |
| P1-08-01 студенты (без ПДн) + CRUD | ⚠️ | Модель ✅ (только StudentsSummary), **CRUD endpoints ❌** |

### P1-09 Seed / P1-10 Индексы / P1-11 Тесты / P1-12 Моки
| ID | Статус | Замечания |
|---|---|---|
| P1-09-01 demo seed 8–12 вузов | ✅ | `scripts/seed_demo.py` → `app/db/seed.py`, 10 вузов, идемпотентно |
| P1-09-02 истекающие лицензии, просрочки | ✅ | Относительные даты, кроме workflow-инстансов (это P2) |
| P1-09-03 30 преподавателей readiness | ✅ | `TEACHER_PLAN` дословно по ТЗ |
| P1-10-01 индексы | ✅ | `000007/000008` композиты, readiness осознанно не индексируется |
| P1-10-02 EXPLAIN ANALYZE | ✅ | `scripts/explain_passport.py`, `check_explain.py` — требует живой PG |
| P1-11-01 unit CRUD, покрытие >80% | ✅ | `test_p1_crud.py` и др., 29 passed. Покрытие замерить в CI (pytest-cov отчёта нет) |
| P1-11-02 тесты паспортов | ✅ | Все зелёные incl. include/perf |
| P1-11-03 тесты лицензий/фильтров | ⚠️ | **1 падающий тест** `test_health_status_filter_not_implemented` — `TypeError` в legacy `modules/universities/repository.py:11` на Python 3.14 (`inspect.signature` + `list[University]`). Чинить удалением legacy |
| P1-12-01 `docs/mocks/*.json` | ✅ | Оба файла в корне `docs/mocks/`, генератор + re-валидация. Minor: в `backend/docs/mocks/` только university — дубль дополнить/удалить |

**Frontend P1:** backend-скоуп; в `frontend/src` страниц паспортов нет (только Catalog/Analytics/Auth-check). Для P1 не gap, но P3-экраны проверить в UI нельзя.

## 3. P2 — детально (37 задач)

> Глобально: таблицы намеренно переименованы (`instance_stages`, `workflow_stage_transitions`, `workflow_comments/attachments/tasks`, `sla_days` вместо `estimated_days`). Задокументировано в миграциях, но расходится с именами ТЗ — фиксировать как отклонение контракта.
> **Frontend P2: `grep workflow|kanban|health_score` по `frontend/src` = 0. Весь P2 UI не выполнен.**

| ID | Суть | Статус | Главное замечание |
|---|---|---|---|
| P2-01-01 | workflow_templates/stages, 14 этапов | ⚠️ | Нет `is_default`, `created_by`, `estimated_days`=sla_days |
| P2-01-02 | instances/instance_stages, partial unique active | ⚠️ | Нет partial unique `WHERE active`, нет триггера, нет `template_version`; статусы снапшота ≠ ТЗ |
| P2-01-03 | transitions/comments/attachments/tasks | ⚠️ | Нет FK attachments→documents, нет `is_system/user_name`, статусы tasks `open/done` ≠ ТЗ, allowlist отключён |
| P2-01-04 | seed 14 этапов | ⚠️ | Названия из README ≠ ТЗ; optional только этап 5 (по ТЗ 5,10,12); sla NULL; нет is_default |
| P2-02-01 | CRUD templates | ⚠️ | Нет is_default/stages_count/фильтра is_active |
| P2-02-02 | POST/PATCH stages, reorder | ✅ | Маршрут PATCH отличается; нет DELETE |
| P2-02-03 | POST instances + detail | ⚠️ | template_id обязателен (нет default), в Detail нет progress/health/comments/tasks/transitions |
| P2-02-04 | rename/reorder/add/disable | ⚠️ | Нет блокировки disable-current и авто-skip в активных |
| P2-03-01 | POST transition | ⚠️ | Другой контракт request/response (`target_instance_stage_id`), нет due_date/кодов ТЗ |
| P2-03-02 | validate_transition | ✅ | Нет admin-override (админ проходит те же проверки) |
| P2-03-03 | история переходов | ⚠️ | Нет user_name/due_date; 422 vs 400 за пустой комментарий |
| P2-03-04 | audit WORKFLOW_TRANSITION | ⚠️ | Синхронно в транзакции (роняет переход), нет request_id/comment |
| P2-04-01 | комментарии CRUD | ⚠️ | Нет DELETE, пагинации, can_*, is_system; привязка к instance, не instance_stage |
| P2-05-01 | upload 10 типов/50MB | ⚠️ | **Allowlist отключён** (`ALLOWED_*=None`, `PARTIAL_BLOCKED_BY_MISSING_FILE_TYPE_CONTRACT`) — осознанно, нет контракта типов |
| P2-05-02 | metadata/download/delete | ⚠️ | Нет list-endpoint; отсутствие файла → 500 вместо 404 |
| P2-05-03 | лимиты/хранение | ✅ | Ключ UUID-hex вместо `{instance}/{stage}/`; лимит не через имена env из ТЗ |
| P2-05-04 | StorageBackend ABC Local+S3 | ✅ | — |
| P2-06-01 | дедлайны/overdue | ✅ | — |
| P2-07-01 формула HS | ✅ | WEIGHTS 0.25/0.2/0.2/0.2/0.15 | 
| P2-07-02 T (задачи) | ✅ | critical = days>14 или priority critical |
| P2-07-03 D (документы) | ✅ | valid=signed/active + expires>=today |
| P2-07-04 S (этапы) | ✅ | — |
| P2-07-05 E (преподаватели) | ✅ | Через канонический compute_teacher_readiness |
| P2-07-06 L (запуск) | ✅ | Порог риска 30д (в ТЗ 14/30 — зафиксировать) |
| P2-07-07 статусы 85/60 | ✅ | — |
| P2-07-08 сборка ответа | ✅ | Коды reasons отличаются от текста ТЗ — проговорить |
| P2-08-01 GET health-score + Redis 5мин | ⚠️ | **Инвалидация не подключена** — `invalidate_health_score()` никто не вызывает |
| P2-08-02 batch ?ids= до 50 | ✅ | Последовательно вместо gather — обоснованно (sync Session) |
| P2-08-03 ranking | ✅ | — |
| P2-09-01 snapshots + cron + history | ⚠️ | Только READ-path; **нет cron-воркера и event-писателей** |
| P2-10-01 5 правил attention | ✅ | Коды отличаются от ТЗ |
| P2-10-02 GET attention-items | ✅ | — |
| P2-11-01 тесты transition | ⚠️ | 23 passed / 48 skipped (нужен PG); покрытие >95% не замерено |
| P2-11-02 тесты upload/overdue | ⚠️ | Нет кейса «запрещённый тип → 400» (allowlist off) |
| P2-11-03 тесты HS edges | ✅ | — |
| P2-11-04 тесты template edit | ✅ | — |
| P2-12-01 mock JSON для P3 | ⚠️ | Лежат в `backend/docs/mocks/`, а не `docs/mocks/`; фронт не импортирует |

## 4. P4 — детально (22 задачи)

> Backend P4 силён (фильтр, dataset, xlsx/pdf/json, jobs, analytics, import — есть с тестами). **Frontend P4 почти отсутствует: только мок-графики на canvas, нет Reports UI, polling, живых фильтров/колонок/матрицы.**

| ID | Статус | Доказательства / gap |
|---|---|---|
| P4-01-01 UnifiedFilter DTO+Service+dependency | ✅ | `analytics/filters.py`, `filter_service.py`, тесты |
| P4-01-02 единый фильтр везде | ⚠️ | Backend ✅ (`catalog/router.py:120`, `report_request.py`), golden-тест ✅. Frontend ❌ — моки, TODO заменить на `GET /analytics/overview` |
| P4-02-01 dataset 14 колонок | ⚠️ | Backend ✅ `columns.py:MANDATORY_COLUMNS`, `dataset.py` license-grain. Grain `University×License` ≠ `programs×products` из ТЗ (осознанно, без декартового раздутия). Frontend выбора ❌ |
| P4-02-02 выбор колонок + пресеты | ⚠️ | Backend ✅ `resolve_columns`, PRESETS, динамические SELECT/JOIN, уважается в xlsx/pdf/json. Frontend чекбоксов ❌ |
| P4-03-01 POST /reports xlsx 202+job | ✅ backend | `reports_router.py:127`, `report_worker.py`, тесты. Frontend submit ❌ |
| P4-03-02 XLSX 2 листа/freeze/filter | ✅ | `xlsx.py` HEADER_ROW=6, freeze A7, autofilter, ширины 1:1, sanitize от формул-инъекций |
| P4-04-01 POST /reports pdf | ✅ | `pdf.py` reportlab landscape A4 + 2 нативных графика, пустой dataset валиден |
| P4-04-02 кириллица PDF DejaVu | ✅ | `Dockerfile` fonts-dejavu-core, `ensure_pdf_fonts`, тест с «МГУ» — образцово |
| P4-05-01 JSON export | ✅ | `json_export.py` ensure_ascii=False, ISO-даты. Отклонения: totals.universities=distinct имён; by_health_status по строкам, не вузам |
| P4-06-01 report jobs / 10 параллельных | ⚠️ | Reports ✅ (`report_jobs` 000018/19, SKIP LOCKED, worker-сервис в compose, RBAC, 24h expiry). **Import sync в request** (`imports/router.py:165` + TODO перенести в worker) |
| P4-06-02 submit→poll→download | ⚠️ | Backend ✅ (202/GET/download + import polling-контракт). Frontend polling ❌ (grep polling пуст; скачивание только мок-PNG) |
| P4-07-01 GET /analytics/overview KPI+7 блоков | ✅ backend | `analytics/router.py:101`, кэш 60s, auth-before-cache. `average=0` при пустой выборке ≠ None в PDF/JSON — несогласованность |
| P4-08-01 4 диаграммы из overview | ⚠️ | Backend данные ✅. Frontend ⚠️ — 4 canvas на `MOCK_*`, набор ≠ ТЗ (нет «вузы по стадиям»), фильтры не применяются |
| P4-09-01 матрица вуз×программа | ⚠️ | Backend ✅ `GET /analytics/matrix` + guard 50k. Frontend ❌. Backend добавил 6-й статус `archived` сверх ТЗ — правильно, но проговорить |
| P4-09-02 health/readiness в матрице | ⚠️ | Backend ✅ все 5 полей в MatrixCell. Frontend рендера/tooltip ❌ |
| P4-10-01 XLS import preview/mapping | ⚠️ | Backend ✅ preview 10 строк, лимиты 10MB/5000. Mapping UI ❌ (P3) |
| P4-10-02 валидация/summary/идемпотентность | ⚠️ | Логика ✅ (коды, error-report листы, idempotency_key). Асинхронность ⚠️ (sync, savepoint-per-row перепроверить) |
| P4-10-03 10 полей ТЗ | ⚠️ | Нет `responsible.email` и `Версия ПО` в EXAMPLE_MAPPING (в TARGET_FIELDS есть) |
| P4-11-01 export PNG | ⚠️ | На моках ✅ (кнопка 📥 PNG, HiDPI 2x). На живых ❌; типа «по стадиям» нет |
| P4-12-01 golden dataset 3 фильтра | ⚠️ | Есть минимальный инвариант `test_p4_golden_seed.py` (list==dataset==overview==exports), но нет 3 фильтров/чисел ТЗ (автор отказался как от противоречивых) |
| P4-13-01 performance p50/p95, 10 параллельных | ⚠️ | Инструменты ✅ (`benchmark_p4_dev2.py`, check_explain, индексы). Результатов ❌ — не запускалось, нет передачи в P5-14-01 |
| P4-14-01 mock JSON для P3 | ✅ | Оба файла в `docs/mocks/` 1:1 со схемами. Но фронт захардкодил копию в `MOCK_*` (уже разошлась с моком по workflow_distribution) |

## 5. Проблемные места (общий аудит)

### КРИТИЧНО
1. **Красный сьют:** `pytest` → 2 collection errors (`test_p4_04_05_pg.py`, `test_p4_04_pdf_unit.py` — нет PDF-зависимостей) + 1 failed (`test_health_status_filter_not_implemented`, legacy `universities/repository.py:11` + Python 3.14). Без `TEST_DATABASE_URL` 566 skipped — «зелёный» прогон из README мнимый.
2. **Auth bypass-шов:** `core/security.py:141` `auth_dev_bypass` (fail-closed, в compose false — ок), но `/ready` (`main.py:103`) светит `dev_bypass/issuer/audience` без auth; десятки тестов переключают глобал без фикстур — флаки при параллели.
3. **Секреты-дефолты:** `change-me` в compose/`.env.example`/`config.py` (minioadmin), демо-пароли в README, `environment:` в plaintext (`docker inspect`). `.env` в гите нет (правильно), но CI-guard `grep change-me` не добавлен.
4. **CORS:** `main.py:45` `allow_credentials=True` + `allow_methods/headers=["*"]` — лишнее расширение поверхности.
5. **Две вселенные кода:** канон (замаунчен в `api/router.py:27`) vs legacy (`modules/workflow/`, `universities/router`, `teachers/router`, `programs/`, `documents/`, `dashboard/`, `reporting/` vs `analytics/reports`, `DeferredBase` vs `Base`). Latent `ImportError` в `modules/auth/dependencies.py:6` (`user_permissions` из `core.security` вместо `core.permissions`). `scripts/generate_p2_mocks.py:225` `create_all` нарушает «SQL — единственный источник».
6. **Миграции vs доки:** README «11 версий 000001–000011», реально 20 (000001–000020). `CANON_TABLES` в `test_p0_deferred_registry.py` без `import_jobs/job_attempts`. `entrypoint.sh:33` SQLite-фолбэк без миграций → дрейф схемы.
7. **Пагинация:** legacy `audit/documents/teachers/programs` — `limit(200).all()`/`q.all()` без page/page_size (канон пагинирован — контраст).
8. **Compose прод-неготов:** keycloak `start-dev` (HTTP/dev), orphan `nginx/nginx.conf` (нет сервиса, нет `Host/X-Forwarded-*`, нет `/openapi.json`), `POSTGRES_PORT=5433` не используется.

### ВАЖНО
9. **RBAC неравномерный:** legacy — голый `get_current_user` (любой токен). `security.py:119` отсутствие `university_ids` = глобальный доступ (fail-open, задокументирован как additive-scope). У manager нет `workflow.change_status`/`university.edit`, у curator нет `import.write` — сверить с ТЗ; в UI не отражено.
10. **`print` вместо логгера** (`seed.py:622`, `seed_workflow.py:120`), голые `except: pass` (`imports/service.py:208`, `storage.py`, `json_export.py`, `pdf.py`, `passport_service.py:1237`).
11. **Фронт на моках:** `pages.tsx:67` + `AnalyticsCharts.tsx:8` TODO, `CatalogViewer.tsx:22` хардкод `page_size=100` без UI-пагинации, `client.ts:75` 401→auto-login без причины. `typecheck` падает (`tsc: Permission denied`), единственный тест `router.test.ts` (4 passed).
12. **Валидация:** `ilike(f"%{q}%")` без экранирования `%/_` (wildcard-инъекция/тормоза); `region` в `UniversityRepository.list` молча игнорируется (200 с неверной выборкой).

### МЕЛОЧИ
13. **Git-гигиена:** ветка `feature/dev3-import-mocks-png`, untracked `.DS_Store`, `hackathon_rostelecom_tasks/` вне гита, `node_modules/.bin` в статусе — в `.gitignore` только `.env` (нет `node_modules/`, `.DS_Store`, `__pycache__/`, `.pytest_cache/`). Висячий stash, ~8 `p1-*` веток без squash.
14. **Хардкод-URL:** `frontend/config.ts:16` fallback `:8081`, `backend/config.py:17` localhost/keycloak:8080.
15. **README:** порты 5433 vs 5432, `keycloak/render_realm.py` упомянут, но путь проверить.
16. **N+1:** канон батчится корректно; риск только в legacy без eager-loading.

## 6. Что чинить первым (приоритет)

1. **Зелёный сьют:** удалить/починить legacy `universities/repository.py:11`, вынести PDF-тесты в integration-марку или добавить зависимость; добавить `pytest-cov` и замер >80/95%.
2. **Удалить legacy из поставки** (`workflow/`, `reporting/`, `identity/`, `documents/`, `dashboard/`...), починить `auth/dependencies.py:6`; убрать `create_all` из скриптов, SQLite-фолбэк из entrypoint.
3. **Синхронизировать README (20 миграций), CANON_TABLES, убрать `dev_bypass` из `/ready`, зажать CORS, добавить `.gitignore` позиции и CI-guard на `change-me`.**
4. **Закрыть контрактные gaps:** P1-07-01/P1-08-01 CRUD (или зафиксировать «только паспорт» как решение), P1-03-01 health_status/sort, `PaginationParams le=100`, единый `UniversityPassport`, моки в одном месте (`docs/mocks/`).
5. **P2:** подключить инвалидацию health-кэша к писателям; добавить cron/event-писатели snapshots (или зафиксировать «только READ»); решить allowlist типов файлов (взять список у заказчика); 500→404 при отсутствии файла; admin-override/DELETE stage по решению.
6. **P4→P3 связка:** Reports UI (колонки/пресеты/submit/polling/download), живые графики из `overview`, матрица с tooltip, import mapping UI + перенос execute в worker; прогнать `benchmark_p4_dev2.py` и golden на demo seed, зафиксировать цифры.
7. **Frontend P2 с нуля:** kanban workflow, health-score виджет, attention-items — иначе INT-06 и демо-вертикаль не показать.

## 7. Как проверено (воспроизводимость)

- `ls hackathon_rostelecom_tasks/tasks/p1|p2|p4` — 38/37/22 файла, все прочитаны.
- `PYTHONPATH=. python -m pytest tests/ -q` → 2 collection errors; с игнором → `1 failed, 351 passed, 566 skipped`.
- `grep workflow|kanban|health_score frontend/src` → 0; `grep polling|refetchInterval frontend/src` → пусто.
- Ключевые файлы: `backend/app/models/*`, `migrations/000001–000020`, `modules/workflow_*/`, `modules/health_score/*`, `modules/analytics/*`, `modules/imports/*`, `frontend/src/pages/pages.tsx`, `components/AnalyticsCharts.tsx`, `CatalogViewer.tsx`.

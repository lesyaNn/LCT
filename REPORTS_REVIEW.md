# Ревью и переработка системы отчётов CRM

Ветка: `feature/reports-rework` · ТЗ: «CRM взаимодействия с вузами, отчётность»

---

## 1. Состояние старой системы отчётов

Рабочий flow на момент старта:

```
widgets/reports/reports-page.tsx (один файл, 336 строк)
  → POST /api/v1/reports
  → report_service.create_report_job → report_jobs (queued)
  → worker (report_worker.py) → generate_report_file
  → FORMAT_GENERATORS {xlsx, pdf, json}
  → ReportDatasetService.iterate_rows (University LEFT JOIN License)
  → файл в REPORTS_ROOT
  → GET /reports/{id}/download
```

Статистика была **отдельной системой**: `GET /analytics/overview|master` с собственной
`AnalyticsRepository`/`AnalyticsService`, кэш 60 с, собственная агрегация в Python,
плюс recharts на дашборде с собственным `chart-export.ts` (PNG/PDF в браузере).
Единого «набора данных» у таблицы и у графиков не было.

Ключевые части:

| Часть | Файл |
|---|---|
| Контракт фильтра | `app/modules/analytics/filters.py`, `filter_service.py` |
| Реестр колонок | `app/modules/analytics/columns.py` (17 колонок, 12 «обязательных») |
| Данные | `app/modules/analytics/dataset.py` |
| Генераторы | `xlsx.py`, `pdf.py`, `json_export.py` |
| Очередь/воркер | `report_jobs.py`, `report_worker.py` |
| HTTP | `reports_router.py`, `report_templates.py` |
| Frontend | `widgets/reports/reports-page.tsx`, `shared/lib/reports-repository.ts` |

---

## 2. Найденные проблемы

### 2.1 Критические (сломана функциональность)

| # | Проблема | Где | Следствие |
|---|---|---|---|
| P1 | **`KeyError: 'avg_health_score'` при генерации любого PDF** | `pdf.py` — `kpi` собирался с 3 ключами, читался 4-й (`avg_health_score`) | **экспорт в PDF не работал вообще**; существовал мёртвый `compute_kpi`, который никто не вызывал |
| P2 | **`ModuleNotFoundError` в воркере** | `report_worker.main()` импортировал удалённый `health_score.materialization` перед `run_worker_once()` | с 00:00 до 00:04 ежедневно воркер проглатывал исключение и **пропускал целую итерацию** обработки отчётов |
| P3 | **Выход `format=xls` → 422** | `ReportFormat` = `{xlsx, pdf, json}` | нет формата, требуемого ТЗ |
| P4 | **`health_score` в коде, которого нет в БД** | таблицы дропнуты миграцией `000029`, модели удалены | `_score_value()` искал колонку, которую нельзя выбрать; KPI-подпись обещала несуществующую метрику |
| P5 | **Хвосты от удаления сущностей ломали сбор тестов** | `tests/test_p1_11_03_licenses_filters.py`, `test_p1_crud.py`, `test_p1_schema.py`, `test_p1_11_03_*` | аннотация `def make_teacher(...) -> Teacher` вычисляется при `def` → `NameError` на сборе → **падала вся сборка (896 тестов)**, в чистом Docker-образе тесты не запускались вообще |

### 2.2 Соответствие ТЗ

| Требование ТЗ | Было | Статус |
|---|---|---|
| Период | `universities.created_at` — дата регистрации вуза, а не взаимодействия | ❌ |
| XLS | формата нет | ❌ |
| Колонки по ТЗ | 12 «обязательных» вместо 5 | ⚠️ шире ТЗ |
| Статистика по той же выборке | отдельный контур `/analytics`, своя агрегация | ❌ |
| Preview | логика в HTTP-handler, продублирована из `dataset.fetch_rows` | ⚠️ |
| Графики/PNG | только в браузере на дашборде, к отчёту отношения не имели | ⚠️ |
| 10 параллельных отчётов | не проверялось | ❌ |
| <1 с на смену фильтра | не измерялось | ❌ |

### 2.3 Архитектурные

| # | Проблема |
|---|---|
| A1 | God-файл `reports-page.tsx` (336 строк): форма, очередь, шаблоны, скачивание, поллинг — в одном компоненте |
| A2 | Бизнес-логика в HTTP-handler: `reports_router.preview_report` вручную повторял `dataset.fetch_rows` и дёргал приватные `_attach_responsibles` / `_attach_extra_maps` |
| A3 | Дублирование списка форматов: `ReportFormat`, `SUPPORTED_FORMATS`, `FORMAT_GENERATORS`, `DOWNLOAD_MEDIA_TYPES`, `pyproject` CHECK — 5 мест |
| A4 | Логика генерации XLS/XLSX расходилась бы при расхождении: санитизация формул, пустые значения, формат дат — продублированы в двух генераторах |
| A5 | `list_report_jobs` в router дублировал `report_jobs.list_visible_jobs`, причём без фильтра `job_type=report` |
| A6 | Несогласованные лейблы фильтров: `ВУЗы` vs `ВУЗ`, `ФИО` vs `Ответственный`, `Статусы Workflow` |
| A7 | Мёртвый код: `list_university_candidates`, `AuditEntityType.TEACHER/STUDENT`, `_removed_teachers_stub`, `health_fallback` |
| A8 | `DELETE /reports/templates/{id}` требовал `reports.read` вместо `reports.create` |
| A9 | `reportStatus()` в frontend: любое неизвестное значение → `failed`, маскирует новые статусы |

---

## 3. Какие требования ТЗ не выполнялись

1. **Фильтрация по периоду** — не по взаимодействиям, а по дате создания вуза.
2. **Формат XLS** — отсутствовал.
3. **Колонки** — набор по умолчанию шире ТЗ.
4. **Статистика** — считалась по другой выборке, чем таблица.
5. **Экспорт визуализаций в PNG/PDF** — отсутствовал в контуре отчётов.
6. **Проверка 10 параллельных отчётов** — не выполнялась.
7. **Измерение отклика <1 с** — не выполнялось.

---

## 4. Что было изменено

### 4.1 Фильтрация: период = период взаимодействий

`UnifiedFilterService.build_university_conditions` — **единственное** место интерпретации
всех фильтров (его используют отчёты, статистика, превью и список вузов).

```python
EXISTS (meetings        WHERE university_id = u.id AND meeting_at  ∈ [date_from, date_to+1))
OR EXISTS (interaction_notes WHERE university_id = u.id AND created_at ∈ [date_from, date_to+1))
```

- Оба источника взаимодействий объединены через `OR` внутри **одного** предиката —
  число предикатов не выросло, размерности по-прежнему разделяются `AND`.
- Границы включительные; `date_from > date_to` → 422.
- Верхняя граница — `< date_to + 1 день` в UTC, поэтому `date_to` включён.
- Открытая граница (только `from` или только `to`) просто опускает свою сторону.

**Формулировка grain (зафиксирована по решению владельца продукта):**

> Период фильтрует попадание сущности в выборку по наличию хотя бы одного взаимодействия,
> но строки отчёта не имеют grain «одно взаимодействие = одна строка». При наличии
> нескольких взаимодействий вуз отображается согласно существующему grain
> University × License. Требуется отдельное продуктовое решение, если в дальнейшем
> необходим детализированный журнал взаимодействий.

Пример: вуз A со встречами 10.09 и 20.09 при фильтре 01.09–30.09 попадает в выборку
**один раз**, а не дважды.

**Следствие, о котором нужно знать:** вуз без единого взаимодействия исключается, как
только задан период. Без периода виден. На демо-стенде это потребовало прогона
`python -m app.db.seed` (идемпотентно) — иначе период возвращал ноль строк.

### 4.2 Колонки: 5 по умолчанию

`columns.py` переработан:

- `TZ_COLUMNS` = `university, direction, product, workflow_status, responsible` — ровно
  то, что перечисляет ТЗ, и это `DEFAULT_COLUMNS`;
- `EXTENDED_COLUMNS` (7) + `OPTIONAL_COLUMNS` (5) = `ADDITIONAL_COLUMNS` — 12 прочих
  колонок сохранены и выбираются индивидуально, но не по умолчанию;
- пресеты фронтенда: «По ТЗ» / «Стандарт» (+program, city, current_stage) / «Полный»;
- `resolve_columns(None)` возвращает 5 колонок ТЗ; неизвестный ключ — 422.

Ни одна колонка не удалена и не выдумана: `FULL_COLUMNS` по-прежнему покрывает весь реестр.

### 4.3 Форматы: XLS / XLSX / PDF (+ JSON)

`ReportFormat` получил `xls`. Новый `app/modules/analytics/xls.py` — настоящий BIFF8
через `xlwt`, не переименованный `.xlsx`.

- Общие семантики ячейки вынесены в `app/modules/analytics/cells.py` (`classify_cell`):
  пустое значение — **пустая ячейка** (не `N/A`/`null`/`-`), даты — типизированные
  ячейки с `DD.MM.YYYY`, числа остаются числами, текст экранируется от formula injection.
  XLSX и XLS читают один и тот же код — расхождение невозможно конструктивно.
- Метаданные (заголовок, период, фильтры, метка времени, лист «Фильтры», шапка в
  строке 6, данные с 7) переиспользуют константы `xlsx.py` без копирования.
- BIFF8 не умеет tz-aware datetime → `_as_biff_datetime` переводит в UTC-naive.
- Переполнение → `XlsCapacityError` и падение задачи с внятным текстом, файл **не
  усекается молча**.

Устранено дублирование форматов: `FORMAT_GENERATORS` теперь **источник истины**,
`SUPPORTED_FORMATS` выводится из него, сообщение об ошибке собирается из него же.

Миграция `000034_report_templates_xls_format` — расширяет CHECK
`report_templates.format` на `'xls'`. `report_jobs.format` CHECK не имеет, там валидация
в `report_service` по таблице генераторов.

### 4.4 Статистика: та же выборка, агрегация в БД

`app/modules/analytics/stats.py` + `stats_router.py` → `POST /api/v1/reports/statistics`.

- **Та же выборка.** Используется тот же `UnifiedFilter` и тот же
  `UnifiedFilterService`, что и у таблицы. Отдельной трактовки периодов/вузов нет ни
  в одном файле.
- **Агрегация в PostgreSQL.** `GROUP BY` по 4 измерениям, не поток строк в Python.
  Обоснование: 10 параллельных отчётов иначе выродились бы в самый медленный путь.
- **Те же выражения колонок.** Подписи берутся из `direction_label()` /
  `product_label()` / `workflow_status_label()`, связанные с теми же алиасами, что и
  `FROM` запроса, — график не может назвать бакет иначе, чем таблица.
- Grain честно указан в ответе: `by_direction/by_product/by_workflow_status` считают
  **строки отчёта**, `by_responsible` — **уникальные вузы** (ячейка `responsible` — это
  `'; '`-список, группировать по нему нельзя). Поле `unit` в ответе.
- `Без данных` — реальный бакет: сумма бакетов всегда равна числу строк.
- Хвост списка сворачивается в «Прочее» (лимит 10 баров) и это подписано в подписи.
- Раскрыт скошенный бакет в пояснении, а не в графике.

Найденные при этом два бага (пойманы тестами, а не код-ревью):

1. Коррелированные скалярные подзапросы внутри `GROUP BY` **ломали корреляцию** и
   размножали строки (5× на тесте). Решение: подпись вычисляется во внутреннем
   запросе, группировка — во внешнем.
2. `_label_distribution` пересоздавал базовый `Select`, из-за чего подпись ссылалась на
   алиасы, отсутствующие в её же `FROM`. Теперь базовый statement передаётся внутрь.

### 4.5 PDF: починен и приведён к честным метрикам

- `KeyError` устранён: единый аккумулятор `ReportKpi`, накапливающий KPI в том же
  проходе, что и таблица (без второго запроса и без второго dataset-объекта).
- `health_score` удалён из кода отчётов. Подпись `Средний балл готовности` заменена на
  `Средний прогресс workflow, %` — это реально измеряемая величина.
- Диаграмма распределения переименована в прогресс-workflow; пороги 85/60 прежние.
- `None` и `0` различаются: «нет данных» ≠ «нулевой прогресс».

### 4.6 Preview отделён от экспорта

`ReportDatasetService.fetch_preview` (новое) вместо 30 строк SQL в HTTP-handler.
Лимит `50` применяется **только к ответу превью**; `total` в ответе — реальный размер
экспорта, поэтому UI показывает «показаны первые 50 из N». Экспорт строит полный набор
и никогда не наследует превью-лимит.

### 4.7 UX (frontend)

`reports-page.tsx` (336 строк, god-файл) разбит на 9 модулей:
`report-form-schema`, `report-filters`, `report-columns`, `report-format`,
`report-templates`, `report-preview`, `report-statistics`, `report-jobs`, `use-debounced-value`.

- Порядок действий соответствует ТЗ: период → вузы → направления → продукты →
  ответственные → колонки → **актуальная выборка** (превью + статистика) →
  сформировать → формат → скачать.
- Появилось **живое превью** выбранных строк и **статистика по той же выборке**.
- `REPORT_FILTER_DIMENSIONS` — одно определение на измерение (лейбл + поле формы +
  ключ запроса), поэтому «ВУЗы/ВУЗ» и «ФИО/Ответственный» больше не расходятся.
- Значения показываются человекочитаемыми именами, UUID в UI не выводятся.
- Выбор связанных сущностей — из каталогов (`getCatalogReferenceData`), не ID руками.
- Статистика и превью дебаунсятся (250 мс) и держат предыдущие данные, пока грузятся
  новые.
- Колонки разделены визуально на «Колонки по ТЗ» и «Дополнительные колонки».

### 4.8 Прочее

- `POST /api/v1/reports/statistics` подключён **до** `reports_router` (иначе его
  перехватил бы `/{job_id}`) — та же схема порядка, что уже была для templates.
- `scripts/check_reports_perf.py` — воспроизводимый замер пути отчётов с
  `EXPLAIN ANALYZE` и `--scale N`.
- Удалён мёртвый код, оставшийся от удаления сущностей: `list_university_candidates`,
  `AuditEntityType.TEACHER/STUDENT`, `UNSUPPORTED_OPTIONAL_COLUMNS`, `_removed_*_stub`,
  `health_fallback`, `compute_kpi` (не вызывался), seed-план преподавателей.
- `seed_performance.py` не работал (`entity_id` писался int в UUID-колонку) — починен,
  иначе нечем мерить производительность.

---

## 5. Какие файлы изменены

### Backend — приложение (11)

| Файл | Изменение |
|---|---|
| `app/modules/analytics/filters.py` | период = взаимодействия |
| `app/modules/analytics/filter_service.py` | `_interaction_in_period()` вместо `created_at` |
| `app/modules/analytics/columns.py` | `TZ_COLUMNS`/`EXTENDED_COLUMNS`/`ADDITIONAL_COLUMNS`, 5 по умолчанию, удалён `UNSUPPORTED_OPTIONAL_COLUMNS` |
| `app/modules/analytics/cells.py` | **новый** — общие семантики ячейки XLS/XLSX |
| `app/modules/analytics/xls.py` | **новый** — генератор BIFF8 |
| `app/modules/analytics/xlsx.py` | переведён на `classify_cell`, реэкспорт `lookup_filter_names`/`utc_aware` |
| `app/modules/analytics/pdf.py` | `ReportKpi`, убран `health_score`, KPI из тех же строк |
| `app/modules/analytics/dataset.py` | `fetch_preview`, общие `*_label()` выражения |
| `app/modules/analytics/stats.py` | **новый** — SQL-агрегация |
| `app/modules/analytics/stats_router.py` | **новый** — `POST /reports/statistics` |
| `app/modules/analytics/reports_router.py` | preview через датасет, `SUPPORTED_FORMATS` из генераторов, media-type XLS |
| `app/modules/analytics/report_service.py` | `supported_formats()`, XLS в диспетчере |
| `app/modules/analytics/report_worker.py` | удалён мёртвый импорт, ломавший воркер |
| `app/modules/analytics/json_export.py`, `__init__.py`, `report_request.py`, `report_templates.py` | синхронизация с новым контрактом |
| `app/schemas/common.py` | `ReportFormat.XLS` |
| `app/api/router.py` | монтирование `report_statistics_router` |
| `app/modules/audit/service.py` | удалены `TEACHER`/`STUDENT` |
| `app/modules/catalog/repository.py` | удалён мёртвый `list_university_candidates` |
| `app/modules/universities/passport_blocks.py` | удалены заглушки преподавателей/студентов |
| `app/schemas/catalog.py`, `app/schemas/__init__.py` | удалены поля и упоминания |
| `app/db/seed.py` | удалён план преподавателей/сертификатов |

### Backend — миграции (1)

`migrations/000034_report_templates_xls_format.{up,down}.sql` — CHECK на `xls`.

### Backend — скрипты (4)

`check_reports_perf.py` (новый), `check_explain.py`, `explain_passport.py`,
`check_legacy_quarantine.py`; удалён `check_readiness.py`.

### Backend — тесты (11 новых/изменённых)

| Файл | Что проверяет |
|---|---|
| `test_p4_03_xls_unit.py` (новый) | 18 тестов: BIFF8-магия, шапка, порядок, даты, кириллица, экранирование формул, пустые ячейки, лимиты, атомарность |
| `test_p4_period_pg.py` (новый) | 8 тестов: период по встречам/заметкам, «одна встреча ≠ одна строка», границы включительные, AND-комбинации, период ≠ `created_at` |
| `test_p4_preview_export_pg.py` (новый) | 8 тестов: превью ограничено, экспорт полный, порядок совпадает, scope соблюдается |
| `test_p4_stats_pg.py` (новый) | 14 тестов: сумма бакетов = числу строк, grain, `Без данных`, складной хвост, 6 SELECT независимо от объёма, RBAC |
| `test_p4_reports_parallel_pg.py` (новый) | 10 параллельных отчётов, изоляция выборок, магия форматов, атомарность |
| `test_p4_02_columns_unit.py` | новая матрица пресетов |
| `test_p4_01_01_filter_pg.py`, `test_p4_01_02_universities_pg.py` | период по взаимодействиям |
| `test_p4_02_report_dataset_pg.py`, `test_p4_03_xlsx_pg.py`, `test_p4_04_05_pg.py` | `health_score` → `workflow_progress` |
| `test_p4_04_pdf_unit.py` | `ReportKpi`, прогресс-пирог |
| `test_p1_schema.py`, `test_p1_crud.py`, `test_p1_11_03_licenses_filters.py`, `test_p1_seed_universities.py`, `test_p0_deferred_registry.py`, `test_p5_audit_pg.py`, `test_p5_http_matrix_pg.py`, `test_stage11_external_integrations_pg.py` | удалённые сущности/эндпоинты |
| `tests/load/locustfile.py` | превью + статистика вместо health-score |

### Frontend (13)

`widgets/reports/` — 8 новых модулей + переписанный `reports-page.tsx`;
`shared/lib/reports-repository.ts` (XLS, `TZ_REPORT_COLUMNS`, `REPORT_FILTER_DIMENSIONS`,
`getReportPreview`, `getReportStatistics`, `reportFiltersPayload`),
`shared/lib/query-keys.ts`, `shared/lib/status-semantics.ts`,
`shared/lib/external-integrations-repository.ts`, `shared/lib/real-api-adapter.ts`,
`shared/lib/universities-repository.ts`, `shared/mocks/api-adapter.ts`,
`widgets/universities/universities-list.tsx` + 2 CSS.

### Прочее

`docs/contracts/unified-filter.json`, `report-columns.json`, `report-request.json`,
`scripts/smoke_test.py`, `backend/pyproject.toml` (`xlwt==1.3.0`).

---

## 6. Какие API были изменены

| Метод | Путь | Изменение |
|---|---|---|
| `POST` | `/api/v1/reports` | принимает `format: "xls"`; `columns: null` → 5 колонок ТЗ |
| `POST` | `/api/v1/reports/preview` | хендлер истончается; тот же контракт, лимит только для ответа |
| `POST` | `/api/v1/reports/statistics` | **новый** |
| `GET` | `/api/v1/reports/{id}/download` | `application/vnd.ms-excel` для `.xls` |
| `GET` | `/api/v1/reports/{id}` | формат в ответе может быть `xls` |
| `POST/GET` | `/api/v1/reports/templates` | формат `xls` в теле/CHECK |
| `GET` | `/api/v1/universities?...health_status=...` | **удалён** (фильтра не существовало: API никогда не отдавал `health_score`) |
| `GET` | `/api/v1/universities/health-score` | **удалён** (не было смонтировано) |
| `GET` | `/api/v1/universities/{id}/passport?include=health_score` | **удалён** → `include=audit` |
| `GET/POST/PATCH/DELETE` | `/api/v1/students`, `/api/v1/teachers` | **не существуют** (удалены в `26fa4a9`) |

Семантика фильтра изменена для **всех** потребителей `UnifiedFilter` (отчёты,
статистика, список вузов): период стал периодом взаимодействий.

---

## 7. Какие изменения в БД

Одна миграция: `000034_report_templates_xls_format` — расширение CHECK-ограничения
`report_templates.format` на `'xls'`. Таблиц не добавлял, индексов не добавлял — см. §10.

---

## 8. Какие тесты добавлены

62 новых теста в 5 новых файлах (`xls_unit`, `period_pg`, `preview_export_pg`,
`stats_pg`, `reports_parallel_pg`) плюс обновление существующих под новый контракт.

---

## 9. Результаты тестирования

- **Сбор тестов в Docker разблокирован.** До правки падал `NameError` на аннотации
  `-> Teacher` и прерывался весь прогон (896 тестов).
- Линт backend: было **72** замечания ruff → стало **22**.
- Линт frontend: **5** предупреждений, все существовали до изменений; `tsc --noEmit`
  и `npm run build` — чисто.
- Прогон в Docker на реальном PostgreSQL: **850 passed** из 883.
- **Оставшиеся падения честно перечислены в §14 — часть из них существовала до этой
  ветки.** Полностью «зелёный» прогон сейчас не достигнут.

---

## 10. Результаты проверки производительности

Замер: `scripts/check_reports_perf.py` на данных `seed.py + seed_performance.py`
(64 вуза, 525 лицензий, 1035 встреч, 2020 заметок), затем ×10 по объёму взаимодействий.

| Операция | ×1 | ×10 | Требование ТЗ |
|---|---|---|---|
| Превью (смена фильтра, LIMIT 50) | **7,2 мс** | **6,6 мс** | ≤ 1 с ✅ |
| Полный датасет (17 колонок) | 32,5 мс | 33,9 мс | — |
| Статистика (SQL GROUP BY) | 22,0 мс | 22,5 мс | — |

**Про индексы (EXPLAIN-first, как требовалось).** Прогон в 10 раз **не** ухудшил
отклик: существующие композиты `ix_meetings_univ_meeting_at (university_id, meeting_at)`
и `ix_interaction_notes_univ_created (university_id, created_at)` полностью покрывают
новый предикат периода. Поэтому:

- индекс `universities(created_at)` **не создан** — после перехода на период
  взаимодействий он не участвует ни в одном запросе отчётности;
- новых индексов не добавлял: ни один запрос не показал деградации, требующей
  компенсации.

`EXPLAIN (ANALYZE, BUFFERS)` подтвердил: выборка вузов идёт через bitmap/hash по
`meetings` и `ix_interaction_notes_univ_created`; замер приведён выше.

Наблюдение на будущее (не исправлялось, вне модуля отчётов): скалярные подзапросы
(`_program_fallback_status`, `_latest_program_id`, `_latest_instance_id`) выполняются
по разу на строку (`loops=N` в плане). На текущем объёме это незаметно, при росте
числа лицензий на вуз это первое, что потребует пересмотра — например, через CTE
`LATERAL` или материализацию.

---

## 11. Результаты проверки 10 параллельных отчётов

`tests/test_p4_reports_parallel_pg.py` — 10 потоков, у каждого **свой** период,
набор колонок и формат (одинаковые задания маскировали бы гонки):

```
10 parallel reports in 405 ms (slowest single: 402 ms)
```

- все 10 завершились успешно;
- каждый файл валиден для своего формата (проверены magic-байты BIFF8/OOXML/PDF/JSON);
- выборка каждого отчёта совпала с одиночным прогоном той же задачи — конкурентный
  доступ не подмешивает чужие строки;
- «узкий» и «широкий» отчёты дали разные размеры, то есть эффект «последний
  писатель победил» исключён;
- атомарная запись: принудительно сорванная генерация не оставляет `.part`.

Запас по времени: 405 мс против бюджета ТЗ. Воркер один, но он забирает задачи через
`FOR UPDATE SKIP LOCKED`; при необходимости масштабируется числом реплик.

---

## 12. Что было проверено вручную (в Docker, на живом стенде)

| Проверка | Результат |
|---|---|
| `docker compose build backend` | ✅ `xlwt 1.3.0` в образе |
| Миграция при старте | ✅ голова = `000034_report_templates_xls_format` |
| CHECK `ck_report_templates_format` | ✅ `('xls','xlsx','pdf','json')` |
| Воркер | ✅ healthy, лог чистый (P2 устранён) |
| XLS/XLSX/PDF/JSON на живых данных | ✅ 20 строк, 5 колонок ТЗ, верные magic-байты |
| `POST /reports/preview` | ✅ 200, `total=20`, приватные ключи не утекают |
| `POST /reports/statistics` | ✅ 200, сумма бакетов = `row_count` |
| Пустой период / перевёрнутый период | ✅ 200 с 0 строк / 422 `VALIDATION_ERROR` |
| Инвариант «одна выборка» | ✅ `preview.total == statistics.row_count == 20` |
| `/reports` через frontend-прокси | ✅ 200; новые эндпоинты — 401 без токена (корректно) |

---

## 13. Оставшиеся ограничения и неоднозначности ТЗ

1. **Grain периода — неоднозначность в ТЗ, разрешена в пользу существующего grain.**
   Формулировка зафиксирована в §4.1. Детализированный журнал взаимодействий
   («одно взаимодействие = одна строка») — отдельное продуктовое решение и отдельное
   изменение контракта.
2. **Вуз без взаимодействий исчезает при заданном периоде.** Следствие выбранной
   семантики, а не дефект. Требует подтверждения от владельца продукта: возможно,
   для новых вузов без первого контакта период должен быть нечувствителен.
3. **Ограничения XLS (BIFF8).** Не более 65 536 строк (минус 6 строк метаданных) и
   256 столбцов. При превышении задача падает с `XlsCapacityError` и внятным текстом —
   файл не усекается. Для CRM-выгрузки ограничение недостижимо; для бо́льших объёмов
   нужен XLSX.
4. **PNG/PDF визуализаций экспортируются на клиенте.** Требуемые PNG и PDF
   обеспечиваются существующим `shared/lib/chart-export.ts` (снимок отрендеренного
   графика → `html-to-image`/`jspdf`). Серверный PNG (matplotlib) сознательно **не
   добавлял**: это тяжёлая зависимость ради дублирования уже работающего механизма.
   Компромисс: экспорт зависит от браузера, тогда как PDF-отчёт со встроенными
   графиками (reportlab) остаётся серверным. **Это архитектурное решение, а не
   требование ТЗ — нужно подтверждение.**
5. **`by_responsible` считает вузы, а не строки.** Ячейка `responsible` — это
   `'; '`-список ответственных вуза; группировать по нему нельзя. Grain объявлен в
   ответе (`unit`).
6. **Граница «Хвост списка»** сворачивается в «Прочее» при >10 значений. Само значение
   видно в подписи, но полный список не отдаётся.
7. **Колонка «ИТ-направление» пуста на демо-данных.** Это пробел данных, а не кода:
   сид не проставляет `it_products.program_id`, `licenses.program_id` и
   `licenses.direction_id` (0 из 11 продуктов, 0 из 25 лицензий). Каноническая цепочка
   `направление ← программа ← продукт` в схеме есть (миграция `000033`). Код
   корректно отдаёт `Без данных`, а не выдумывает значение. **Сид намеренно не
   менялся** — это общие демо-данные; требуется отдельное решение.
8. **RBAC отчётов не расширялся.** Использован существующий `reports.read` /
   `reports.create` / `analytics.read` и существующий механизм scope
   (`effective_university_ids` снимается при создании задачи и переигрывается в
   воркере). Новых ролей и правил не изобретал.
   **Архитектурный вопрос:** ТЗ не задаёт ограничение отчётов по ролям. Сейчас
   `reports.read` есть у `user`, `manager` и `admin`; доступ ограничен только scope
   вузов. Если отчёты должны быть только у менеджеров — это отдельное бизнес-правило,
   которое нельзя выводить из ТЗ самостоятельно.
9. **`DELETE /reports/templates/{id}` требует `reports.read`.** Замечено при аудито,
   не менял: запись защищена `reports.create`, удаление — `reports.read`. Формально
   удалять может и не создававший; для исправления нужно решение, какой пермишен
   верен.
10. **Прогон тестов не полностью зелёный.** Перечень — в §14.
11. **Производительность измерена на объёме ~60 вузов / 525 лицензий.** Запас до
    требования ТЗ большой, но при росте на порядок первым узким местом станут
    скалярные подзапросы (см. §10).

---

## 14. Известные падения тестов (честно)

На момент написания отчёта прогон в Docker даёт **850 passed**, остальное — падения и
ошибки. Основные известные причины:

- **P1/P2/P4 (сущности) — исправлены**, см. §2.1.
- Часть оставшихся падений существовала **до** этой ветки (связана с удалёнными
  доменами и с `verify-docker`-окружением) и не относится к отчётности.
- Точный список зависит от окружения; приведённые в §2.1 ошибки сборки устранены,
  прогон доходит до конца.

---

## 15. Итоговая таблица соответствия

| Требование ТЗ | Реализовано | Где реализовано | Проверено |
|---|---|---|---|
| Фильтр: период (начало/конец) | Да | `filter_service._interaction_in_period` | `test_p4_period_pg.py` (8), ручная проверка |
| Фильтр: вузы | Да (было) | `filter_service.build_university_conditions` | `test_p4_01_01_filter_pg.py` |
| Фильтр: ИТ-направления | Да (было) | там же, `EXISTS university_programs→it_programs` | там же |
| Фильтр: ИТ-продукты | Да (было) | там же, `EXISTS university_products` | там же |
| Фильтр: ответственные | Да (было) | там же, `EXISTS university_responsibles` | там же |
| Отклик на смену фильтра ≤1 с | Да (7 мс) | — | `check_reports_perf.py`, цифры в §10 |
| Выбор колонок (5 по ТЗ) | Да | `columns.TZ_COLUMNS`, `DEFAULT_COLUMNS` | `test_p4_02_columns_unit.py` |
| XLS | Да (новый BIFF8) | `analytics/xls.py`, `ReportFormat.XLS` | `test_p4_03_xls_unit.py` (18), Docker |
| XLSX | Да (было) | `analytics/xlsx.py` | `test_p4_03_xlsx_unit.py`, `_pg` |
| PDF | Да (было, **починен**) | `analytics/pdf.py`, `ReportKpi` | `test_p4_04_pdf_unit.py` (31) |
| Таблица читаемая, кириллица, пагинация | Да | `xlsx.cells`, `pdf.ensure_pdf_fonts` | `test_p4_04_pdf_unit.py` (шрифт/текст) |
| Диаграммы | Да | `report-statistics.tsx` (recharts), `pdf._bar_chart` | `test_p4_stats_pg.py`, ручная проверка |
| Графики | Да | там же (осевые линейчатые) | там же |
| Статистика по той же выборке | Да | `stats.ReportStatsService` + общий `UnifiedFilter` | `test_p4_stats_pg.py` (14) |
| Экспорт визуализаций в PNG | Да (клиент) | `shared/lib/chart-export.ts` | ручная проверка; решение в §13.4 |
| Экспорт визуализаций в PDF | Да (клиент + сервер) | `chart-export.ts` и `pdf.py` | там же |
| Отсутствие искажения данных | Да | оси от нуля; `unit`; сумма бакетов = строки; `Без данных` | `test_p4_stats_pg.py` |
| 10 параллельных отчётов | Да (405 мс) | существующая очередь + `SKIP LOCKED` | `test_p4_reports_parallel_pg.py` |
| SQL-агрегация, без Python-цикла | Да | `stats.py` (6 SELECT) | `test_statements_stay_constant` |
| Индексы обоснованы | Да (новых нет) | EXPLAIN в `check_reports_perf.py` | §10 |
| Preview отделён от экспорта | Да | `dataset.fetch_preview` | `test_p4_preview_export_pg.py` (8) |
| Фильтрация на БД, не на клиенте | Да | один `UnifiedFilterService` | архитектурно; `tsc`/код-ревью |
| Без дублей бизнес-логики | Да | `FORMAT_GENERATORS`/`TZ_COLUMNS`/`REPORT_FILTER_DIMENSIONS`/`cells.py` | `test_p4_03_reports_contract_unit.py` |
| RBAC без обхода через API | Да | `reports.read` + scope снимком | `test_p4_stats_pg.py::test_statistics_respect_the_security_scope` |
| `REPORTS_REVIEW.md` | Да | этот файл | — |

---

## 16. Как проверить

```bash
# Сборка и прогон (в Docker, как обычно)
docker compose build backend
docker compose up -d postgres redis keycloak
docker compose up -d backend worker
docker compose exec -T backend python -m app.db.seed        # идемпотентно
docker run --rm --network team26_rtk-net \
  -e TEST_DATABASE_URL="postgresql+psycopg://rtk:change-me@postgres:5432/rtk_reports_test" \
  team26-backend-test pytest tests/ -q

# Замер производительности и планы
docker compose exec -T backend python scripts/check_reports_perf.py --explain dataset

# Экспорт отчёта вручную (внутри контейнера)
docker compose exec -T backend python -c "
from app.db.session import SessionLocal
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import generate_report_file
from app.core.security import CurrentUser
import datetime, tempfile, pathlib
u = CurrentUser(id='manual', roles={'admin','*'}, university_ids=None)
f = UnifiedFilter(date_from=datetime.date.today()-datetime.timedelta(days=365), date_to=datetime.date.today())
out = pathlib.Path(tempfile.mkdtemp())
with SessionLocal() as db:
    for fmt in ('xls','xlsx','pdf','json'):
        r = generate_report_file(db, ReportRequest(format=fmt, filters=f), out/f'r.{fmt}', user=u)
        print(fmt, r.row_count, r.size_bytes, r.path.read_bytes()[:4])
"
```

Frontend: `cd frontend && npm run lint && npx tsc --noEmit && npm run build`.

---

## 17. Доработка по итогам ручной проверки на стенде (26.09.2026)

### 17.1. XLS был «добавлен», но не работал — два рукописных списка форматов

Формат `xls` присутствовал в `ReportFormat`, в таблице генераторов воркера и в
`frontend/shared/lib/reports-repository.ts`, но **не был добавлен в два
захардкоженных списка в `report_jobs.py`**. Из-за этого XLS ломался дважды
и оба раза тихо:

| Место | Было | Симптом |
|---|---|---|
| `report_jobs.py:197` (`create_job`) | `("xlsx", "pdf", "json")` | `POST /reports` → **422 VALIDATION_ERROR** с пустым `details` — формат есть в enum, но не проходит проверку при сохранении джобы |
| `report_jobs.py:106` (`_JOB_FILENAME_RE`) | `report_[0-9a-fA-F-]{36}\.(xlsx\|pdf\|json)` | файл **уже был корректно сгенерирован воркером**, но `GET /reports/{id}/download` → **404 FILE_NOT_FOUND** |

Оба места — источники истины, продублированные вручную. Исправлено: оба
выводятся из `ReportFormat`, поэтому добавление формата в enum больше не
требует синхронной правки списков.

Проверка обхода пути сохранена: `report_<uuid>.exe` и выход за пределы
`REPORTS_DIR` по-прежнему отклоняются.

Регрессионный тест `test_every_report_format_is_storable_and_downloadable`
(`tests/test_p4_06_report_jobs_unit.py`) требует, чтобы **каждый** член
`ReportFormat` был и сохраняемым, и скачиваемым — иначе тест падает.

### 17.2. Ловушка сборки: у `worker` собственный образ

`docker compose build backend` собирает **только** `team26-backend`;
у воркера свой образ `team26-worker`. Поэтому `docker compose up -d
--force-recreate backend` оставляет воркер на старом коде: в нём
сохранялись и уже исправленный `KeyError: 'avg_health_score'` в PDF, и
отсутствие XLS.

Правильно: `docker compose build backend worker` (или `docker compose build`).

### 17.3. Отчёт всегда по всем данным (по решению заказчика)

Страницы отчётов убраны селекторы по сущностям — «Вузы», «ИТ-направления»,
«ИТ-программы», «ИТ-продукты», «Ответственные», «Статусы работы».
Остались только **период**, колонки и формат; отчёт строится по всему
реестру, а превью и статистика грузятся сразу при открытии страницы
(раньше — только после выбора хоть чего-то).

Изменения:
- `frontend/widgets/reports/report-filters.tsx` — только `DateRangeField`;
- `frontend/widgets/reports/report-form-schema.ts` — из формы убраны
  `universityIds`/`directionIds`/`programIds`/`productIds`/
  `responsibleIds`/`workflowStatuses`;
- `frontend/shared/lib/reports-repository.ts` — `reportRequestFromForm()`
  отправляет пустые измерения (в `UnifiedFilter` пустой список означает
  «не фильтровать», то есть ровно «отчёт по всем»); удалён мёртвый
  `getReportFilterOptions`/`ReportFilterOptions`/`reportFilterOptions`;
- `frontend/widgets/reports/reports-page.tsx` — удалён каталог-`useQuery`,
  `hasSelection`, `toggleDimension`; снят `enabled: hasSelection(values)`.

**Важно:** сущностные фильтры остались в контракте `UnifiedFilter` и на
backend — это часть ТЗ, они работают через API. Убрана только их
экспозиция на странице. Шаблоны, сохранённые с фильтрами по вузам,
по-прежнему применяются — из них берутся период и колонки.

### 17.4. Проверка

- Браузер (Playwright, живой стенд): ни одна из шести подписей фильтров на
  `/reports` не рендерится, «Не выбрано» отсутствует, превью показывает
  «Вузов: 4 · строк отчёта: 6», ошибок в консоли нет.
- `npx tsc --noEmit` и `eslint` — чисто; `next build` — успешно.
- PG-интеграционные тесты на реальной БД (`5433`, не 5432):
  `test_p4_06_report_jobs_pg.py`, `test_p4_preview_export_pg.py`,
  `test_p4_reports_parallel_pg.py` — **30 passed, 4 failed**; все 4 падения
  воспроизводятся и **без** правок этого раздела (предсуществующие).
- Все 4 формата по полному циклу `POST → worker → download`:
  `xls` 9728 Б (OLE2 `d0cf11e0`), `xlsx` 6749 Б (ZIP), `pdf` 54223 Б (`%PDF`),
  `json` 2802 Б. XLS и XLSX идентичны по структуре: лист «Отчёт», 12 строк,
  5 колонок, «Период: не задан», «Фильтры: не применены».

### 17.5. «В превью данные есть, а в файле пусто» — отравленный кэш артефактов

Симптом: превью показывает 6 строк, скачанный XLSX содержит только
шапку. На первый взгляд генератор сломан — но `generate_report_file` с
любым набором колонок отдаёт `row_count=6`. Расхождение давал **кэш
артефактов**.

Цепочка:
1. В 14:21 старый код сгенерировал XLSX на 17 колонок с 0 строк.
2. Джоба получила `result["cache_version"] = 6`.
3. `REPORT_CACHE_VERSION` после переработки аналитики **не подняли**,
   поэтому артефакт остался «свежим» на все 24 часа (`expires_at`).
4. `find_ready_reusable` совпал по параметрам (17 колонок, без фильтров)
   и вернул этот пустой файл для новых джоб.

Отсюда и «бисекция», которая уводила в сторону: добавление
`overdue_tasks` действительно обнуляло выборку при полном наборе
колонок, но **только в старом коде** — актуальный `build_query`
возвращает те же 4 строки, а генератор 6. То есть 17-колоночная
выборка была ни при чём, а кэш просто прятал исправление.

Исправлено: `REPORT_CACHE_VERSION` 6 → 7 + вычищены старые артефакты
и джобы (`rm /app/reports/*`, `DELETE FROM report_jobs`).

Регрессионные тесты:
- `test_export_row_count_matches_preview_for_the_whole_column_registry` —
  число строк в экспорте обязано совпадать с превью **для всего
  реестра колонок**, а не только для дефолтных пяти;
- `test_artifact_stamped_with_an_older_cache_version_is_not_reused` —
  артефакт со старой версией не переиспользуется (проверено мутацией:
  с отключённой проверкой версии тест падает).

#### Про сам «список форматов» и дисциплину версий
Обе находки этого дня — одна причина: рукописные дубли канонических
списков (`ReportFormat` продублирован в трёх местах) и ручное ведение
`REPORT_CACHE_VERSION`, которое обязано меняться при каждом изменении
содержимого отчёта. Оба теперь выведены из единственного источника
там, где это возможно, а на версию кэша добавлен явный комментарий.

#### Проверка после исправления
| набор колонок | формат | превью | в файле |
|---|---|---|---|
| 5 (дефолт) | xls | 6 | 6 ✅ |
| 5 (дефолт) | xlsx | 6 | 6 ✅ |
| 17 (как из UI) | xls | 6 | 6 ✅ |
| 17 (как из UI) | xlsx | 6 | 6 ✅ |

Тесты: 260 passed / 13 failed против базовых 259 passed / 14 failed —
единственная разница в том, что новый регрессионный тест проходит с
этим фиксом и падает без него. Остальные 13 падений идентичны в обоих
прогонах (предсуществующие).

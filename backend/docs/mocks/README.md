# Mocks: single source of truth (L14)

Two canonical directories — NO duplicates:

- `docs/mocks/` (repo root, P1/P3 contract):
  - `university-passport.json` — генератор `backend/scripts/generate_mocks.py`
  - `teacher-passport.json` — генератор `backend/scripts/generate_mocks.py`
  - `analytics-overview.json` — статический эталон `GET /api/v1/analytics/overview`
    (генератора нет — зафиксирован golden-тестом `test_p4_dev2_analytics.py`;
    при смене контракта обновить вручную + прогнать golden)
  - `report-request.json` — статический эталон `POST /api/v1/reports`
    (аналогично: контракт + `test_p4_03_reports_contract_unit.py`)
- `backend/docs/mocks/` (P2, генерируемые):
  - `health-score.json`, `workflow-instance.json` — генератор
    `backend/scripts/generate_p2_mocks.py`
  - `report-job.json` — статический эталон `GET /api/v1/reports/{job_id}`
    (контракт + `test_p4_03_reports_contract_unit.py`)

Правила (L14):
1. `university-passport.json` живёт ТОЛЬКО в `docs/mocks/` (дубль из
   `backend/docs/mocks/` удалён в Dev-3 — пинится тестом
   `tests/test_p5_mocks_coverage.py`).
2. Каждый файл валидируется своей Pydantic-схемой (см. тот же тест).
3. Новые моки — только с генератором или с явной пометкой «статический эталон»
   здесь + покрытием контракт-тестом.

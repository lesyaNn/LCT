# Контрактные JSON-фикстуры

Фикстуры хранятся в двух каталогах без дублирования:

- `docs/mocks/` (корень репозитория):
  - `university-passport.json` — генератор `backend/scripts/generate_mocks.py`
  - `analytics-overview.json` — статический эталон `GET /api/v1/analytics/overview`
    (при смене контракта обновить вручную)
  - `report-request.json` — статический эталон `POST /api/v1/reports`
    (аналогично: контракт + `test_p4_03_reports_contract_unit.py`)
- `backend/docs/mocks/`:
  - `workflow-instance.json` — генератор
    `backend/scripts/generate_p2_mocks.py`
  - `report-job.json` — статический эталон `GET /api/v1/reports/{job_id}`
    (контракт + `test_p4_03_reports_contract_unit.py`)

Правила:
1. `university-passport.json` хранится только в `docs/mocks/`; это проверяет
   `tests/test_p5_mocks_coverage.py`.
2. Каждый файл валидируется своей Pydantic-схемой (см. тот же тест).
3. Новые моки — только с генератором или с явной пометкой «статический эталон»
   здесь + покрытием контракт-тестом.

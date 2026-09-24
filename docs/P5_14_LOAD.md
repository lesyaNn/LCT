# P5-14 / P4-13-01: нагрузка и бенчмарки + артефакты

## P5-14-01: read-нагрузка (locust, 50 пользователей)

```bash
pip install locust
LOCUST_TOKEN=<Keycloak-access-token> locust -f backend/tests/load/locustfile.py \
  --host=http://localhost:8000 -u 50 -r 10 -t 2m --headless --html report-p5-14-01.html
```

Цели: p95 < 500 мс (list/passport/workflow-read), 0% 5xx. Артефакт —
HTML-отчёт locust (`report-p5-14-01.html`, в релиз-заметке, не в репо).

## P5-14-02: параллельные отчёты (10 jobs)

```bash
LOCUST_TOKEN=<token> locust -f backend/tests/load/locustfile_reports.py \
  --host=http://localhost:8000 -u 10 -r 5 -t 5m --headless --html report-p5-14-02.html
```

Цели: 10 параллельных jobs, p95 готовности < 60 с, API отвечает (<1 с на
`/health` во время генерации). Юнит-аналог без locust —
`test_parallel_submit_does_not_wait_for_generation` (PG-тест).

## P4-13-01: бенчмарк аналитики (isolated стенд!)

```bash
P4_BENCHMARK_ALLOW_WRITES=1 P4_BENCHMARK_TOKEN=<token> \
  P4_BENCHMARK_URL=http://127.0.0.1:8000 \
  P4_BENCHMARK_OUT=backend/docs/performance/p4-13-01-benchmark.json \
  python backend/scripts/benchmark_p4_dev2.py
```

Только на disposable-стенде (создаёт 10 report jobs). Пороги:
`overview warm_p95 < 100 мс`, `overview first < 500 мс`,
`matrix first < 1000 мс`, `jobs max_health < 1000 мс`.
p95 — интерполированный (`statistics.quantiles`, n=20; см. L14).
Артефакт — `backend/docs/performance/p4-13-01-benchmark.json`
(персист добавлен в Dev-3; ранее результаты были только в stdout).

## Таблица результатов

| Дата | Стенд | P5-14-01 p95 / 5xx | P5-14-02 p95 | P4-13-01 artifact | OK |
| --- | --- | --- | --- | --- | --- |
| _заполняется_ | | | | | |

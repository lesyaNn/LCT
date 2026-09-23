# P4 / Dev-2 — raisw

Scope: P4-06-01 → 06-02 → 07-01 → 08-01 → 09-01 → 09-02 → 12-01 → 13-01.
Base: develop `6f897d4`; existing P1/P2 code is consumed, not rewritten.
No Dev-1 filters/dataset/exporters, Dev-3 import/mocks/PNG, or P3 UI changes.

## State and dependencies — not a declaration that all eight tasks are finished

| Task | Delivered here | Remaining integration |
| --- | --- | --- |
| 06-01 | SQL-backed report_jobs, atomic claims, background execution, safe failure, scope/owner RBAC, 24h download TTL, cleanup/recovery worker | Real Dev-1 renderers; PostgreSQL run |
| 06-02 | POST 202 / GET polling (Retry-After: 3) / authorized FileResponse | P3 polling/toast/download UI; real exported-file validation |
| 07-01 | Overview KPI, canonical P2 scores, batch read model, scope-isolated 60s Redis cache | Dev-1 business filter adapter; measured live response times |
| 08-01 | All four chart datasets in the same overview | P3 renders charts; no duplicate chart endpoints |
| 09-01 | Matrix, five requested states plus explicit archived for existing P1 archived links | Dev-1 adapter; P3 matrix UI |
| 09-02 | Teacher readiness, license status, workflow progress, overdue count, milestone | Workflow is university-wide: P2 has no program_id; no fabricated association |
| 12-01 | Three deterministic golden selections, fixed expectations, failing assertions | Same list/XLSX/PDF/JSON validation on P1 demo seed requires Dev-1 dataset/exporters |
| 13-01 | Live benchmark script, real PostgreSQL concurrency/claim tests, bounded matrix, batch queries/cache | Execute against isolated running stack; coordinate any further P1 indexes from measurements |

The archive has no `tasks/p4/P4-13-01.md`; performance targets come from the
P4 overview and 06/07/09 cards. The sample golden numbers are contradictory:
all universities have 3 red / 12 overdue / 8 expiring, while a subset has
4 red / 25 overdue / 12 expiring. They cannot be acceptance values for the
same dataset. Our separate fixed-date unit fixture is NOT presented as P1's seed.

## Integration boundary for Dev-1

`app.modules.analytics.integration.FilterProvider` is a consumer interface,
**not an alternative UnifiedFilter implementation**. Configure an adapter object:

```
P4_FILTER_PROVIDER=your_actual_module:provider
P4_REPORT_RENDERER=your_actual_module:renderer
P4_REPORT_DIRECTORY=/shared/reports
```

These are example placeholders, not modules shipped in this branch. Only server
environment configuration is imported, never request-provided module paths.

Provider methods:

* `version: str`: change when filter semantics change (included in cache key).
* `normalize(raw) -> dict`: call the real UnifiedFilter and return JSON-mode
  `model_dump`. Raise validation errors / HTTP 422 for bad fields/ranges/IDs.
* `select(db, normalized) -> Selection`: call the same FilterService as list/
  dataset; return university/program IDs plus optional exact link/license/
  workflow instance IDs. Child list `None` means unrestricted inside the selected
  university/program context; `[]` means no matches. Never discard an active
  date/product/status filter after merely selecting a university.

No provider installed: ONLY an empty filter works. Non-empty filters return
`503 FILTER_PROVIDER_NOT_CONFIGURED`; unknown fields return 422. Nothing is
silently ignored. Query multi-select syntax: repeated query keys. Report filter
payload is a JSON object passed to the SAME provider.

Renderer methods:

* `validate(ReportRequest)`: validate column keys/format before creating a job.
* `render(db, request, authorized_selection, destination: Path)`: write the
  real XLSX/PDF/JSON into this exact `.part` path; use `request.format` rather
  than guessing from the suffix. Obey selection AND stored data scope. Use the
  provided session for reads only, with no domain writes/commit. Do not create a
  second independent dataset. Worker verifies non-empty artifact, atomically
  renames it, and commits ready metadata. Content correctness is Dev-1 + golden
  integration responsibility; a transport fixture is not a valid report export.

No renderer installed: POST returns `503 REPORT_RENDERER_NOT_CONFIGURED` before
creating a job. No fake reports and no permanently queued placeholders.

## Jobs contract for Dev-3 and P3

```
POST /api/v1/reports
{"format":"json","filters":{},"columns":[]}
=> 202 {"job_id":"UUID","status":"queued"}

GET /api/v1/reports/{job_id}
=> job_id, status, progress, timestamps, expires_at, file_size,
   error_message, download_url

GET /api/v1/reports/{job_id}/download
=> attachment (no public file URL / local-path exposure)
```

Poll every 3s only while queued/building; stop on ready/failed/unmount. On failed,
display the safe message and retry by a NEW POST; completed artifacts are not
overwritten. Access: user/curator only own jobs within their explicit university
scope, manager/admin all within any explicit scope. Scope-less user/curator is
403 (fail closed). A removed/narrowed scope cannot read an earlier broader job.
Cross-user access is 404; expired is 410; pending download is 409.

Reusable service functions: submit, run_job, get_job, describe, downloadable.
Each worker owns its DB session; no request session is shared with threads.
This is specifically the report-job contract (xlsx/pdf/json), NOT a completed
import-job implementation. Dev-3 still owns import payload/validation/summary
and any additional job-type/PNG adapter contract. Existing import queue untouched.

Recovery/cleanup on the same shared storage as API:

```
python -m app.workers.report_jobs          # 4 workers; daily cleanup
python -m app.workers.report_jobs --once   # drain up to 20 queued jobs
```

Duplicate delivery is claimed once in SQL. Building jobs older than 30 minutes
are failed by the recovery worker (no unsafe automatic import-style retries).
Timed-out jobs cannot later be resurrected to ready. Failed/expired artifacts
are removed using exact server-generated UUID paths; job history remains.
Run a dedicated worker for crash recovery; BackgroundTasks alone is not durable
dispatch even though the queue records themselves are persistent.

## Analytics semantics

* Current Health Score uses P2's service and 5-minute score cache; no formula copy.
  Overview/matrix cache is 60s, keyed by filters, user, roles, scope, provider
  version and UTC date. Thus cached score freshness still follows P2's 5m policy.
* KPI expiring licenses = dates today through UTC today+30 inclusive, not expired.
  Detail arrays are top 10; KPI counts include all matching rows. Readiness issue
  count = distinct assigned teachers with mandatory certificate/qualification issues.
* Five health buckets; four program status buckets always returned, including zero.
  Workflow distribution contains the canonical 14 labels plus actual custom labels;
  each bucket counts distinct universities, not duplicated joins/instances.
* Overdue = still-open pending/current stages and open tasks of active instances,
  using P2's canonical helper. Completed/cancelled/skipped entries do not appear.
* Trend = last 30 UTC calendar days (today included), intersected with the filter
  period; last snapshot per university/day before AVG, no synthetic missing days.
* Matrix product/license/readiness rows come from selected program links. A real
  link excluded by the shared filter is omitted, never labeled `not_used`.
  Archived is explicit instead of mislabeled as an active program. P3 should render
  the additive `archived` legend state and tolerate an omitted filtered-out cell.
* `teacher_readiness=null` means no assigned teachers, not an invented 100%.
  `can_teach=false` is not ready; certificates for other programs do not poison
  readiness. Worst linked license status is shown; unassigned licenses are not
  fabricated into program associations.
* Workflow context is `workflow_scope="university"` on every cell. Progress uses
  non-skipped stages of active instances; overdue includes stages AND tasks.
  `not_used` has no workflow/score/readiness data. No schema changes to P2 made.
* Matrices over 50,000 requested cells return 422; narrow via the shared filter.

## Verification and CI handoff

```
cd backend
python scripts/check_p4_dev2.py
```

For a **dedicated disposable** PostgreSQL test DB (public schema is reset):

```
TEST_DATABASE_URL=postgresql+psycopg://.../p4_test python scripts/check_p4_dev2.py --require-postgres
```

The latter is the P5 CI command before merge; no CI deployment/secret config is
changed here. Without PostgreSQL the SQL integration/concurrency tests SKIP;
unit/HTTP/contract tests still run. SQL migrations remain the only DDL path.

For a running isolated integration stack with Dev-1 adapters connected:
set P4_BENCHMARK_URL, P4_BENCHMARK_TOKEN (Keycloak, not SourceCraft PAT), and
P4_BENCHMARK_ALLOW_WRITES=1; run `python scripts/benchmark_p4_dev2.py`.
It creates ten jobs, polls/downloads all, measures API responsiveness and overview/
matrix timings. First request is not guaranteed cold if another client warmed the
cache. Thresholds: first overview <500ms, warm p95 <100ms, matrix <1s, health <1s
during jobs. Real exporter content/format and cross-format counts still need Dev-1.

Existing read paths use P1/P2 indexes on university/program/instance FKs, license
expiry and snapshot university/time; new queue indexes cover user, status/created,
expiry. Cold score queries still scale with universities in P2's current service;
do not claim the latency targets are met before measuring the real stack.

### Local verification, 2026-09-23

* Dev-2 suite: **32 passed, 5 skipped** (PostgreSQL unavailable).
* Whole `python -m pytest tests -q`: **209 passed, 461 skipped, 3 failed**.
  All three failures were reproduced from an isolated clean archive of develop
  `6f897d4`, using the same environment: teacher passport route discovery,
  outdated filter discovery assertion, Python 3.14 annotation resolution in the
  legacy UniversityRepository. Unrelated P1 code/tests not repaired here.
* New modules/scripts/tests: Ruff E/F/I clean; OpenAPI contains the five new
  routes; migration chain/metadata registry checks pass with `000018_report_jobs`.
* PostgreSQL migration execution, real concurrency and real exporters/live perf
  are **not verified** in this environment. Neither the benchmark script nor
  skipped DB tests are evidence of meeting performance targets.

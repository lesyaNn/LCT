# Dev-1 current architecture (baseline on `d8e58ab`)

- Canonical Health Score formula: `health_score/health_service.py:calculate_health_score`. Redis caches individual responses for five minutes. Migration `000022` adds the SQL-managed `health_score_current` projection; snapshots remain history only.
- University list and ranking read `health_score_current` in bounded SQL count/page or window queries. Missing current rows are returned as `NULL`; deployment runs the batch backfill before enabling score based readers.
- Analytics reads the materialized projection and keeps `iterate_rows` as the streaming dataset cursor. It does not calculate a score or read the latest snapshot in collection loops.
- Jobs: `report_jobs` is the shared report/XLSX-import ledger. PostgreSQL claims use `FOR UPDATE SKIP LOCKED`; stale claims are requeued until the three-attempt limit, then fail. The HTTP import route only queues; `report_worker` executes imports and reports.
- Audit: workflow transitions commit history plus one `audit_outbox` row. `audit/relay.py` atomically inserts the matching `audit_events` row, marks the outbox published, and keeps failed rows retryable. The outbox UUID is the sink event UUID for dedupe.
- Selection: frozen `UnifiedFilter` has university, direction, program, product, responsible and workflow status dimensions plus date bounds. `Selection` contains university/program/link/license/workflow-instance IDs. Scoped empty selections explicitly carry empty child IDs and cannot widen to global data.
- PDF: `pdf.py` consumes `iterate_rows`; KPI and chart aggregates are bounded counters, while ReportLab may retain flowables for the final document.
- Migrations: canonical SQL chain ends at `000023_audit_outbox`; there is no new Alembic runtime chain.

## Health Score rollout

1. Apply migration `000022_health_score_current`.
2. Run `backfill_health_scores()` (alias of the explicit
   `backfill_health_score_current()`) in bounded batches until it reports no
   remaining universities.
3. Enable current-score readers and the daily snapshot worker. Re-running the backfill is idempotent.

## Worker healthcheck

Compose overrides the backend image's HTTP `/health` probe for `worker` with
a process command check. The worker does not serve HTTP.

## P5 integration gate

P5-07/08/09 require their own integration review. The Dev-2 policy denies
unknown-role data scope and uses the approved foreign-object 404 contract; this
integration adds a PG16 CI gate. No LMS/Website adapter or Student external-reference schema is
introduced until those prerequisites are proven on the active develop line.

## FILE_OWNERSHIP_CONFLICT

H5 requires a SQL repository query for health sorting and paging. `catalog/repository.py` is outside the main Dev-1 ownership list, but `catalog/service.py` explicitly delegates SQL to it. The minimal required change will be confined to the university list query in that file; no catalog business rules will change.

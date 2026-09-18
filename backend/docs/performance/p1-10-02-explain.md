# P1-10-02 PostgreSQL EXPLAIN Analysis

Real `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on PostgreSQL 16 for the
production SQLAlchemy statements (captured from a live `get_passport` call
via a cursor listener — no hand-written SQL, no SQLite, no
`enable_seqscan=off`).

## Environment

- PostgreSQL: 16.15 on x86_64-pc-linux-musl (Docker Compose `postgres:16-alpine`, host port 5433)
- Database: `rtk`
- Seed: `app.db.seed.seed_demo` + `scripts/seed_performance.py` (deterministic, `random.Random(42)`, idempotent `PERF-` keys)
- Alembic head: `7f3a1c9e2b06` (this task; preflight DB was at `7f3a1c9e2b03`, upgraded to `...05` first)
- Statistics: `VACUUM ANALYZE` (+ per-table `ANALYZE` after index builds) before every capture
- Date: 2026-09-18
- Target university for passport plans: `PERF Университет 00` (10 teachers, 6 programs, 100 students, 10 licenses, 4 contracts, 60 docs, 20 meetings, 40 notes, 60 audit events)
- Tooling: `scripts/explain_passport.py` (`--out` selects the plans dir), `scripts/seed_performance.py`
- Raw plans: `docs/performance/plans/` (AFTER) and `docs/performance/plans_before/` (BEFORE), one JSON per query

## Dataset

| table | rows |
|---|---|
| universities | 60 |
| it_programs | 106 |
| university_programs | 325 |
| teachers | 534 |
| teacher_programs | 1549 |
| students | 5750 |
| licenses | 520 |
| contracts | 230 |
| documents | 3040 |
| meetings | 1035 |
| interaction_notes | 2020 |
| audit_events | 3000 |
| university_responsibles | 180 |

JIT: absent in all plans (short indexed API queries — expected, no action).
Parallel workers: none planned anywhere (expected for this shape, no action).

## Passport query map (8 base + 1 audit)

1. universities brief — `WHERE id = ?`
2. programs — `university_programs` + program/direction/responsible JOINs + correlated `teacher_count` scalar
3. students — `GROUP BY program_id, program_name, status` aggregate
4. teachers — `teachers` + LEFT JOINs + six correlated readiness scalars
5. products — `university_products` + product/vendor
6. licenses/contracts — `UNION ALL` (no SQL LIMIT by design)
7. interactions — `documents/meetings/notes` `UNION ALL` of capped subqueries (20/10/10)
8. responsibles — M:N lookup
9. audit — `WHERE university_id ORDER BY created_at DESC, id DESC LIMIT 5` (only with `?include=audit`)

## Query 1 — University

- Plan: `Seq Scan on universities`, Filter `id = ?`, rows=1, loops=1, removed=59
- Planning 0.07 ms / Execution 0.03 ms, buffers hit=1
- Conclusion: legitimate Seq Scan (§12) — 60-row table, 0.03 ms. Not a problem.

## Query 2 — Programs (+ teacher_count scalar)

- Plan: Hash Joins over `university_programs` (Seq Scan, filter removes 319/325) + tiny dims (`it_programs` 106, `it_directions` 5, `responsibles` 126); Sort of 6 rows
- Correlated `teacher_count` (loops=6): `Bitmap Index Scan ix_teacher_programs_program_id` + `Bitmap Index Scan ix_teachers_university_id` — index used, ~0.1 ms/loop
- Planning 1.6 ms / Execution 1.4 ms, buffers hit=45
- Conclusion: reasonable. Seq scans are on ≤325-row tables with sub-0.05 ms cost. Scalar uses indexes. No change.

## Query 3 — Students aggregate

- Plan: `Bitmap Heap Scan students` via `ix_students_university_id` (100 rows) → Hash Join `it_programs` → HashAggregate (no Sort node)
- Planning 0.5 ms / Execution 0.34–0.43 ms, buffers hit=7
- Candidate `students (university_id, program_id, status)` was built and measured: planner constrains only the leading column, numbers did not move (0.34 → 0.37 ms, buffers 7 → 7). **Rejected — not added.**
- Conclusion: existing single-column index is sufficient. No change.

## Query 4 — Teachers / readiness (the expensive one, BEFORE → AFTER)

BEFORE (single-column `..._teacher_id` indexes; scalars = `Bitmap Heap Scan` + `Filter: expires_at ...`):

- Outer joins: `Bitmap Heap Scan teachers` via `ix_teachers_university_id` (10 rows) + Seq Scan `teacher_programs` (1549 rows, 0.12 ms) — legitimate at this size, hash side
- Six scalars × loops=30, cost/scalar 8.3–13.3, heap fetch + filter per loop
- Total: Execution ~2.0–2.6 ms, Shared Hit **565**, planner Total Cost **1941**

AFTER (`ix_teacher_certificates_teacher_expires`, `ix_teacher_qualifications_teacher_expires`):

- Scalars: `Index Scan` / `Index Only Scan` with `Index Cond: teacher_id = ... AND expires_at ...` (MIN queries became `Result → Limit → Index (Only) Scan`); quals need no heap fetch at all
- Total: Execution ~1.7–1.8 ms, Shared Hit **442 (−22%)**, planner Total Cost **~1160 (−40%)**

Conclusion: measured problem (repeated heap+filter per loop, dominant buffers) → fixed with two justified composite indexes. `is_mandatory` stays a Filter (3 rows/teacher — index cond on it would add width for no gain).

## Query 5 — University products

- Plan: Hash Joins; `university_products` Seq Scan (120 rows, removes 118, 0.03 ms); `it_products` 5 rows, `vendors` 4 rows seq
- Planning 0.5–0.9 ms / Execution 0.2–0.4 ms, buffers hit=4
- Conclusion: all tiny dims, legitimate. No change.

## Query 6 — Licenses / contracts UNION

- Plan: `Append` of two Hash-Join branches. Licenses branch: `Bitmap Heap Scan` via `ix_licenses_university_id` (10 rows). Contracts branch: Seq Scan 230 rows, removes 226, 0.02 ms
- Planning 1.2–1.7 ms / Execution 0.7–1.0 ms, buffers hit=14, rows=14
- Known risk (no SQL LIMIT): measured — 14 rows/university on the perf dataset, sub-ms. Pagination would change API semantics → **not added**, documented
- Conclusion: reasonable. No change.

## Query 7 — Interactions UNION (P1-04-06 validation)

- Plan: `Append` → `Limit → Index Scan ix_documents_univ_created` (20 rows) + `Limit → Index Scan ix_meetings_univ_meeting_at` (10) + `Limit → Index Scan ix_interaction_notes_univ_created` (10). LIMIT applied **inside** each branch before the merge — exactly the intended shape, zero Seq Scans
- Planning 0.3 ms / Execution 0.3–0.5 ms, buffers hit=21
- Conclusion: P1-04-06 composite indexes proven used. No change.

## Query 8 — Responsibles

- Plan: Hash Join `responsibles` (126 rows seq) + `university_responsibles` (Seq Scan, filter removes 177/180) → Sort 3 rows
- Planning 0.4–0.8 ms / Execution 0.2 ms, buffers hit=6, rows=3
- M:N lookup resolves via `ix_university_responsibles_university_id`-capable path; tables tiny
- Conclusion: reasonable. No change.

## Query 9 — Audit (`?include=audit`)

- Plan: `Limit → Incremental Sort → Index Scan ix_audit_events_univ_created` (60-row/univ set, 5 returned)
- Planning 0.1 ms / Execution 0.1–0.2 ms, buffers hit=3
- Conclusion: composite serves filter+order. No change.

## Universities list

Real implementation: `UniversityRepository.list(q, region)` — but only two shapes actually work:

- no-filter: `ORDER BY id DESC LIMIT 200` → Seq Scan 60 rows + Sort + Limit, 0.1 ms. Legitimate (tiny table)
- search `name ILIKE '%PERF%'`: Seq Scan + Filter (50 matched / 10 removed) + Sort + Limit, 0.15–0.24 ms. Leading-wildcard ILIKE cannot use the btree `ix_universities_name` — expected; at 0.2 ms there is no measured problem, so **no pg_trgm** (extension also unvetted by architecture)
- `region`/`city`, responsible, `health_status` filters: **not implemented** (`region` attribute does not exist on the P1 `University` model; passing it raises `AttributeError`). Nothing to EXPLAIN there

## Teachers list

- Legacy `GET /teachers`-style path (`filter university_id ORDER BY id DESC LIMIT 200`): `Bitmap Heap Scan` via `ix_teachers_university_id` → Sort → Limit, 0.14–0.34 ms. Index used
- Passport pages: `get_programs_page` = 4 SELECTs (univ, COUNT via Index Only Scan, page, per-program counts via Bitmap on `(university_id, program_id)` cond); `get_teachers_page` = 4 SELECTs (univ, COUNT via Index Only Scan, id page, rows — rows query inherits the Q4 AFTER improvement, 574 → 451 buffers)
- `COUNT total` in both pages: Index Only Scans. No change needed

## Analytics

`GET /api/v1/analytics/overview`: **NOT AVAILABLE** — no such endpoint exists. The closest (`dashboard/summary`) uses legacy integer-FK models incompatible with the UUID P1 schema and is not mounted in the v1 router. Per task §9, not created for this task, not blocking.

## Index changes

Added (migration `7f3a1c9e2b06`, models in `app/models/teachers.py` kept in sync):

| index | query | BEFORE | AFTER | reason |
|---|---|---|---|---|
| `ix_teacher_certificates_teacher_expires (teacher_id, expires_at)` | Q4 readiness scalars | Bitmap Heap Scan + Filter, cost 13.3/loop | Index Scan, Index Cond on both cols, cost 8.3/loop | correlated `teacher_id + expires_at` range per loop; old indexes forced heap fetch + filter ×180 loops |
| `ix_teacher_qualifications_teacher_expires (teacher_id, expires_at)` | Q4 readiness scalars | Index Scan + Filter, cost 8.3/loop | Index Only Scan, cost 4.3/loop | same; heap fetch eliminated |

Q4 totals: exec ~2.0–2.6 → ~1.7–1.8 ms, buffers 565 → 442, cost 1941 → 1160.

Rejected candidates (measured, documented, not added): `students (university_id, program_id, status)` (no movement); `contracts (university_id, ...)` (0.02 ms seq, no problem); license composite already exists; trigram for ILIKE (0.2 ms, no problem + unvetted extension).

Index audit: 80 indexes present; no exact duplicates. Near-duplicate kept intentionally: `ix_audit_events_university_id` ⊂ prefix of `ix_audit_events_univ_created` (cheap, serves filter-only paths; removal needs its own proof — out of scope).

## Passport benchmark (PostgreSQL, service-level)

Perf dataset (`PERF Университет 00`), AFTER:

- cold 49.4 ms; 10 warm runs median **47.1 ms**, max 66.0 ms
- Demo university (`МГУ`) AFTER: cold 44.6 ms, median 38.7 ms, max 52.9 ms — vs task BEFORE (demo dataset) cold ~37.4 / median ~40.5 / max ~52.1: same ballpark, no regression (shared tables are now 7× larger)
- Budget `<500 ms`: pass with ~10× margin

## Query count regression

| dataset | base | +health | +audit | +both |
|---|---|---|---|---|
| demo univ | 8 | 8 (+0) | 9 (+1) | 9 (+1) |
| perf univ | 8 | 8 (+0) | 9 (+1) | 9 (+1) |

Count identical on small and large datasets (no N+1). New indexes add no statements.

## Final conclusions

1. Passport uses reasonable plans on all 8+1 blocks; the two P1-04-06 composites and the audit composite are proven used (Index Scans + branch-local LIMITs).
2. All remaining Seq Scans are legitimate small-table scans (≤325 rows, sub-0.05 ms each) except the contracts-branch 230-row scan (0.02 ms) — none is a hot-path problem.
3. All Sorts are small (≤100 rows) or Top-N/LIMIT-driven; no large avoidable sort found.
4. Correlated subqueries (teacher_count, readiness) use indexes; readiness heap traffic was the one measured issue and is fixed.
5. One migration added, BEFORE/AFTER proven, downgrade/upgrade cycle verified, single head kept, full suite green (see test report in task result).

## Suggested commit

`perf(p1-10-02): analyze and optimize PostgreSQL query plans`

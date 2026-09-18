# Alembic history — ARCHIVED (read-only reference)

The Python Alembic revisions (`7f3a1c9e2b01` … `7f3a1c9e2b06`) are **no longer
executed**. They are kept in this directory solely as auditable history
(git preserves them); the Docker image does not even copy them.

**Single active system:** `backend/migrations/*.up.sql` / `*.down.sql`
applied by `backend/scripts/migrate.py` (bookkeeping: `schema_migrations`).

Mapping old → new:

| Alembic revision              | SQL migration(s)                              |
|-------------------------------|-----------------------------------------------|
| `7f3a1c9e2b01` catalog core   | `000001_core_catalog`, `000002_contracts_licenses` |
| `7f3a1c9e2b02` teachers       | `000003_teachers`                             |
| `7f3a1c9e2b03` interactions   | `000004_students_links`, `000005_interactions` |
| `7f3a1c9e2b04` audit          | `000006_audit`                                |
| `7f3a1c9e2b05` passport idx   | `000007_passport_perf_indexes`                |
| `7f3a1c9e2b06` readiness idx  | `000008_readiness_perf_indexes` (latest)      |

Existing databases at Alembic head `7f3a1c9e2b06` are adopted via:

```bash
python scripts/migrate.py baseline   # strict verify + mark applied, data kept
python scripts/migrate.py up         # no-op afterwards
```

Do NOT add new Alembic revisions. All schema changes go through new
numbered SQL migration pairs (`000009_*.up.sql` / `000009_*.down.sql`).

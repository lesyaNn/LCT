# Demo data

Idempotent production-ready seed: `backend/app/scripts/seed_demo.py`.
Safe to rerun any number of times — reruns create no duplicates, perform no
extra workflow transitions and emit no audit noise.

## Dry run (writes nothing)

```bash
docker compose exec backend python -m app.scripts.seed_demo --dry-run
```

PowerShell:

```powershell
docker compose exec backend python -m app.scripts.seed_demo --dry-run
```

## Production execution (explicit confirmation required)

```bash
docker compose exec -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo
```

PowerShell (one line):

```powershell
docker compose exec -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo
```

Alternative confirmation: `python -m app.scripts.seed_demo --confirm-production`.
Without `SEED_DEMO_DATA=true` (or `--confirm-production`) the script prints
`Demo seeding is disabled.` and exits WITHOUT touching the database.
No interactive `input()` — works in Docker/CI.

## What is created

| Entity | Count | Natural key |
|---|---|---|
| Universities | 5 | `name` |
| Directions | 6 | `code` (`IB-DEMO` … `NET-DEMO`) |
| Programs | 9 | `name` + direction (existing `DevOps-инженерия` is reused) |
| Vendors | 5 | `name` |
| Products | 10 | `vendor` + `name` + `version` (always with program + version) |
| Responsibles | 5 | `email` (+ primary link per university) |
| University programs | 9 | university + program |
| University products | 10 | university + product |
| Contracts | 4 | `ДОГ-ДЕМО-01` … `ДОГ-ДЕМО-04` |
| Licenses | 4 | `ЛИЦ-ДЕМО-01` … `ЛИЦ-ДЕМО-04` (`ЛИЦ-ДЕМО-02` expires in ~20 days) |
| Workflow template | 1 | `Демонстрационный маршрут взаимодействия с вузом` (5 stages) |
| Workflow instances | 5 | one per university, on its target stage |
| Meetings | 5 | university + subject |

Notes:

- Relative dates (`today ± N days`) are computed ONLY at first creation;
  reruns never re-date existing rows.
- Workflow moves go through the canonical `transition_instance` service
  (never direct `current_stage_id` writes); instances already on target are
  left untouched.
- No `vendor_contacts` are created: the codebase currently exposes only
  read models for them (no create service) — the seed prints a warning.
- `Attention=true` demo is skipped (`[SKIP]`): the business API does not
  support its safe creation.
- No existing data is ever deleted or modified; no raw SQL writes; no
  hardcoded UUIDs; no secrets in output.

## Tests

```bash
cd backend && python -m pytest tests/test_seed_demo.py -q
```

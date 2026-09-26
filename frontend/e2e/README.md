# Critical demo-flow smoke

`auth-foundation.spec.ts` includes self-contained adapter checks and real
Keycloak scenarios when the corresponding `E2E_ADMIN_*`, `E2E_MANAGER_*`,
`E2E_CURATOR_*`, or `E2E_USER_*` username/password variables are present.
Credential values stay in the local shell or CI secret store and are never
committed.

The suite contains one mutating desktop smoke test with ten ordered Playwright
steps. It runs against a complete deployed stand because authentication,
Workflow transitions, report jobs, downloads, and audit events cross the
frontend boundary.

## Required environment

| Variable | Purpose |
| --- | --- |
| `E2E_BASE_URL` | Frontend origin. Defaults to `http://localhost:3000`. |
| `E2E_MANAGER_USERNAME` | Username of the dedicated Keycloak manager. |
| `E2E_MANAGER_PASSWORD` | Password of that manager. Keep it in a local shell or CI secret. |
| `E2E_UNIVERSITY_ID` | Stable university fixture shown by `/universities`. |
| `E2E_UNIVERSITY_NAME` | Accessible link name for that fixture. |
| `E2E_WORKFLOW_INSTANCE_ID` | UUID of a write-capable Workflow instance. |
| `E2E_WORKFLOW_PROGRAM_ID` | UUID of the selected university program linked to that Workflow. |
| `E2E_EXPECTED_WORKFLOW_STAGE` | Current stage name after the fixture reset. |
| `E2E_RUN_ID` | Optional stable run label used in created comments. SourceCraft uses `SOURCECRAFT_RUN_ID` automatically. |
| `E2E_CRITICAL_ISOLATED` | Optional `1` on a disposable stand: create a unique program and Workflow before each run. Requires `E2E_ADMIN_USERNAME`, `E2E_ADMIN_PASSWORD`, and `E2E_API_URL`; static Workflow IDs and stage name are then unnecessary. |

Do not commit credential values. SourceCraft reads them from repository
secrets named `e2e_base_url`, `e2e_manager_username`,
`e2e_manager_password`, `e2e_university_id`, `e2e_university_name`,
`e2e_workflow_instance_id`, and `e2e_expected_workflow_stage`.

On a shared stand, the configured fixture must be reset before every run (or a
fresh instance ID must be supplied), because the scenario intentionally advances
Workflow and adds a comment. The disposable-stand mode creates a unique fixture
automatically and is repeatable without a reset. Playwright retries are disabled
to avoid repeating mutations on shared stands.
The report endpoint must return a terminal `ready` job with a downloadable
XLSX URL, and the audit endpoint must expose the corresponding
`WORKFLOW_TRANSITION` event.

Run the complete stand first, export the variables, then execute:

```bash
cd frontend
npm run test:e2e:smoke
```

Artifacts are written to `test-results/` and `playwright-report/`. Five named
checkpoint screenshots are attached on successful runs; failure screenshot,
video, and trace are retained automatically.

## Admin Users / RBAC integration

`admin-users-real.spec.ts` checks real Keycloak login for admin, manager, and
user. Its fourth test creates users and universities, changes role/scope,
blocks/unblocks an account, and attempts invite/reset. It is opt-in and must
run only against a disposable realm and database:

```bash
docker compose -p team26-admin-users-e2e -f docker-compose.yml -f docker-compose.admin-users-e2e.yml up -d --build frontend
```

The Compose project name gives this stand its own network and volumes; ports
are 13000 (frontend), 18000 (backend), and 18081 (Keycloak). On this isolated
Keycloak instance, update the `rtk-frontend` client's redirect URI and web
origin to `http://localhost:13000/*` and `http://localhost:13000`. The imported
realm requires HTTPS by default. For local HTTP testing only, explicitly set
its `sslRequired` to `NONE` in this disposable realm, or provide HTTPS instead.
Never change the shared dev realm's SSL policy for this test.

Set `E2E_BASE_URL=http://localhost:13000`, `E2E_API_URL=http://localhost:18000`,
the `E2E_ADMIN_*`, `E2E_MANAGER_*`, and `E2E_USER_*` credentials, plus
`E2E_ADMIN_USERS_MUTATIONS=1` and `E2E_ADMIN_USERS_ISOLATED=1` before running
`npx playwright test e2e/admin-users-real.spec.ts --workers=1`. Without both
mutation flags, the destructive scenario is skipped. The mutation test restores
the seeded user's role/scope, but creates uniquely named test records.
Afterward, `docker compose -p team26-admin-users-e2e -f docker-compose.yml -f
docker-compose.admin-users-e2e.yml down -v` removes only the disposable stand.

## External integrations (Stage 11)

`external-integrations-real.spec.ts` uses the actual backend endpoints with
the explicit server-side mock LMS/Website adapters, not frontend fixtures.
It needs a disposable realm and DB. Start the dedicated Compose project:

```bash
docker compose -p team26-stage11-e2e -f docker-compose.yml -f docker-compose.external-e2e.yml up -d --build frontend
```

The imported realm requires HTTPS by default. For localhost HTTP testing,
change `sslRequired` to `NONE` **only** inside this isolated realm, and set
the `rtk-frontend` client's redirect URI/web origin to
`http://localhost:23000/*` / `http://localhost:23000`. Then run:

```bash
E2E_STAGE11_ISOLATED=1 E2E_BASE_URL=http://localhost:23000 E2E_API_URL=http://localhost:28000 \
  npx playwright test e2e/external-integrations-real.spec.ts --workers=1
```

The test creates its own catalog/Workflow fixtures, verifies persisted LMS
students, website aggregate, KPI filter, Workflow repeat, and degraded LMS
section. It uses the realm's disposable admin fixture unless
`E2E_STAGE11_ADMIN_USERNAME` / `E2E_STAGE11_ADMIN_PASSWORD` are supplied.
Afterward, `docker compose -p team26-stage11-e2e -f docker-compose.yml -f
docker-compose.external-e2e.yml down -v` removes only its temporary volumes.

## Final integration audit

Use a disposable realm/database for mutation tests. `E2E_WORKFLOW_ISOLATED=1`
creates a unique program and Workflow on `E2E_WORKFLOW_UNIVERSITY_ID` before
each `workflow-mutations-real.spec.ts` run; choose a university outside the
manager/user scope. It requires `E2E_WORKFLOW_MUTATIONS=1`, `E2E_API_URL`,
and admin credentials, but no pre-existing Workflow/program IDs. The
`E2E_CRITICAL_ISOLATED=1` mode above similarly prepares the manager smoke.
Configure the isolated Keycloak client redirect/web origin **and**
`post.logout.redirect.uris` for the frontend origin; the shared dev realm
must not be changed. `final-responsive-audit.spec.ts` needs the IDs of any
visible university, teacher, and Workflow to check real pages at 1440, 1024,
768, and 390 px. The external integration E2E uses the explicit backend
test adapters and does not prove connectivity to a live LMS or website.

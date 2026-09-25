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
| `E2E_EXPECTED_WORKFLOW_STAGE` | Current stage name after the fixture reset. |
| `E2E_RUN_ID` | Optional stable run label used in created comments. SourceCraft uses `SOURCECRAFT_RUN_ID` automatically. |

Do not commit credential values. SourceCraft reads them from repository
secrets named `e2e_base_url`, `e2e_manager_username`,
`e2e_manager_password`, `e2e_university_id`, `e2e_university_name`,
`e2e_workflow_instance_id`, and `e2e_expected_workflow_stage`.

The configured fixture must be reset before every run (or a fresh instance ID
must be supplied), because the scenario intentionally advances Workflow and
adds a comment. Playwright retries are disabled to avoid repeating mutations.
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

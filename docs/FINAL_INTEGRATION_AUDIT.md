# Final frontend ↔ backend integration audit

Branch: `integration/api-12-final-audit` (from `integration/api-11-external-integrations`; no `develop` pull or merge). Audit used only the disposable `team26-stage12-e2e` PostgreSQL/Redis/Keycloak/backend/worker/frontend Compose project for browser mutations. `R` = verified real backend path; `B` = unavailable/incomplete contract or external environment; `—` = not a meaningful operation. A read marked `R` is not a claim that all mutations for that domain exist.

## Actual route map

| Route | Result |
| --- | --- |
| `/`, `/teachers` | Redirects to `/dashboard`, `/universities` respectively; no empty menu destination |
| `/login` | REAL Keycloak login/logout, four role accounts |
| `/dashboard`, `/universities`, `/universities/[id]` | REAL analytics/list/passport; individual unsupported passport sections remain read-only |
| `/teachers/[id]` | REAL UUID teacher passport, read-only |
| `/workflows`, `/workflows/[id]` | REAL list, detail, transitions, comments, files; Kanban tested |
| `/reports`, `/audit`, `/docs` | REAL reports/jobs/download, audit, documentation |
| `/admin` | Working landing with section links |
| `/admin/users`, `/admin/catalogs`, `/admin/import` | REAL users, catalogs, import wizard |
| `/admin/workflow/templates`, `/admin/workflow/templates/[id]/edit` | REAL template list/create/activate and stage editor |
| `/403`, `/404`, `/500`, `/_not-found` | Existing system states/routes; unauthorized/missing backend entities were also exercised |

No discovered menu route was empty or broken. The historical teacher list is deliberately a redirect, because the old integer-PK teacher CRUD router is unmounted and incompatible with the canonical UUID teacher model.

## Domain matrix

| Domain | Read | Create | Update | Delete/deactivate | Upload/download | Status and qualification |
| --- | --- | --- | --- | --- | --- | --- |
| Auth | R | — | — | R logout | — | R Keycloak + `/auth/me` |
| Users/RBAC | R | R invite | R role/scope/block/reset | R block; hard delete — | — | R isolated admin/manager/user and re-login scope |
| Universities | R | R API/catalog | R API/catalog | R API hard-delete policy | — | R list/search/scope/passport; deletion of referenced records forbidden |
| Four catalogs | R | R | R | R API policy | R XLS/XLSX import | R Universities, IT products, IT directions, responsibles; some linked rows cannot be deleted |
| Passport | R | — | R supported relations | — | — | R aggregate/subresources; not every tab has mutation contract |
| Programs | R | R catalog/attach | R catalog | R constrained API | R import | R program selection and relation; no invented UUID |
| Teachers | R | B | B | B | B | UUID teacher passport is read-only; legacy integer CRUD is unmounted |
| Students | R | R | R | R | R XLS/XLSX/LMS sync | R browser CRUD/reload; PII not exposed in common lists |
| Certificates | R | B | B | B | B | Teacher certificate/readiness view only; no mounted UUID mutation contract |
| Products | R | R catalog/attach | R catalog | R constrained catalog API | R import | R catalog and University relation; relation editing limited by API |
| Licenses | R | R import | R import | B | B | Read in passport/report; no general license CRUD/download UI/API |
| Documents | R | R import/Workflow attachment | R import | B passport; R Workflow attachment | R Workflow files; B passport files | Passport document metadata has no authenticated download URL or general UUID file API |
| Meetings | R | R | R | R | — | R browser CRUD/reload |
| Health Score | R | R backend calculation | — | — | R chart export | R dashboard/passport calculations, history/breakdown |
| Workflow | R | R | R transition/comment/template/stage | R comment/file/stage deactivate | R attachment upload/download | R details, program selection, Kanban confirm/cancel, audit |
| Reports | R | R async job | — | — | R XLSX download | R UI → job → worker → inspected XLSX |
| Analytics | R | — | — | — | R chart export | R real overview/KPI/charts; no fake counts |
| Audit | R | R automatic events | — | — | — | R transition/report/user/import events, filter/detail; sensitive values masked in UI |
| Import | R | R preview/dry-run/execute | R upsert | — | R XLS/XLSX/errors report | R async worker, result history, idempotent catalog tests |
| External LMS | R cached/test adapter | R sync via test adapter | R sync | — | — | B LIVE: no external LMS service/credentials supplied |
| Website applications | R cached/test adapter | R sync and Workflow from application | R sync | — | — | B LIVE: no external website service/credentials supplied; test adapter dedup/idempotence verified |

`R API` in the matrix means a mounted production endpoint exists and its backend suite passed; it does **not** overstate browser CRUD coverage. Teacher/certificate/license/passport-document gaps are blockers for a claim of complete end-user CRUD and need a separate UUID-domain contract/business decision. The final-stage request explicitly prohibited inventing new business modules.

## Fixes and evidence

- Enabled existing real Workflow template create/stage add/stage update and PATCH active state through canonical repository/mutation hooks. Browser verified create, add, reload, deactivate/reload. Removed obsolete read-only text.
- Removed dead profile/settings/notification/header buttons and mock-only disabled Workflow/Passport actions. Unsupported document downloads show `—`, not an actionable fake button. Existing real transition opens its modal.
- Fixed Keycloak logout navigation race; isolated realm additionally needs `post.logout.redirect.uris` configured for its frontend origin. Main branded login/logout and `/auth/me` passed for admin, manager, curator, user.
- Replaced raw query-key arrays with factory keys and kept mutation invalidation scoped. Search found no direct `fetch`/`XMLHttpRequest` in components/pages; the shared `api-client.ts` alone owns transport and authenticated blob download. No global `invalidateQueries()` call remains.
- Removed Kanban per-card allowed-transition GET fan-out. Opening the board issues no such per-card requests; dropping one card fetches and validates its allowed target once. Cancel does not mutate, confirm persists.
- Explicit Mock/Demo paths remain behind production opt-in. Static review found no REAL-error → mock dataset catch/fallback. Error/retry paths were exercised on University/Passport and external degraded state. No broad refactor of distinct API semantics was needed.
- Full browser run verified no unexpected API 4xx/5xx or console/page errors on ordinary key routes. Permission 403 and unknown-entity 404 were intentional test cases. Responsive route sweep covered Login plus 14 key routes at 1440, 1024, 768 and 390 px with no document-level horizontal overflow. This is a structural responsive/console check, not a claim that every visual detail was pixel-reviewed.
- Teacher Passport and University Passport were read from real UUID data; disabled teacher edit was removed because only the old, unmounted integer CRUD router contains that capability.

## Runtime scenario and fixtures

Admin: real Keycloak login, Users list, change role/scope, block/unblock, invite/reset, re-login as user and backend-scoped Universities GET. Self/last-admin protections have backend regression tests (`test_admin_users_rbac.py`); destructive last-admin cases were not replayed against the shared realm. Manager: real login, Dashboard/KPI, University list/Passport/Health, Program selector, Workflow transition/comment, Reports ready/download, Audit event, Import. User: real login and denied unassigned Passport/Workflow writes. Teacher/Student/Meeting/Document/License tabs were opened in real Passport; student and meeting CRUD persisted after reload. Workflow comments and attachment upload/download/delete persisted after reload. Report XLSX opened with `openpyxl`: 7 rows × 14 columns in the inspected test job, 11/14 populated data cells in its row; empty fields reflected seed data, not fabricated values. Audit listed the actual transition.

Import of `docs/import-example-20.xlsx` on the isolated DB: first real execution had 20 rows, 15 inserted, 5 skipped, 0 errors; a repeated execution had 0 inserted/updated, 20 skipped, 0 errors. Dry-run and persisted job history passed. Backend suite also tests four catalog upserts, duplicate/conflict handling and empty-cell preservation. `.xls` is implemented with `xlrd` and accepted by the endpoint, but no provided legacy `.xls` fixture was available for a browser runtime check. External LMS/website E2E used the explicitly labeled backend **test adapters**, never frontend mock fallback; live connectivity remains unverified.

Clean disposable DB startup applied the canonical SQL migrations through `000027_external_integrations` (`27/27`, 37 tables, verify OK). Standard seed ran and reran without error. PostgreSQL, Redis, Keycloak, backend, worker and production frontend were healthy. Isolated HTTP-only Keycloak `sslRequired=NONE` and redirect configuration were confined to this disposable realm; no shared dev realm or DB was changed. `.env.example` defaults to REAL Keycloak/data and requires explicit production mock opt-in; no credentials were committed.

## Tests and limitations

- Backend full PostgreSQL suite: **1119 passed**, 3 third-party deprecation warnings. The initial test-container invocation omitted read-only `/docs` and `/keycloak` fixture mounts (16 fixture-file failures, not product failures); the corrected full rerun passed.
- Frontend: `npm run typecheck`, `npm run lint -- --max-warnings=0` (via script), `npm run build` all passed.
- Playwright final full isolated stand: **38 passed, 0 failed, 0 skipped**. A previous run had five intentional Workflow skips because the separate unassigned-WU fixture flag was unset; `E2E_WORKFLOW_ISOLATED=1` now creates a unique program/instance per run and removed those skips. The critical manager smoke likewise uses `E2E_CRITICAL_ISOLATED=1` for repeatable fixtures.
- Browser runtime cannot prove real LMS/website connectivity, SMTP mail delivery, or unsupported UUID teacher/certificate/license/passport-document CRUD. These must not be presented as REAL before merge. The isolated test realm's HTTP concession is unsuitable for production; production must retain HTTPS.
- No frontend or backend secrets, personal test credentials, or generated reports/import files are committed. The disposable stand and volumes are removed after verification.

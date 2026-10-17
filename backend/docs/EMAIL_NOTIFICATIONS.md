# Email delivery for CRM notifications

Email is an optional second channel of the existing notification service. The
business event creates one notification; when enabled and a usable address is
known, `publish()` enqueues one `notification_deliveries` row in the same
transaction. SMTP is only called by the existing report/import worker after
commit. The in-app inbox continues to work when SMTP is unavailable.
An email enqueue database error is isolated with a savepoint so the business
audit event and in-app notification can still commit.
Reprocessing an event with the same key reuses its notification without changing
its content. If email is currently enabled and the recipient now has one valid
address, it may repair a missing email delivery; an existing delivery is reused.

## Address and preferences

The recipient is identified by Keycloak `sub`. Existing events resolve email
through the local `responsibles` row linked by `keycloak_sub`. For
`user_university_assigned`, the admin-users operation supplies the target
Keycloak user's email at publication time; a `Responsible` row is unnecessary
and cannot override this address. Missing or invalid explicit email yields only
the in-app notification, even when a linked `Responsible` exists. The worker
never queries Keycloak for an address. Every queued delivery stores its
recipient as a snapshot; later Keycloak email changes do not alter it. There is
no existing notification preference store, so this version uses the global
`EMAIL_NOTIFICATIONS_ENABLED` switch; it defaults to `false`. No user toggle is
exposed yet.

## Configuration

Set the following environment variables for both API and worker through the
local compose file. The API needs `EMAIL_NOTIFICATIONS_ENABLED`, `SMTP_HOST`
and `SMTP_FROM_EMAIL` for configuration validation and enqueue; SMTP credentials
are only injected into the worker.

| Variable | Purpose |
| --- | --- |
| `EMAIL_NOTIFICATIONS_ENABLED` | `false` by default; `true` enables enqueue and send |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server and port; default port 587 |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Optional SMTP authentication |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | Sender address and display name |
| `SMTP_SECURITY` | `starttls` (default) or `ssl`; plaintext is unsupported |
| `SMTP_TIMEOUT_SECONDS` | Network timeout, default 10, maximum 60 |
| `EMAIL_MAX_ATTEMPTS` | Maximum delivery attempts, default 5 |
| `FRONTEND_ORIGIN` | Public CRM origin used for absolute links |

TLS uses the system CA trust store and certificate verification. Do not place
credentials in Git. The worker stores fixed error categories such as `timeout`
and `smtp_permanent`, never raw SMTP replies. Logs contain delivery and
notification IDs but no recipient address or message body.
When email is enabled, startup validates `SMTP_FROM_EMAIL` as exactly one
mailbox. Outbound recipients use the same stricter check, while contact-field
validation elsewhere in the CRM keeps its existing contract. Disabled email
does not require SMTP settings.

## Delivery

Every event currently handled by `Notification Service` is eligible: assignment,
workflow stage change and rollback, current stage/task deadline and overdue,
contract and license expiry, import errors, and user university assignment. The
existing scanner and its event deduplication rules are reused. The inbox's target
routes are mirrored in plain-text emails; no tokens are added to links.

When a user's role or university scope changes, Keycloak sessions are ended so
the next login receives current claims. A previously issued access token can
retain its old scope until its short expiry; the inbox and university routes
continue to enforce that scope. After signing in again, the new notification and
its university target are available under the new scope.

The worker atomically claims one due row with `FOR UPDATE SKIP LOCKED`, commits
a claim token and lease, then calls SMTP without an open database transaction.
A separate short database session renews the lease every 30 seconds while SMTP
runs. Renewal and final status writes require the current claim token; an old
worker cannot overwrite a reclaimed delivery. If renewal fails, the worker
retries promptly and records a lost lease without changing the new owner's row.
Temporary failures retry after 1, 5, 15,
and 60 minutes. An unambiguous SMTP 5xx or invalid recipient fails immediately.
After five attempts the row becomes `failed`. Expired leases are reclaimed;
attempts exhausted during a crash become `failed` on the next worker cycle.
Delivery semantics are **at-least-once**. SMTP does not offer an atomic
acknowledgement with PostgreSQL across a process crash:
if a worker dies after the server accepts a message but before recording `sent`,
that message can be retried. The unique `(notification_id, channel)` constraint
prevents duplicate outbox rows.

## Local testing

Run unit tests without SMTP: `python -m pytest tests/test_notification_email.py -q`.
For database tests, set `TEST_DATABASE_URL` to a dedicated local PostgreSQL
database whose name contains `test`; the fixture resets its public schema and
applies the full SQL migration chain. The sender is replaced with a fake in
tests, so no external mail is sent. A local SMTP sink used for manual testing
must support STARTTLS or SSL; the application has no plaintext fallback.

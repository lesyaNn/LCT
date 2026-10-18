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
Workflow stage completion, rollback and final completion, task creation and
completion, current stage/task deadline and overdue,
contract and license expiry, import errors, user university assignment and manual
Workflow comments (including comments with attachments). The
existing scanner and its event deduplication rules are reused. The inbox's target
routes are mirrored in both email alternatives; no tokens are added to CRM links.

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

## Email presentation

CRM sends UTF-8 `multipart/alternative`: the original `text/plain` followed by
`text/html`. Subjects, the sender's three-string interface, outbox, recipients,
retries and event text are unchanged. `email_templates.py` renders every event,
including future types, from the same canonical text. Only the final CRM footer
on the configured frontend origin becomes a CTA and visible fallback URL.
Unusable origins produce no CTA. Dynamic text is HTML-escaped; line breaks,
full messages and escaped entity paths are preserved. Templates ship as package data.

The design follows `frontend/styles/globals.css`: purple `#7700ff`, orange
`#ff4f12`, page `#f4f4f7`, primary text `#101828`, 18px cards and 10px buttons.
The header uses the site's original horizontal logo exported to a 436×138 PNG with white padding,
displayed at 218×69 with a white backing for readability in both color schemes.
CRM attaches it inline using a Content-ID in the HTML part's `multipart/related`
container; the original `text/plain` alternative stays unchanged. No remote
request is needed for CRM images. Keycloak serves the matching PNG from its email
theme's public resources URL; when rendering without a request URL, the company
name is shown as text. Both paths retain alt text and the automatic-message footer.
Brand fonts fall back to Arial; no external fonts or styles load.
Presentation tables, a fluid 600px card, inline core styles, Outlook conditional
width tables and padded button cells provide the baseline. Responsive padding
and dark colors are progressive enhancements in embedded media queries.
Clients that strip media queries retain the fluid layout and explicit light colors.

### Keycloak account emails

Invitations/password updates still use Keycloak's existing `execute-actions-email`
API. `keycloak/themes/rostelecom/email` inherits `base` and overrides only its
common HTML layout. All 18 base email types receive the branding: verification
links/codes, password reset, email change, identity linking, organization invites,
credential offers, security events, workflow notifications and SMTP tests.
Informational/code messages have no added button. Action emails retain the
original inline link and add a button and visible fallback URL.

Base subjects, localized messages, sanitized HTML, required actions, expiration,
URLs/tokens and `text/` alternatives remain inherited. Only presentation labels
have new Russian/English translations, using
[Keycloak theme inheritance](https://www.keycloak.org/ui-customization/themes).

The realm export sets `emailTheme: rostelecom` for new installations. Startup
import does not overwrite existing persisted realms: select **Realm settings →
Themes → Email theme → rostelecom** once, or use an already authenticated admin
`kcadm.sh` session:

```sh
kcadm.sh update realms/rtk -s emailTheme=rostelecom
```

The existing Compose mount provides theme files. Clear the theme cache/restart
Keycloak after changing cached templates in deployed environments.

## Local testing

Run unit tests without SMTP: `python -m pytest tests/test_notification_email.py -q`.
For database tests, set `TEST_DATABASE_URL` to a dedicated local PostgreSQL
database whose name contains `test`; the fixture resets its public schema and
applies the full SQL migration chain. The sender is replaced with a fake in
tests, so no external mail is sent. A local SMTP sink used for manual testing
must support STARTTLS or SSL; the application has no plaintext fallback.

### Preview without sending mail

From `backend/`, generate all 19 CRM scenarios (HTML and original text), including
both university access destinations, comments and both import outcomes:

```sh
python -m scripts.preview_notification_emails --output /tmp/rtk-emails
python -m pytest tests/test_notification_email_templates.py tests/test_notification_email.py -q
```

Open `/tmp/rtk-emails/index.html`. Generation needs no database or SMTP.

To render actual inherited Keycloak templates, use JARs from the installed image
(currently 26.7.4) and a local JDK 21+. From the repository root:

```sh
docker compose cp keycloak:/opt/keycloak/lib/lib/main/org.keycloak.keycloak-themes-26.7.4.jar /tmp/rtk-keycloak-themes.jar
docker compose cp keycloak:/opt/keycloak/lib/lib/main/org.freemarker.freemarker-2.3.32.jar /tmp/rtk-freemarker.jar
java --class-path /tmp/rtk-freemarker.jar keycloak/tests/EmailThemePreview.java /tmp/rtk-keycloak-themes.jar keycloak/themes/rostelecom/email /tmp/rtk-emails/keycloak
python keycloak/tests/verify_email_previews.py /tmp/rtk-emails/keycloak
```

This generates 44 previews: 18 types in Russian/English plus unpersonalized
invitations and general, deletion and custom workflow messages. Verification compares 36 standard
previews with base templates, checking full text, URLs/tokens, leading-zero codes
and informative headings. Trusted demo fixtures stand in for data/sanitization;
production retains Keycloak's real sanitizer. The harness never changes a realm
or sends email. Open `/tmp/rtk-emails/keycloak/index.html` to browse the previews.

After generating the Keycloak previews, build the single offline gallery from
`backend/`:

```sh
python -m scripts.build_email_gallery --keycloak-dir /tmp/rtk-emails/keycloak --output ../docs/email-examples.html
```

The resulting `docs/email-examples.html` embeds only the 21 implemented sending
scenarios: 19 CRM variants and 2 account scenarios (invitation and administrator
password update), both using `executeActions` with `UPDATE_PASSWORD`. The gallery
uses Russian, matching the realm configuration. Inherited Keycloak templates
without an application trigger are excluded. It includes navigation,
search, light/dark preview modes, desktop/375px/320px widths, text representations
and per-email HTML download. JavaScript belongs only to this review page; email
templates remain script-free. Logos in this standalone gallery are embedded data
URIs, so it still works offline. All data and links are demonstrative.

Check widths 320px, 375px and desktop, light/dark media modes, long unbroken
titles/messages/URLs and disabled styles. Browser previews do not emulate Word's
Outlook rendering or Gmail's automatic color inversion. Validate those on actual
Gmail, Outlook and Apple Mail test mailboxes before deploying.

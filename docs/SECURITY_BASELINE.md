# P5‑13‑01 Security baseline

Техническая сводка проверяемых мер и ссылок на код.

| Мера | Реализация | Проверка |
|---|---|---|
| Secrets | production settings fail closed; S3 credentials имеют только env source | `app/config.py`, secret scan |
| CORS | explicit `CORS_ORIGINS`, credentials with allowlist, fixed methods/headers | `app/main.py`, CORS tests |
| Headers | nosniff, DENY, CSP, Referrer-Policy, Permissions-Policy, X-XSS-Protection | `app/core/middleware.py` |
| Request size | bounded body counter (Content-Length and streaming chunks), 413 ErrorResponse | `RequestSizeLimitMiddleware` |
| Uploads | streamed 50 MiB exact file limit, filename sanitization, temp cleanup, optional extension allowlist | `workflow_attachments/policy.py`, `service.py`, `storage.py` |
| Paths | generated storage keys and root containment for local/report files | `workflow_attachments/storage.py`, report jobs |
| SQL | SQLAlchemy ORM/Core expressions and enum/allowlist sort mappings | catalog/analytics repositories |
| Logs | `SensitiveFilter`, audit/report sanitizers; no Authorization/JWT/password values | `app/core/logging.py`, audit service |
| Dependencies | runtime direct dependencies exact pinned in `pyproject.toml`; Docker pins match | `backend/pyproject.toml`, `backend/Dockerfile` |

No dependency vulnerability scan was run in this environment. Dependency scan
status is therefore **NOT RUN**; exact pins reduce drift but do not replace a
SCA process.

## Operational boundaries

`/health`, `/ready`, `/docs`, `/redoc` and `/openapi.json` remain operational
exceptions outside `/api/v1`. All mounted business operations are under
`/api/v1`, require `BearerAuth`, and expose the unified `ErrorResponse` for
documented errors. Swagger/ReDoc CSP explicitly allow only the jsDelivr origins
used by FastAPI's generated pages.


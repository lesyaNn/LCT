# P5 audit contract

## CANONICAL_NAME_COMPATIBILITY

`audit_events` is the existing P1/P2 canonical ledger. Migration `000021_audit_p5`
evolves it in place; there is no `audit_logs` table. The P5 public names
`timestamp` and `ip` map to physical `created_at` and `ip_address`. The old
`before_data` and `after_data` text columns become `old_value` and `new_value`
JSONB. Existing integer event and entity IDs are mapped deterministically to
UUIDs. The university foreign key is removed so a DELETE event can retain the
deleted university ID for historical scope checks.

`AuditService.log_event` remains available for legacy direct-write paths.
Workflow transitions use `AuditService.enqueue_event`: the business mutation,
transition history and sanitized `audit_outbox` intent commit together. A
worker relay later materializes `audit_events` in one transaction. Delivery is
eventually consistent and idempotent (the outbox UUID is the audit event UUID);
an unavailable audit sink therefore never rolls back the workflow transition.

### M9 decision (Dev-2 boundary)

Dev-2 keeps the audit ledger in the **same database transaction** as the
business mutation. This is the accepted M9 decision for the security/contract
scope: a successful mutation cannot commit without its audit row, and a
rollback removes both the mutation and its pending audit event. `AuditService`
therefore deliberately never calls `commit()`; the request/service transaction
is the single owner of commit and rollback.

This gives atomicity, but it is not an asynchronous outbox guarantee. If the
audit insert fails, the business mutation fails as well; that fail-closed
behaviour is intentional for security-sensitive changes. Introducing an
outbox worker would require coordinated changes to the workflow/import job
boundaries and is outside the Dev-2 zone. No endpoint in this branch claims
eventual outbox delivery.

## Current production paths

| Operation | Audit action | Entity |
| --- | --- | --- |
| University create, update, delete | CREATE, UPDATE, DELETE | university |
| Responsible create, update, delete | CREATE, UPDATE, DELETE | responsible |
| University responsible assign/unassign | ASSIGN_RESPONSIBLE | responsible (assignment ID) |
| Meeting create, update, delete | CREATE, UPDATE, DELETE | meeting |
| Student create, update, delete | CREATE, UPDATE, DELETE | student |
| Direction, program, vendor, product create/update/delete | CREATE, UPDATE, DELETE | direction, program, vendor, product |
| Workflow comment create, update, delete | CREATE, UPDATE, DELETE | workflow_comment |
| Workflow instance transition | WORKFLOW_TRANSITION | workflow_instance |
| Report job creation | REPORT_GENERATE | report (job ID) |
| XLSX import job creation | IMPORT | report (job ID) |
| Workflow template/stage create/update | ADMIN_CONFIG | config/workflow_stage |

The production teacher router is not mounted. License and contract changes
currently occur in the import orchestrator and are represented by its IMPORT
event; there are no mounted standalone license/contract mutation endpoints.
The IMPORT event records the durable job creation in the same transaction.
The worker executes row imports through later commits, so the event does not
certify successful import of every row. Adapters are unchanged.
The Keycloak OIDC flow has no reliable backend LOGIN/LOGOUT lifecycle hook, so
those actions are registered but no synthetic events are emitted.

`GET /api/v1/audit/events` is the only public audit route. Managers see only
events for assigned universities. Explicit foreign university filters return
403. Admins see all events, including global config and multi-scope report
events. Users and compatibility curators have no `audit.read` permission.

Snapshots are recursively redacted and capped at 8 KiB. Request IDs reuse the
request middleware value; IP comes from `request.client.host`, without trusting
an unconfigured proxy header. User-Agent is stored as a bounded raw string.

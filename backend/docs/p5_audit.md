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

### M9 integration decision

Workflow transitions use the Dev-1 outbox: the business change, history, and
sanitized audit intent commit in one transaction. The relay delivers to
`audit_events` later and retries a failed sink without undoing the transition.
Other mounted mutation paths, including Dev-2's student, catalog, and workflow
comment coverage, currently call `AuditService.log_event` in the business
transaction. `AuditService` never commits on its own. A failed direct audit
insert therefore aborts that business mutation; a rollback removes both.

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
events. Users have no `audit.read` permission.

Snapshots are recursively redacted and capped at 8 KiB. Request IDs reuse the
request middleware value; IP comes from `request.client.host`, without trusting
an unconfigured proxy header. User-Agent is stored as a bounded raw string.

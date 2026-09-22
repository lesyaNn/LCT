-- Rollback for 000017_tasks_priority.

DROP INDEX IF EXISTS ix_workflow_tasks_instance_priority;
ALTER TABLE workflow_tasks DROP COLUMN IF EXISTS priority;

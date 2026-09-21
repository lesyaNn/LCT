-- Rollback for 000013_tasks_priority.

DROP INDEX IF EXISTS ix_tasks_instance_priority;
ALTER TABLE tasks DROP COLUMN IF EXISTS priority;

-- SQL migration 000017: workflow_tasks.priority (P2-07-02).
--
-- Source of truth for: workflow_tasks.priority + index.
--
-- Ported from the pre-merge 000013_tasks_priority migration (which targeted
-- the superseded short-name ``tasks`` table) onto the canonical B1
-- ``workflow_tasks`` table. DDL semantics preserved: priority
-- VARCHAR(32) NOT NULL DEFAULT 'normal' (normal/critical); Health Score
-- component T penalizes critical overdue tasks with -8 and normal overdue
-- tasks with -4.
--
-- Additive only: no B1 migration file is modified.

ALTER TABLE workflow_tasks ADD COLUMN priority VARCHAR(32) NOT NULL DEFAULT 'normal';
CREATE INDEX ix_workflow_tasks_instance_priority ON workflow_tasks USING btree (instance_id, priority);

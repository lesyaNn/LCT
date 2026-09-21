-- SQL migration 000013 DOWN: remove instance runtime stages.
-- Dependency order: drop the instance -> instance_stages FK/columns first,
-- then the instance_stages table. No CASCADE: nothing outside 000013
-- references these objects.

ALTER TABLE workflow_instances
    DROP CONSTRAINT fk_workflow_instances_current_instance_stage_id_instance_stages;
DROP INDEX ix_workflow_instances_current_instance_stage_id;
ALTER TABLE workflow_instances
    DROP COLUMN current_instance_stage_id,
    DROP COLUMN completed_at;
DROP TABLE instance_stages;

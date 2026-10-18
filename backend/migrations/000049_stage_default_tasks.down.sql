ALTER TABLE workflow_stages
    DROP CONSTRAINT ck_workflow_stages_default_tasks_array,
    DROP COLUMN default_tasks;

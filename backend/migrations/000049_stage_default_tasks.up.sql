-- Tasks are copied to each new workflow; existing instances stay unchanged.
ALTER TABLE workflow_stages
    ADD COLUMN default_tasks JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT ck_workflow_stages_default_tasks_array
        CHECK (jsonb_typeof(default_tasks) = 'array');

-- A linked Workflow meeting is a draft until its real date and type are set.
ALTER TABLE meetings ALTER COLUMN meeting_at DROP NOT NULL;
ALTER TABLE meetings ALTER COLUMN meeting_type DROP NOT NULL;
ALTER TABLE meetings ALTER COLUMN meeting_type DROP DEFAULT;
ALTER TABLE meetings ADD COLUMN workflow_instance_stage_id UUID;
ALTER TABLE meetings ADD CONSTRAINT fk_meetings_workflow_instance_stage_id_instance_stages
    FOREIGN KEY (workflow_instance_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL;
ALTER TABLE meetings ADD CONSTRAINT uq_meetings_workflow_instance_stage_id
    UNIQUE (workflow_instance_stage_id);

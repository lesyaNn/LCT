DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM meetings WHERE meeting_at IS NULL OR meeting_type IS NULL) THEN
        RAISE EXCEPTION 'Cannot roll back workflow meeting drafts while unscheduled meetings exist';
    END IF;
END $$;
ALTER TABLE meetings DROP CONSTRAINT uq_meetings_workflow_instance_stage_id;
ALTER TABLE meetings DROP CONSTRAINT fk_meetings_workflow_instance_stage_id_instance_stages;
ALTER TABLE meetings DROP COLUMN workflow_instance_stage_id;
ALTER TABLE meetings ALTER COLUMN meeting_at SET NOT NULL;
ALTER TABLE meetings ALTER COLUMN meeting_type SET NOT NULL;
ALTER TABLE meetings ALTER COLUMN meeting_type SET DEFAULT 'online';

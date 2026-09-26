ALTER TABLE students ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'manual';
ALTER TABLE students ADD COLUMN progress INTEGER;
ALTER TABLE students ADD COLUMN synced_at TIMESTAMPTZ;
ALTER TABLE students ADD CONSTRAINT ck_students_progress_range CHECK (progress IS NULL OR progress BETWEEN 0 AND 100);

CREATE TABLE external_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(32) NOT NULL,
    external_id VARCHAR(256) NOT NULL,
    ingest_channel VARCHAR(32) NOT NULL,
    university_id UUID REFERENCES universities(id) ON DELETE RESTRICT,
    program_id UUID REFERENCES it_programs(id) ON DELETE RESTRICT,
    student_id UUID REFERENCES students(id) ON DELETE SET NULL,
    person_name VARCHAR(512),
    status VARCHAR(64),
    flow_name VARCHAR(256),
    external_created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ NOT NULL,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_applications_source_id UNIQUE (source, external_id)
);
CREATE INDEX ix_external_applications_university_program ON external_applications(university_id, program_id);
CREATE INDEX ix_external_applications_created_at ON external_applications(external_created_at);
CREATE INDEX ix_external_applications_workflow_instance_id ON external_applications(workflow_instance_id);

CREATE TABLE external_sync_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    university_id UUID NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    source VARCHAR(32) NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_sync_states_university_source UNIQUE (university_id, source)
);

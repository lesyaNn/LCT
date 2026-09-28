-- Down can recreate the former shape, but deleted individual learner PII is
-- intentionally not recoverable from aggregates. Restore from backup if needed.
ALTER TABLE teacher_programs
    DROP CONSTRAINT IF EXISTS ck_teacher_programs_training_status,
    DROP CONSTRAINT IF EXISTS ck_teacher_programs_qualification_status,
    DROP COLUMN IF EXISTS training_status,
    DROP COLUMN IF EXISTS qualification_status,
    DROP COLUMN IF EXISTS last_training_at,
    DROP COLUMN IF EXISTS next_qualification_due_at;

-- Keep email nullable: records created after 000037 have no email, and a
-- rollback must not fabricate personal contact data.

CREATE TABLE students (
    id UUID PRIMARY KEY,
    external_id VARCHAR(256) NOT NULL UNIQUE,
    university_id UUID NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    program_id UUID NOT NULL REFERENCES it_programs(id) ON DELETE RESTRICT,
    full_name VARCHAR(512) NOT NULL,
    group_name VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    started_at DATE NOT NULL,
    finished_at DATE,
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    progress INTEGER CHECK (progress IS NULL OR progress BETWEEN 0 AND 100),
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_students_university_id ON students(university_id);
CREATE INDEX ix_students_program_id ON students(program_id);
CREATE INDEX ix_students_status ON students(status);
ALTER TABLE external_applications ADD COLUMN student_id UUID REFERENCES students(id) ON DELETE SET NULL;
CREATE INDEX ix_external_applications_student_id ON external_applications(student_id);

DROP TABLE program_education_stats;

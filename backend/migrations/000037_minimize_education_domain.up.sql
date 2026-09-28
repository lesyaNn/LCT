-- Keep only the program statistics required by the ТЗ. 000036 may already
-- have been applied; reduce its learner records to counts before removal.
CREATE TABLE program_education_stats (
    id UUID PRIMARY KEY,
    university_id UUID NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES it_programs(id) ON DELETE RESTRICT,
    source VARCHAR(32) NOT NULL,
    learners_count INTEGER NOT NULL DEFAULT 0 CHECK (learners_count >= 0),
    flows_count INTEGER NOT NULL DEFAULT 0 CHECK (flows_count >= 0),
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_program_education_stats_source UNIQUE (university_id, program_id, source)
);
CREATE INDEX ix_program_education_stats_university_id ON program_education_stats(university_id);
CREATE INDEX ix_program_education_stats_program_id ON program_education_stats(program_id);

INSERT INTO program_education_stats
    (id, university_id, program_id, source, learners_count, flows_count, synced_at)
SELECT gen_random_uuid(), university_id, program_id, source,
       count(*)::integer, count(DISTINCT group_name)::integer,
       coalesce(max(synced_at), now())
FROM students
GROUP BY university_id, program_id, source;

ALTER TABLE external_applications DROP COLUMN IF EXISTS student_id;
DROP TABLE students;

-- Teacher identity remains scoped to one university. Contact/HR columns and
-- historical evidence rows stay in place for existing data, but new workflows
-- use only per-program training and qualification status.
ALTER TABLE teachers ALTER COLUMN email DROP NOT NULL;
ALTER TABLE teacher_programs
    ADD COLUMN training_status VARCHAR(32) NOT NULL DEFAULT 'not_started',
    ADD COLUMN qualification_status VARCHAR(32) NOT NULL DEFAULT 'not_started',
    ADD COLUMN last_training_at DATE,
    ADD COLUMN next_qualification_due_at DATE;
ALTER TABLE teacher_programs
    ADD CONSTRAINT ck_teacher_programs_training_status
        CHECK (training_status IN ('not_started', 'in_progress', 'completed', 'needs_review')),
    ADD CONSTRAINT ck_teacher_programs_qualification_status
        CHECK (qualification_status IN ('not_started', 'in_progress', 'completed', 'needs_review'));

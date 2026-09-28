-- Restore the learner and educator domain required by the CRM specification.
-- 000029 remains immutable. Its deleted rows require an external backup.
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

CREATE TABLE teachers (
    id UUID PRIMARY KEY,
    university_id UUID NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    full_name VARCHAR(512) NOT NULL,
    email VARCHAR(512) NOT NULL UNIQUE,
    phone VARCHAR(64),
    "position" VARCHAR(256) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_teachers_university_id ON teachers(university_id);

CREATE TABLE teacher_qualifications (
    id UUID PRIMARY KEY,
    teacher_id UUID NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    qualification_name VARCHAR(512) NOT NULL,
    obtained_at DATE NOT NULL,
    expires_at DATE,
    document_ref VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_teacher_qualifications_teacher_id ON teacher_qualifications(teacher_id);
CREATE INDEX ix_teacher_qualifications_teacher_expires ON teacher_qualifications(teacher_id, expires_at);

CREATE TABLE teacher_certificates (
    id UUID PRIMARY KEY,
    teacher_id UUID NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    certificate_name VARCHAR(512) NOT NULL,
    issued_by VARCHAR(512) NOT NULL DEFAULT '',
    issued_at DATE NOT NULL,
    expires_at DATE,
    is_mandatory BOOLEAN NOT NULL DEFAULT FALSE,
    program_id UUID REFERENCES it_programs(id) ON DELETE SET NULL,
    document_ref VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_teacher_certificates_teacher_id ON teacher_certificates(teacher_id);
CREATE INDEX ix_teacher_certificates_expires_at ON teacher_certificates(expires_at);
CREATE INDEX ix_teacher_certificates_mandatory ON teacher_certificates(is_mandatory, expires_at);
CREATE INDEX ix_teacher_certificates_teacher_expires ON teacher_certificates(teacher_id, expires_at);

CREATE TABLE teacher_programs (
    id UUID PRIMARY KEY,
    teacher_id UUID NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    program_id UUID NOT NULL REFERENCES it_programs(id) ON DELETE RESTRICT,
    can_teach BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_at DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_teacher_programs_teacher_program UNIQUE (teacher_id, program_id)
);
CREATE INDEX ix_teacher_programs_teacher_id ON teacher_programs(teacher_id);
CREATE INDEX ix_teacher_programs_program_id ON teacher_programs(program_id);

ALTER TABLE external_applications ADD COLUMN student_id UUID REFERENCES students(id) ON DELETE SET NULL;
CREATE INDEX ix_external_applications_student_id ON external_applications(student_id);

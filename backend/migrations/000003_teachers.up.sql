-- SQL migration 000003: teachers domain.
--
-- Source of truth for: teachers, teacher_qualifications,
-- teacher_certificates, teacher_programs.
-- Replaces Alembic 7f3a1c9e2b02.
--
-- FK policies (verbatim):
-- * teachers.university_id -> RESTRICT
-- * qualifications/certificates -> teacher CASCADE
-- * certificates.program_id -> SET NULL
-- * teacher_programs.teacher_id -> CASCADE, program_id -> RESTRICT
-- NOTE: readiness composite indexes (teacher_id, expires_at) live in
-- 000008_readiness_perf_indexes (Alembic 7f3a1c9e2b06), not here.

CREATE TABLE teachers (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    full_name VARCHAR(512) NOT NULL,
    email VARCHAR(512) NOT NULL,
    phone VARCHAR(64),
    "position" VARCHAR(256) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_teachers PRIMARY KEY (id),
    CONSTRAINT uq_teachers_email UNIQUE (email),
    CONSTRAINT fk_teachers_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE RESTRICT
);
CREATE INDEX ix_teachers_university_id ON teachers USING btree (university_id);

CREATE TABLE teacher_qualifications (
    id UUID NOT NULL,
    teacher_id UUID NOT NULL,
    qualification_name VARCHAR(512) NOT NULL,
    obtained_at DATE NOT NULL,
    expires_at DATE,
    document_ref VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_teacher_qualifications PRIMARY KEY (id),
    CONSTRAINT fk_teacher_qualifications_teacher_id_teachers
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE
);
CREATE INDEX ix_teacher_qualifications_teacher_id ON teacher_qualifications USING btree (teacher_id);

CREATE TABLE teacher_certificates (
    id UUID NOT NULL,
    teacher_id UUID NOT NULL,
    certificate_name VARCHAR(512) NOT NULL,
    issued_by VARCHAR(512) NOT NULL DEFAULT '',
    issued_at DATE NOT NULL,
    expires_at DATE,
    is_mandatory BOOLEAN NOT NULL DEFAULT FALSE,
    program_id UUID,
    document_ref VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_teacher_certificates PRIMARY KEY (id),
    CONSTRAINT fk_teacher_certificates_teacher_id_teachers
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE,
    CONSTRAINT fk_teacher_certificates_program_id_it_programs
        FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE SET NULL
);
CREATE INDEX ix_teacher_certificates_teacher_id ON teacher_certificates USING btree (teacher_id);
CREATE INDEX ix_teacher_certificates_expires_at ON teacher_certificates USING btree (expires_at);
CREATE INDEX ix_teacher_certificates_mandatory ON teacher_certificates USING btree (is_mandatory, expires_at);

CREATE TABLE teacher_programs (
    id UUID NOT NULL,
    teacher_id UUID NOT NULL,
    program_id UUID NOT NULL,
    can_teach BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_at DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_teacher_programs PRIMARY KEY (id),
    CONSTRAINT uq_teacher_programs_teacher_program UNIQUE (teacher_id, program_id),
    CONSTRAINT fk_teacher_programs_teacher_id_teachers
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE,
    CONSTRAINT fk_teacher_programs_program_id_it_programs
        FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE RESTRICT
);
CREATE INDEX ix_teacher_programs_teacher_id ON teacher_programs USING btree (teacher_id);
CREATE INDEX ix_teacher_programs_program_id ON teacher_programs USING btree (program_id);

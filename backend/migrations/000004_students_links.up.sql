-- SQL migration 000004: students + university links.
--
-- Source of truth for: students, university_programs, university_products.
-- Replaces Alembic 7f3a1c9e2b03 (first part).
--
-- FK policies (verbatim):
-- * students -> RESTRICT on both sides
-- * university_programs.university_id -> CASCADE, program_id -> RESTRICT,
--   responsible_id -> SET NULL
-- * university_products.university_id -> CASCADE, product_id -> RESTRICT,
--   license_id -> SET NULL

CREATE TABLE students (
    id UUID NOT NULL,
    external_id VARCHAR(256) NOT NULL,
    university_id UUID NOT NULL,
    program_id UUID NOT NULL,
    full_name VARCHAR(512) NOT NULL,
    group_name VARCHAR(256),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    started_at DATE NOT NULL,
    finished_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_students PRIMARY KEY (id),
    CONSTRAINT uq_students_external_id UNIQUE (external_id),
    CONSTRAINT fk_students_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE RESTRICT,
    CONSTRAINT fk_students_program_id_it_programs
        FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE RESTRICT
);
CREATE INDEX ix_students_university_id ON students USING btree (university_id);
CREATE INDEX ix_students_program_id ON students USING btree (program_id);
CREATE INDEX ix_students_status ON students USING btree (status);

CREATE TABLE university_programs (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    program_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'planned',
    launch_date DATE,
    responsible_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_university_programs PRIMARY KEY (id),
    CONSTRAINT uq_university_programs_uni_prog UNIQUE (university_id, program_id),
    CONSTRAINT fk_university_programs_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_university_programs_program_id_it_programs
        FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE RESTRICT,
    CONSTRAINT fk_university_programs_responsible_id_responsibles
        FOREIGN KEY (responsible_id) REFERENCES responsibles (id) ON DELETE SET NULL
);
CREATE INDEX ix_univ_programs_university_id ON university_programs USING btree (university_id);
CREATE INDEX ix_univ_programs_program_id ON university_programs USING btree (program_id);
CREATE INDEX ix_univ_programs_status ON university_programs USING btree (status);

CREATE TABLE university_products (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    product_id UUID NOT NULL,
    license_id UUID,
    status VARCHAR(32) NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_university_products PRIMARY KEY (id),
    CONSTRAINT uq_university_products_uni_prod UNIQUE (university_id, product_id),
    CONSTRAINT fk_university_products_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_university_products_product_id_it_products
        FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE RESTRICT,
    CONSTRAINT fk_university_products_license_id_licenses
        FOREIGN KEY (license_id) REFERENCES licenses (id) ON DELETE SET NULL
);
CREATE INDEX ix_univ_products_university_id ON university_products USING btree (university_id);
CREATE INDEX ix_univ_products_product_id ON university_products USING btree (product_id);

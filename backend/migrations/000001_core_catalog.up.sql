-- SQL migration 000001: core catalog (root tables, no dependencies).
--
-- Source of truth for: universities, it_directions, it_programs,
-- vendors, it_products, responsibles.
-- Replaces Alembic 7f3a1c9e2b01 (catalog part).
--
-- Conventions (match the Alembic-head baseline exactly):
-- * UUID PKs are client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * created_at/updated_at are TIMESTAMPTZ NOT NULL DEFAULT now().
--   Python-side default=/onupdate= are runtime behaviour only, not schema.
-- * Python-side default="" / False / True become SQL DEFAULT only where the
--   real PostgreSQL schema already has them (see pg_dump baseline).
-- * FK ON DELETE policies preserved verbatim (RESTRICT where set).
-- * No native ENUM types: all statuses are VARCHAR (no CHECK by design;
--   transfer_status_raw hardening is a future DATA INTEGRITY task).
-- * No extensions required (uuid/timestamptz/jsonb are built-in; plpgsql only).

CREATE TABLE universities (
    id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    city VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_universities PRIMARY KEY (id),
    CONSTRAINT uq_universities_name UNIQUE (name)
);
CREATE INDEX ix_universities_name ON universities USING btree (name);
CREATE INDEX ix_universities_city ON universities USING btree (city);

CREATE TABLE it_directions (
    id UUID NOT NULL,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_it_directions PRIMARY KEY (id),
    CONSTRAINT uq_it_directions_code UNIQUE (code)
);

CREATE TABLE it_programs (
    id UUID NOT NULL,
    direction_id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_it_programs PRIMARY KEY (id),
    CONSTRAINT fk_it_programs_direction_id_it_directions
        FOREIGN KEY (direction_id) REFERENCES it_directions (id) ON DELETE RESTRICT
);
CREATE INDEX ix_it_programs_direction_id ON it_programs USING btree (direction_id);

CREATE TABLE vendors (
    id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_vendors PRIMARY KEY (id),
    CONSTRAINT uq_vendors_name UNIQUE (name)
);

CREATE TABLE it_products (
    id UUID NOT NULL,
    vendor_id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    version VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_it_products PRIMARY KEY (id),
    CONSTRAINT fk_it_products_vendor_id_vendors
        FOREIGN KEY (vendor_id) REFERENCES vendors (id) ON DELETE RESTRICT,
    CONSTRAINT uq_it_products_vendor_name_version UNIQUE (vendor_id, name, version)
);
CREATE INDEX ix_it_products_vendor_id ON it_products USING btree (vendor_id);

CREATE TABLE responsibles (
    id UUID NOT NULL,
    full_name VARCHAR(512) NOT NULL,
    email VARCHAR(512) NOT NULL,
    phone VARCHAR(64),
    role VARCHAR(256) NOT NULL DEFAULT '',
    keycloak_sub VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_responsibles PRIMARY KEY (id),
    CONSTRAINT uq_responsibles_email UNIQUE (email),
    CONSTRAINT uq_responsibles_keycloak_sub UNIQUE (keycloak_sub)
);

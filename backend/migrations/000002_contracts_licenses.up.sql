-- SQL migration 000002: contracts, licenses, university_responsibles.
--
-- Source of truth for: contracts, licenses, university_responsibles.
-- Replaces Alembic 7f3a1c9e2b01 (contracts/licenses part).
--
-- FK policies (verbatim from baseline):
-- * contracts.university_id -> RESTRICT, contracts.product_id -> SET NULL
-- * licenses.university_id/product_id -> RESTRICT, licenses.contract_id -> SET NULL
-- * university_responsibles both sides -> CASCADE
-- transfer_status_raw stays VARCHAR WITHOUT CHECK (see DATA INTEGRITY HARDENING TODO).

CREATE TABLE contracts (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    contract_number VARCHAR(256) NOT NULL,
    product_id UUID,
    signed_at DATE NOT NULL,
    expires_at DATE,
    status_raw VARCHAR(32) NOT NULL DEFAULT 'signed',
    transfer_status_raw VARCHAR(32) NOT NULL DEFAULT 'pending',
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_contracts PRIMARY KEY (id),
    CONSTRAINT uq_contracts_contract_number UNIQUE (contract_number),
    CONSTRAINT fk_contracts_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE RESTRICT,
    CONSTRAINT fk_contracts_product_id_it_products
        FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE SET NULL
);
CREATE INDEX ix_contracts_university_id ON contracts USING btree (university_id);
CREATE INDEX ix_contracts_expires_at ON contracts USING btree (expires_at);

CREATE TABLE licenses (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    product_id UUID NOT NULL,
    contract_id UUID,
    license_number VARCHAR(256) NOT NULL,
    signed_at DATE NOT NULL,
    expires_at DATE NOT NULL,
    transfer_status_raw VARCHAR(32) NOT NULL DEFAULT 'pending',
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_licenses PRIMARY KEY (id),
    CONSTRAINT fk_licenses_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE RESTRICT,
    CONSTRAINT fk_licenses_product_id_it_products
        FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE RESTRICT,
    CONSTRAINT fk_licenses_contract_id_contracts
        FOREIGN KEY (contract_id) REFERENCES contracts (id) ON DELETE SET NULL
);
CREATE INDEX ix_licenses_university_id ON licenses USING btree (university_id);
CREATE INDEX ix_licenses_product_id ON licenses USING btree (product_id);
CREATE INDEX ix_licenses_expires_at ON licenses USING btree (expires_at);
CREATE INDEX ix_licenses_transfer_status_raw ON licenses USING btree (transfer_status_raw);
CREATE INDEX ix_licenses_univ_expires ON licenses USING btree (university_id, expires_at);

CREATE TABLE university_responsibles (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    responsible_id UUID NOT NULL,
    role_in_university VARCHAR(64),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_university_responsibles PRIMARY KEY (id),
    CONSTRAINT uq_university_responsibles_uni_resp UNIQUE (university_id, responsible_id),
    CONSTRAINT fk_university_responsibles_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_university_responsibles_responsible_id_responsibles
        FOREIGN KEY (responsible_id) REFERENCES responsibles (id) ON DELETE CASCADE
);
CREATE INDEX ix_university_responsibles_university_id ON university_responsibles USING btree (university_id);
CREATE INDEX ix_university_responsibles_responsible_id ON university_responsibles USING btree (responsible_id);

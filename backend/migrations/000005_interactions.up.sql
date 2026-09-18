-- SQL migration 000005: meetings, documents, notes, meeting_documents.
--
-- Source of truth for: meetings, documents, interaction_notes,
-- meeting_documents.
-- Replaces Alembic 7f3a1c9e2b03 (second part).
--
-- FK policies (verbatim):
-- * meetings/interaction_notes -> universities CASCADE
-- * documents.university_id -> CASCADE, license_id/contract_id -> SET NULL
-- * meeting_documents both sides -> CASCADE
-- CHECK quirk preserved: the real DB constraint is named
--   ck_documents_ck_documents_single_link (doubled prefix produced by the
--   SQLAlchemy naming convention on top of the declared
--   ck_documents_single_link). The doubled name is kept verbatim so
--   pg_dump equivalence holds; see SCHEMA DISCREPANCIES doc.
-- NOTE: passport composite indexes (documents/interaction_notes univ_created)
-- live in 000007 (Alembic 7f3a1c9e2b05), not here.

CREATE TABLE meetings (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    meeting_type VARCHAR(32) NOT NULL DEFAULT 'online',
    subject VARCHAR(1024) NOT NULL,
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome TEXT,
    next_action TEXT,
    next_action_due DATE,
    meeting_at TIMESTAMPTZ NOT NULL,
    created_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_meetings PRIMARY KEY (id),
    CONSTRAINT fk_meetings_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
);
CREATE INDEX ix_meetings_university_id ON meetings USING btree (university_id);
CREATE INDEX ix_meetings_meeting_at ON meetings USING btree (meeting_at);
CREATE INDEX ix_meetings_univ_meeting_at ON meetings USING btree (university_id, meeting_at);

CREATE TABLE documents (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    document_type VARCHAR(32) NOT NULL,
    title VARCHAR(1024) NOT NULL,
    file_path VARCHAR(1024) NOT NULL,
    file_name VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    mime_type VARCHAR(128) NOT NULL DEFAULT '',
    license_id UUID,
    contract_id UUID,
    signed_at DATE,
    expires_at DATE,
    status_raw VARCHAR(32) NOT NULL DEFAULT 'draft',
    uploaded_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_documents PRIMARY KEY (id),
    CONSTRAINT fk_documents_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_documents_license_id_licenses
        FOREIGN KEY (license_id) REFERENCES licenses (id) ON DELETE SET NULL,
    CONSTRAINT fk_documents_contract_id_contracts
        FOREIGN KEY (contract_id) REFERENCES contracts (id) ON DELETE SET NULL,
    CONSTRAINT ck_documents_ck_documents_single_link
        CHECK (NOT ((license_id IS NOT NULL) AND (contract_id IS NOT NULL)))
);
CREATE INDEX ix_documents_university_id ON documents USING btree (university_id);
CREATE INDEX ix_documents_status_raw ON documents USING btree (status_raw);
CREATE INDEX ix_documents_license_id ON documents USING btree (license_id);
CREATE INDEX ix_documents_contract_id ON documents USING btree (contract_id);
CREATE INDEX ix_documents_expires_at ON documents USING btree (expires_at);

CREATE TABLE interaction_notes (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    author_keycloak_sub VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_interaction_notes PRIMARY KEY (id),
    CONSTRAINT fk_interaction_notes_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE
);
CREATE INDEX ix_interaction_notes_university_id ON interaction_notes USING btree (university_id);
CREATE INDEX ix_interaction_notes_created_at ON interaction_notes USING btree (created_at);

CREATE TABLE meeting_documents (
    id UUID NOT NULL,
    meeting_id UUID NOT NULL,
    document_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_meeting_documents PRIMARY KEY (id),
    CONSTRAINT uq_meeting_documents_meeting_document UNIQUE (meeting_id, document_id),
    CONSTRAINT fk_meeting_documents_meeting_id_meetings
        FOREIGN KEY (meeting_id) REFERENCES meetings (id) ON DELETE CASCADE,
    CONSTRAINT fk_meeting_documents_document_id_documents
        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);
CREATE INDEX ix_meeting_documents_meeting_id ON meeting_documents USING btree (meeting_id);
CREATE INDEX ix_meeting_documents_document_id ON meeting_documents USING btree (document_id);

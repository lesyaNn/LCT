-- SQL migration 000006: audit_events.
--
-- Source of truth for: audit_events (+ audit_events_id_seq).
-- Replaces Alembic 7f3a1c9e2b04.
--
-- Notes:
-- * Legacy Integer PK with sequence audit_events_id_seq (SERIAL semantics).
-- * Legacy entity_type/entity_id are INTEGER (incompatible with UUID
--   universities by design); per-university attribution uses nullable
--   university_id UUID -> universities.id ON DELETE SET NULL.
-- * before_data/after_data/ip_address keep DB DEFAULTs '{}'/'{}'/''.
-- * This is the ONLY append-only log table in scope. Keycloak tables are
--   out of scope (separate `keycloak` database, Liquibase-managed).
-- * health_score_history is intentionally NOT created here: the model has
--   an int->UUID FK mismatch and the table was never in the Alembic head.

CREATE TABLE audit_events (
    id SERIAL NOT NULL,
    user_id INTEGER NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    entity_id INTEGER NOT NULL,
    action VARCHAR(32) NOT NULL,
    before_data TEXT NOT NULL DEFAULT '{}',
    after_data TEXT NOT NULL DEFAULT '{}',
    ip_address VARCHAR(64) NOT NULL DEFAULT '',
    university_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_audit_events PRIMARY KEY (id),
    CONSTRAINT fk_audit_events_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE SET NULL
);
CREATE INDEX ix_audit_events_university_id ON audit_events USING btree (university_id);
CREATE INDEX ix_audit_events_univ_created ON audit_events USING btree (university_id, created_at);

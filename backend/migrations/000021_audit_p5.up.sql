-- CANONICAL_NAME_COMPATIBILITY: evolve P1 audit_events, never create audit_logs.
-- Existing integer identities are deterministically mapped to UUIDs.
ALTER TABLE audit_events DROP CONSTRAINT fk_audit_events_university_id_universities;
ALTER TABLE audit_events DROP CONSTRAINT pk_audit_events;
ALTER TABLE audit_events ALTER COLUMN id DROP DEFAULT;
ALTER TABLE audit_events ALTER COLUMN id TYPE UUID
    USING md5('audit-event:' || id::text)::uuid;
ALTER TABLE audit_events ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);
DROP SEQUENCE IF EXISTS audit_events_id_seq;

ALTER TABLE audit_events ALTER COLUMN entity_id TYPE UUID USING (
    CASE WHEN entity_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         THEN entity_id::uuid ELSE md5('audit-entity:' || entity_id)::uuid END
);
ALTER TABLE audit_events RENAME COLUMN before_data TO old_value;
ALTER TABLE audit_events RENAME COLUMN after_data TO new_value;
ALTER TABLE audit_events ALTER COLUMN old_value DROP DEFAULT;
ALTER TABLE audit_events ALTER COLUMN new_value DROP DEFAULT;
ALTER TABLE audit_events ALTER COLUMN old_value TYPE JSONB USING old_value::jsonb;
ALTER TABLE audit_events ALTER COLUMN new_value TYPE JSONB USING new_value::jsonb;
ALTER TABLE audit_events ALTER COLUMN old_value DROP NOT NULL;
ALTER TABLE audit_events ALTER COLUMN new_value DROP NOT NULL;
ALTER TABLE audit_events ADD COLUMN user_name VARCHAR(512) NOT NULL DEFAULT '';
ALTER TABLE audit_events ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'user';
ALTER TABLE audit_events ADD COLUMN request_id UUID;
ALTER TABLE audit_events ADD COLUMN user_agent TEXT;
ALTER TABLE audit_events ALTER COLUMN ip_address TYPE VARCHAR(45);
ALTER TABLE audit_events ALTER COLUMN ip_address DROP NOT NULL;
ALTER TABLE audit_events ALTER COLUMN ip_address DROP DEFAULT;
UPDATE audit_events SET action = upper(action);
CREATE INDEX ix_audit_events_created_desc ON audit_events (created_at DESC);
CREATE INDEX ix_audit_events_user_id ON audit_events (user_id);
CREATE INDEX ix_audit_events_entity ON audit_events (entity_type, entity_id);
CREATE INDEX ix_audit_events_action ON audit_events (action);
CREATE INDEX ix_audit_events_request_id ON audit_events (request_id);

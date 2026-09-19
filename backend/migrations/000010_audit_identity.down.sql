-- Rollback for 000010_audit_identity.
--
-- Non-numeric identities (Keycloak subs, UUIDs) cannot go back to
-- INTEGER and are mapped to 0; numeric values round-trip exactly.

ALTER TABLE audit_events
    ALTER COLUMN user_id TYPE INTEGER
        USING (CASE WHEN user_id ~ '^[0-9]+$' THEN user_id::integer ELSE 0 END),
    ALTER COLUMN entity_id TYPE INTEGER
        USING (CASE WHEN entity_id ~ '^[0-9]+$' THEN entity_id::integer ELSE 0 END);

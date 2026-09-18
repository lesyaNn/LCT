-- SQL migration 000010: audit identity columns as TEXT.
--
-- Why: Keycloak `sub` (str/UUID) and UUID entity ids do not fit INTEGER.
-- user_id/entity_id become TEXT; existing integer values are preserved
-- via USING ...::text. id stays SERIAL (see 000006).

ALTER TABLE audit_events
    ALTER COLUMN user_id TYPE TEXT USING user_id::text,
    ALTER COLUMN entity_id TYPE TEXT USING entity_id::text;

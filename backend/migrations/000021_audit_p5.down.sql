-- Restore P1 physical schema for a down/up verification cycle.
DROP INDEX ix_audit_events_request_id;
DROP INDEX ix_audit_events_action;
DROP INDEX ix_audit_events_entity;
DROP INDEX ix_audit_events_user_id;
DROP INDEX ix_audit_events_created_desc;
ALTER TABLE audit_events DROP COLUMN user_agent;
ALTER TABLE audit_events DROP COLUMN request_id;
ALTER TABLE audit_events DROP COLUMN role;
ALTER TABLE audit_events DROP COLUMN user_name;
UPDATE audit_events SET old_value = '{}'::jsonb WHERE old_value IS NULL;
UPDATE audit_events SET new_value = '{}'::jsonb WHERE new_value IS NULL;
ALTER TABLE audit_events ALTER COLUMN old_value TYPE TEXT USING old_value::text;
ALTER TABLE audit_events ALTER COLUMN new_value TYPE TEXT USING new_value::text;
ALTER TABLE audit_events ALTER COLUMN old_value SET NOT NULL;
ALTER TABLE audit_events ALTER COLUMN new_value SET NOT NULL;
ALTER TABLE audit_events ALTER COLUMN old_value SET DEFAULT '{}';
ALTER TABLE audit_events ALTER COLUMN new_value SET DEFAULT '{}';
ALTER TABLE audit_events RENAME COLUMN old_value TO before_data;
ALTER TABLE audit_events RENAME COLUMN new_value TO after_data;
ALTER TABLE audit_events ALTER COLUMN entity_id TYPE TEXT USING entity_id::text;
ALTER TABLE audit_events ALTER COLUMN ip_address TYPE VARCHAR(64);
UPDATE audit_events SET ip_address = '' WHERE ip_address IS NULL;
ALTER TABLE audit_events ALTER COLUMN ip_address SET NOT NULL;
ALTER TABLE audit_events ALTER COLUMN ip_address SET DEFAULT '';
ALTER TABLE audit_events DROP CONSTRAINT pk_audit_events;
ALTER TABLE audit_events DROP COLUMN id;
ALTER TABLE audit_events ADD COLUMN id INTEGER;
CREATE SEQUENCE audit_events_id_seq OWNED BY audit_events.id;
ALTER TABLE audit_events ALTER COLUMN id SET DEFAULT nextval('audit_events_id_seq');
UPDATE audit_events SET id = nextval('audit_events_id_seq');
ALTER TABLE audit_events ALTER COLUMN id SET NOT NULL;
ALTER TABLE audit_events ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);
UPDATE audit_events AS a SET university_id = NULL
WHERE university_id IS NOT NULL AND NOT EXISTS
    (SELECT 1 FROM universities AS u WHERE u.id = a.university_id);
ALTER TABLE audit_events ADD CONSTRAINT fk_audit_events_university_id_universities
    FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE SET NULL;

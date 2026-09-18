-- Rollback for 000009_license_row_links.

DROP INDEX IF EXISTS ix_licenses_direction_id;
DROP INDEX IF EXISTS ix_licenses_program_id;
ALTER TABLE licenses DROP CONSTRAINT IF EXISTS fk_licenses_direction_id_it_directions;
ALTER TABLE licenses DROP CONSTRAINT IF EXISTS fk_licenses_program_id_it_programs;
ALTER TABLE licenses DROP COLUMN IF EXISTS direction_id;
ALTER TABLE licenses DROP COLUMN IF EXISTS program_id;

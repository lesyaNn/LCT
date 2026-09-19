-- SQL migration 000009: per-row program/direction on licenses.
--
-- Source of truth for: licenses.program_id, licenses.direction_id.
-- One import row = one contract/license for one product for one university,
-- and the row's direction/program is stored on the license itself.
-- it_programs stays workflow-owned: import creates programs/links only
-- when a program column is mapped, never synthesizes them.
--
-- FK policies: program_id/direction_id -> SET NULL (deleting a program or
-- direction must not delete licenses).

ALTER TABLE licenses ADD COLUMN program_id UUID;
ALTER TABLE licenses ADD COLUMN direction_id UUID;
ALTER TABLE licenses ADD CONSTRAINT fk_licenses_program_id_it_programs
    FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE SET NULL;
ALTER TABLE licenses ADD CONSTRAINT fk_licenses_direction_id_it_directions
    FOREIGN KEY (direction_id) REFERENCES it_directions (id) ON DELETE SET NULL;
CREATE INDEX ix_licenses_program_id ON licenses USING btree (program_id);
CREATE INDEX ix_licenses_direction_id ON licenses USING btree (direction_id);

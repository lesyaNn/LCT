DROP TABLE external_sync_states;
DROP TABLE external_applications;
ALTER TABLE students DROP CONSTRAINT ck_students_progress_range;
ALTER TABLE students DROP COLUMN synced_at;
ALTER TABLE students DROP COLUMN progress;
ALTER TABLE students DROP COLUMN source;

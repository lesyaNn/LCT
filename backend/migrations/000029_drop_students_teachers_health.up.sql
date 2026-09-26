-- Remove students / teachers / health-score entities.
ALTER TABLE external_applications DROP COLUMN IF EXISTS student_id;
DROP TABLE IF EXISTS health_score_current;
DROP TABLE IF EXISTS health_score_snapshots;
DROP TABLE IF EXISTS teacher_programs;
DROP TABLE IF EXISTS teacher_certificates;
DROP TABLE IF EXISTS teacher_qualifications;
DROP TABLE IF EXISTS teachers;
DROP TABLE IF EXISTS students;

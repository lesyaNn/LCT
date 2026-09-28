DROP INDEX IF EXISTS ix_external_applications_student_id;
ALTER TABLE external_applications DROP COLUMN IF EXISTS student_id;
DROP TABLE IF EXISTS teacher_programs;
DROP TABLE IF EXISTS teacher_certificates;
DROP TABLE IF EXISTS teacher_qualifications;
DROP TABLE IF EXISTS teachers;
DROP TABLE IF EXISTS students;

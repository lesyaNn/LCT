-- Rollback for 000008_readiness_perf_indexes.

DROP INDEX IF EXISTS ix_teacher_qualifications_teacher_expires;
DROP INDEX IF EXISTS ix_teacher_certificates_teacher_expires;

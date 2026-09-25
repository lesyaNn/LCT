-- Rollback for 000018_report_jobs.

DROP INDEX IF EXISTS ix_report_jobs_expires_at;
DROP INDEX IF EXISTS ix_report_jobs_created_at;
DROP INDEX IF EXISTS ix_report_jobs_status;
DROP INDEX IF EXISTS ix_report_jobs_actor_sub;
DROP TABLE IF EXISTS report_jobs;

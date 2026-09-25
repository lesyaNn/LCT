ALTER TABLE report_jobs DROP COLUMN idempotency_key;
ALTER TABLE report_jobs DROP COLUMN result;
ALTER TABLE report_jobs DROP COLUMN payload;
ALTER TABLE report_jobs DROP COLUMN job_type;
DROP INDEX IF EXISTS uq_report_jobs_idempotency;
DROP INDEX IF EXISTS ix_report_jobs_type_status;

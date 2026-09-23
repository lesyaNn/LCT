-- SQL migration 000020: report job attempts for worker retries (P4-06-01).
--
-- The spec requires up to 3 attempts before a job goes failed: the worker
-- atomically claims (queued -> building) and increments attempts; a failed
-- attempt with attempts < 3 is requeued, otherwise the job is failed.
-- Additive only: no earlier migration file is modified.

ALTER TABLE report_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

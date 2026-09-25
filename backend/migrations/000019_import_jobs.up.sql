-- SQL migration 000019: import jobs on the shared report_jobs ledger (Dev-3).
--
-- P4-10-01 requires import jobs ("job_id (как reports)", dependency on
-- P4-06-01): instead of the ephemeral task_queue stub, POST /import/execute
-- now persists rows in report_jobs. Four additive columns:
-- * job_type VARCHAR(32) DEFAULT 'report' ('report' | 'xlsx_import');
-- * payload JSONB DEFAULT '{}' — worker params (file_id/mapping/options);
-- * result JSONB — terminal summary (inserted/updated/skipped/errors);
-- * idempotency_key VARCHAR(64) — re-POST dedup (partial unique index).
--
-- Dev-1 report rows are unaffected (job_type defaults to 'report').
-- Additive only: no earlier migration file is modified.

ALTER TABLE report_jobs ADD COLUMN job_type VARCHAR(32) NOT NULL DEFAULT 'report';
ALTER TABLE report_jobs ADD COLUMN payload JSONB NOT NULL DEFAULT '{}';
ALTER TABLE report_jobs ADD COLUMN result JSONB;
ALTER TABLE report_jobs ADD COLUMN idempotency_key VARCHAR(64);

CREATE INDEX ix_report_jobs_type_status ON report_jobs USING btree (job_type, status);
CREATE UNIQUE INDEX uq_report_jobs_idempotency ON report_jobs USING btree (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

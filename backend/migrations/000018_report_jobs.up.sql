-- P4-06-01: additive Dev-2 job state; no changes to Dev-1/Dev-3 tables.
CREATE TABLE report_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    user_name VARCHAR(255) NOT NULL,
    university_id UUID,
    scope_ids JSONB,
    format VARCHAR(10) NOT NULL,
    filters JSONB NOT NULL,
    columns JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    file_path VARCHAR(500),
    file_size BIGINT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
    CONSTRAINT ck_report_jobs_status CHECK (status IN ('queued','building','ready','failed')),
    CONSTRAINT ck_report_jobs_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT ck_report_jobs_format CHECK (format IN ('xlsx','pdf','json'))
);
CREATE INDEX ix_report_jobs_user ON report_jobs(user_id);
CREATE INDEX ix_report_jobs_status_created ON report_jobs(status, created_at);
CREATE INDEX ix_report_jobs_expires ON report_jobs(expires_at);

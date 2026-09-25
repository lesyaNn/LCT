-- SQL migration 000018: report_jobs (P4-06-01).
--
-- Source of truth for: report_jobs (async analytics report execution).
--
-- Notes:
-- * UUID PK client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * format is VARCHAR(16) (xlsx/pdf/json); no native ENUM (P1 convention).
-- * filters/columns are JSONB snapshots of the validated request: the worker
--   rehydrates them instead of trusting a changed client request.
-- * Security snapshot is canonical multi-scope (NOT a single legacy
--   university_id): actor_sub + actor_roles (JSONB) + effective_university_ids
--   (JSONB NULL = global/admin scope, [] = empty scope, fail closed).
--   A single legacy university_id column would lose the multi-university
--   intersection, so it is deliberately absent.
-- * status is VARCHAR(16) with a CHECK (queued/building/ready/failed only).
-- * progress is INTEGER 0..100 with a CHECK.
-- * expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + 24 hours (tz-aware).
-- * created_at TIMESTAMPTZ NOT NULL DEFAULT now(); started_at/completed_at
--   are filled by the worker lifecycle (queued -> building -> ready/failed).
-- * No FK to a users table: actors are Keycloak subjects (external ids),
--   auth code maps sub -> users.external_id only when PostgreSQL users land.
--
-- Additive only: no earlier migration file is modified.

CREATE TABLE report_jobs (
    id UUID NOT NULL,
    format VARCHAR(16) NOT NULL,
    filters JSONB NOT NULL,
    columns JSONB NOT NULL,
    actor_sub VARCHAR(256) NOT NULL,
    actor_name VARCHAR(512) NOT NULL DEFAULT '',
    actor_roles JSONB NOT NULL DEFAULT '[]',
    effective_university_ids JSONB,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    file_path VARCHAR(1024),
    file_size BIGINT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours'),
    CONSTRAINT pk_report_jobs PRIMARY KEY (id),
    CONSTRAINT ck_report_jobs_status CHECK (status IN ('queued', 'building', 'ready', 'failed')),
    CONSTRAINT ck_report_jobs_progress CHECK (progress >= 0 AND progress <= 100)
);
CREATE INDEX ix_report_jobs_actor_sub ON report_jobs USING btree (actor_sub);
CREATE INDEX ix_report_jobs_status ON report_jobs USING btree (status);
CREATE INDEX ix_report_jobs_created_at ON report_jobs USING btree (created_at DESC);
CREATE INDEX ix_report_jobs_expires_at ON report_jobs USING btree (expires_at);

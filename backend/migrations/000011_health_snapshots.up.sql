-- SQL migration 000011: health_score_snapshots (P2-09-01).
--
-- Source of truth for: health_score_snapshots.
-- Replaces Alembic b2c909010901 (same DDL, same names).
--
-- Notes:
-- * UUID PK client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * university_id UUID NOT NULL -> universities.id ON DELETE CASCADE.
-- * status is VARCHAR(16) (green/yellow/red); no native ENUM (P1 convention).
-- * breakdown/reasons are JSONB NOT NULL DEFAULT '{}'/'[]'.
-- * calculated_at TIMESTAMPTZ NOT NULL (no DEFAULT: writer sets now()).
-- * period_day DATE NOT NULL (calculated_at::date, cron idempotency).
-- * trigger_event VARCHAR(64) NOT NULL DEFAULT 'daily_cron'.
-- * Unique (university_id, period_day, trigger_event): cron writes
--   ON CONFLICT DO NOTHING; event snapshots never clash with daily ones.
-- * Endpoint GET .../health-score/history и cron/event писатели — позже,
--   отдельными задачами (здесь только DDL).

CREATE TABLE health_score_snapshots (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    score INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    breakdown JSONB NOT NULL DEFAULT '{}',
    reasons JSONB NOT NULL DEFAULT '[]',
    calculated_at TIMESTAMPTZ NOT NULL,
    period_day DATE NOT NULL,
    trigger_event VARCHAR(64) NOT NULL DEFAULT 'daily_cron',
    CONSTRAINT pk_health_score_snapshots PRIMARY KEY (id),
    CONSTRAINT fk_health_snapshots_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT uq_health_snapshots_uni_day_trigger
        UNIQUE (university_id, period_day, trigger_event)
);
CREATE INDEX ix_health_snapshots_university_id ON health_score_snapshots USING btree (university_id);
CREATE INDEX ix_health_snapshots_univ_calculated ON health_score_snapshots USING btree (university_id, calculated_at DESC);

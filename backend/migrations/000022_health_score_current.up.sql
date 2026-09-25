-- Materialized output of the canonical Python Health Score calculator.
CREATE TABLE health_score_current (
    university_id UUID PRIMARY KEY REFERENCES universities(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    status VARCHAR(16) NOT NULL CHECK (status IN ('green', 'yellow', 'red')),
    breakdown JSONB NOT NULL,
    reasons JSONB NOT NULL,
    input_counters JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_health_score_current_score ON health_score_current (score DESC, university_id);
CREATE INDEX ix_health_score_current_status_score ON health_score_current (status, score DESC, university_id);

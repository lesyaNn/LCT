CREATE TABLE health_score_observations (
    id UUID PRIMARY KEY,
    university_id UUID NOT NULL REFERENCES universities (id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    level VARCHAR(16) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_health_score_observations_univ_calculated
    ON health_score_observations (university_id, calculated_at DESC);

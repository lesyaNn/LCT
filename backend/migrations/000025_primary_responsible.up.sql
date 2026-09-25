-- Exactly one primary responsible per university; non-primary links remain historical.
CREATE UNIQUE INDEX uq_university_responsibles_primary
    ON university_responsibles (university_id) WHERE is_primary;

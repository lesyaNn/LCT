-- SQL migration 000007: passport composite ordering indexes.
--
-- Replaces Alembic 7f3a1c9e2b05.
-- Passport blocks filter by university_id and ORDER BY created_at DESC LIMIT n;
-- without these composites the DB sorts per request.
-- No new tuning here: exact index names/columns from the baseline.

CREATE INDEX ix_documents_univ_created ON documents USING btree (university_id, created_at);
CREATE INDEX ix_interaction_notes_univ_created ON interaction_notes USING btree (university_id, created_at);

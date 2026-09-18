-- Rollback for 000007_passport_perf_indexes.

DROP INDEX IF EXISTS ix_interaction_notes_univ_created;
DROP INDEX IF EXISTS ix_documents_univ_created;

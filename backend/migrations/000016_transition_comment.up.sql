-- SQL migration 000016: workflow_stage_transitions.comment (P2-03-03).
--
-- Source of truth for: workflow_stage_transitions.comment.
--
-- B2 transition history must record prev stage + new stage + actor +
-- comment (NOT NULL) + timestamp. The B1 migration 000012 created the
-- history table without a comment column, so this additive migration adds
-- it: existing (creation) rows are backfilled with '' via the column
-- DEFAULT; every B2 transition write provides a real non-empty comment
-- (enforced in the service layer, P2-03-02).
--
-- Additive only: no B1 migration file is modified.

ALTER TABLE workflow_stage_transitions
    ADD COLUMN comment TEXT NOT NULL DEFAULT '';

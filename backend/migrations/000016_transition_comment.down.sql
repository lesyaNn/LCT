-- Rollback for 000016_transition_comment.

ALTER TABLE workflow_stage_transitions DROP COLUMN IF EXISTS comment;

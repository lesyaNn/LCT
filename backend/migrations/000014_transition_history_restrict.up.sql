-- SQL migration 000014: transition history keeps its stage anchors (P2-01-03 fix).
--
-- Defect fixed (baseline failure test_stage_delete_sets_anchors_null): with
-- 000012 semantics (from_stage_id / to_stage_id ON DELETE SET NULL) deleting
-- a referenced workflow_stages row NULLs BOTH anchors of a middle transition
-- (from = X, to = X-adjacent rows pointing at the same deleted stage, or any
-- transition whose both sides reference the one deleted row), which trips the
-- CHECK has_side violation (from AND to cannot both be NULL). The schema
-- contradicted itself: the FK policy manufactured the exact row state the
-- CHECK forbids.
--
-- Chosen fix: ON DELETE RESTRICT on BOTH transition anchors (creation =
-- NULL from_stage_id and closure = NULL to_stage_id stay legal single-NULL
-- states; only the deletion of a *referenced* stage is refused). Rationale:
-- * Transition history is the audit trail (previous stage + new stage +
--   actor + timestamp). NULLing an anchor destroys the trail; RESTRICT keeps
--   every recorded move intact.
-- * It mirrors the already-canonical parent rule in 000012 (template with
--   live instances -> RESTRICT; disable via is_active instead). Same rule
--   here: a stage with recorded history is retired via is_active = FALSE,
--   not via DELETE.
-- * Operational pointers keep SET NULL on purpose: workflow_instances.
--   current_stage_id, comments/attachments/tasks stage_id and
--   instance_stages.template_stage_id are single nullable anchors with no
--   CHECK over pairs, so stage removal there degrades gracefully and the
--   snapshot columns preserve runtime history. Only the paired-anchor
--   history table needs RESTRICT.
--
-- No CHECK change: has_side stays exactly as in 000012 (creation/closure
-- single-NULL legal, double-NULL rejected). No data migration: existing rows
-- are untouched; only the FK delete rule changes.
-- Does NOT touch 000011 or 000012 files.

ALTER TABLE workflow_stage_transitions
    DROP CONSTRAINT fk_workflow_stage_transitions_from_stage_id_workflow_stages;
ALTER TABLE workflow_stage_transitions
    ADD CONSTRAINT fk_workflow_stage_transitions_from_stage_id_workflow_stages
        FOREIGN KEY (from_stage_id) REFERENCES workflow_stages (id) ON DELETE RESTRICT;
ALTER TABLE workflow_stage_transitions
    DROP CONSTRAINT fk_workflow_stage_transitions_to_stage_id_workflow_stages;
ALTER TABLE workflow_stage_transitions
    ADD CONSTRAINT fk_workflow_stage_transitions_to_stage_id_workflow_stages
        FOREIGN KEY (to_stage_id) REFERENCES workflow_stages (id) ON DELETE RESTRICT;

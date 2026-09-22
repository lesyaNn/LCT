-- SQL migration 000014 DOWN: restore the 000012 transition FK policy.
-- Reverts both transition anchors to ON DELETE SET NULL (re-exposes the
-- has_side contradiction fixed in UP; kept only as a mechanical rollback).

ALTER TABLE workflow_stage_transitions
    DROP CONSTRAINT fk_workflow_stage_transitions_from_stage_id_workflow_stages;
ALTER TABLE workflow_stage_transitions
    ADD CONSTRAINT fk_workflow_stage_transitions_from_stage_id_workflow_stages
        FOREIGN KEY (from_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL;
ALTER TABLE workflow_stage_transitions
    DROP CONSTRAINT fk_workflow_stage_transitions_to_stage_id_workflow_stages;
ALTER TABLE workflow_stage_transitions
    ADD CONSTRAINT fk_workflow_stage_transitions_to_stage_id_workflow_stages
        FOREIGN KEY (to_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL;

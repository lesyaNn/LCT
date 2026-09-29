ALTER TABLE instance_stages ADD COLUMN started_at TIMESTAMPTZ;

-- Existing transitions record each entry into a stage, including returns.
-- Reopened future stages remain unset until they become current again.
UPDATE instance_stages AS stage
SET started_at = COALESCE(
    (
        SELECT MAX(movement.created_at)
        FROM workflow_stage_transitions AS movement
        WHERE movement.instance_id = stage.instance_id
          AND movement.to_stage_id = stage.template_stage_id
    ),
    CASE WHEN stage.id = instance.current_instance_stage_id
              AND stage.order_index = 1
         THEN instance.created_at END
)
FROM workflow_instances AS instance
WHERE stage.instance_id = instance.id
  AND (stage.status = 'completed' OR stage.id = instance.current_instance_stage_id);

-- SQL migration 000011 DOWN: remove P2 workflow template schema.
-- Dependency order: stages (child) first, then templates (parent).
-- No CASCADE: nothing else references these tables.

DROP TABLE workflow_stages;
DROP TABLE workflow_templates;

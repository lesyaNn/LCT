-- SQL migration 000012 DOWN: remove P2 workflow instances pipeline.
-- Dependency order: children (transitions/comments/attachments/tasks)
-- first, then workflow_instances. No CASCADE: nothing outside 000012
-- references these tables.

DROP TABLE workflow_tasks;
DROP TABLE workflow_attachments;
DROP TABLE workflow_comments;
DROP TABLE workflow_stage_transitions;
DROP TABLE workflow_instances;

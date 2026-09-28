DROP INDEX IF EXISTS ix_workflow_attachments_comment_id;
ALTER TABLE workflow_attachments DROP COLUMN comment_id;

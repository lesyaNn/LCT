ALTER TABLE workflow_attachments ADD COLUMN comment_id UUID NULL;
ALTER TABLE workflow_attachments
    ADD CONSTRAINT fk_workflow_attachments_comment_id_workflow_comments
    FOREIGN KEY (comment_id) REFERENCES workflow_comments(id) ON DELETE SET NULL;

CREATE INDEX ix_workflow_attachments_comment_id ON workflow_attachments(comment_id);

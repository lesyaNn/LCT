-- Existing comments remain ordinary comments; no heuristic backfill.
ALTER TABLE workflow_comments
    ADD COLUMN question_status VARCHAR(16) NOT NULL DEFAULT 'none',
    ADD CONSTRAINT ck_workflow_comments_question_status
        CHECK (question_status IN ('none', 'open', 'resolved'));

CREATE INDEX ix_workflow_comments_open_questions
    ON workflow_comments (instance_id, created_at, id)
    WHERE question_status = 'open';

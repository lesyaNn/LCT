-- Stage 5: optional program binding for the canonical workflow instance.
-- Existing university-level instances remain valid and are not guessed into a program.
ALTER TABLE workflow_instances ADD COLUMN program_id UUID;
ALTER TABLE workflow_instances ADD CONSTRAINT fk_workflow_instances_program_id_it_programs
    FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_workflow_instances_university_program
    ON workflow_instances (university_id, program_id) WHERE program_id IS NOT NULL;
CREATE INDEX ix_workflow_instances_program_id ON workflow_instances (program_id);

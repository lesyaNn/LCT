DROP INDEX IF EXISTS uq_workflow_instances_univ_prog_noprod;
DROP INDEX IF EXISTS uq_workflow_instances_univ_prog_prod;
CREATE UNIQUE INDEX uq_workflow_instances_university_program
    ON workflow_instances (university_id, program_id) WHERE program_id IS NOT NULL;

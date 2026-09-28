-- Restoring the older uniqueness rule requires no duplicate archived bindings.
DROP INDEX uq_workflow_instances_univ_prog_prod;
DROP INDEX uq_workflow_instances_univ_prog_noprod;
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_prod
    ON workflow_instances (university_id, program_id, product_id)
    WHERE program_id IS NOT NULL;
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_noprod
    ON workflow_instances (university_id, program_id)
    WHERE program_id IS NOT NULL AND product_id IS NULL;

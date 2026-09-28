-- Archived workflows retain their records and may be replaced by a new active run.
DROP INDEX uq_workflow_instances_univ_prog_prod;
DROP INDEX uq_workflow_instances_univ_prog_noprod;
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_prod
    ON workflow_instances (university_id, program_id, product_id)
    WHERE program_id IS NOT NULL AND status <> 'archived';
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_noprod
    ON workflow_instances (university_id, program_id)
    WHERE program_id IS NOT NULL AND product_id IS NULL AND status <> 'archived';

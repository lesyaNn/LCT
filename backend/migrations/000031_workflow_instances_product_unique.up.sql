-- Stage 6b: allow several workflows per (university, program) with different
-- prospective products. The old rule (one workflow per program) blocked the
-- direction -> program -> product wizard with 409 UniqueViolation as soon as
-- a second product was chosen for the same program.
--
-- Two partial uniques (NULL product rows never collide with each other in
-- the 3-column index, hence the second one):
-- * (university_id, program_id, product_id) WHERE program_id IS NOT NULL
-- * (university_id, program_id) WHERE program_id IS NOT NULL AND product_id IS NULL
--
-- Safe upgrade: the old 2-column rule is strictly stronger, so no existing
-- row can violate the new rules.
DROP INDEX IF EXISTS uq_workflow_instances_university_program;
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_prod
    ON workflow_instances (university_id, program_id, product_id) WHERE program_id IS NOT NULL;
CREATE UNIQUE INDEX uq_workflow_instances_univ_prog_noprod
    ON workflow_instances (university_id, program_id) WHERE program_id IS NOT NULL AND product_id IS NULL;

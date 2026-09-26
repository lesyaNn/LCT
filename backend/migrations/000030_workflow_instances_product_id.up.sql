-- Stage 6: optional prospective product binding for the workflow instance.
-- The product is chosen for the future (which product to license next);
-- a license is NOT required, so no validation against licenses here.
-- Existing instances remain valid (NULL product). The (university, program)
-- uniqueness is intentionally unchanged: one workflow per program.
ALTER TABLE workflow_instances ADD COLUMN product_id UUID;
ALTER TABLE workflow_instances ADD CONSTRAINT fk_workflow_instances_product_id_it_products
    FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE RESTRICT;
CREATE INDEX ix_workflow_instances_product_id ON workflow_instances (product_id);

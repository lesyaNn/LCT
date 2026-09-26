ALTER TABLE workflow_instances DROP CONSTRAINT IF EXISTS fk_workflow_instances_product_id_it_products;
DROP INDEX IF EXISTS ix_workflow_instances_product_id;
ALTER TABLE workflow_instances DROP COLUMN IF EXISTS product_id;

-- Rollback for 000001_core_catalog: drop root tables in reverse dependency order.

DROP TABLE IF EXISTS responsibles;
DROP TABLE IF EXISTS it_products;
DROP TABLE IF EXISTS vendors;
DROP TABLE IF EXISTS it_programs;
DROP TABLE IF EXISTS it_directions;
DROP TABLE IF EXISTS universities;

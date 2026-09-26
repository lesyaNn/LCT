-- SQL migration 000028: product <-> direction link (import file sheet
-- "Продукт_Направление", many-to-many).
--
-- Source of truth for: product_directions.
--
-- FK policies (catalog protection, cf. 000004 university_products):
-- * product_id -> it_products RESTRICT, direction_id -> it_directions
--   RESTRICT: a product/direction in use cannot be deleted (P1-11-03
--   rule); links are removed explicitly first.
-- * Pair uniqueness: UNIQUE (product_id, direction_id).
--
-- Conventions (match 000001/000004):
-- * UUID PKs are client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * created_at/updated_at are TIMESTAMPTZ NOT NULL DEFAULT now().

CREATE TABLE product_directions (
    id UUID NOT NULL,
    product_id UUID NOT NULL,
    direction_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_product_directions PRIMARY KEY (id),
    CONSTRAINT uq_product_directions_prod_dir UNIQUE (product_id, direction_id),
    CONSTRAINT fk_product_directions_product_id_it_products
        FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE RESTRICT,
    CONSTRAINT fk_product_directions_direction_id_it_directions
        FOREIGN KEY (direction_id) REFERENCES it_directions (id) ON DELETE RESTRICT
);
CREATE INDEX ix_product_directions_product_id ON product_directions USING btree (product_id);
CREATE INDEX ix_product_directions_direction_id ON product_directions USING btree (direction_id);

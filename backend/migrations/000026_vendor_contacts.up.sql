CREATE TABLE vendor_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,
    product_id UUID NOT NULL REFERENCES it_products(id) ON DELETE CASCADE,
    full_name VARCHAR(512) NOT NULL,
    phone VARCHAR(64),
    email VARCHAR(512) NOT NULL,
    communication_method VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_vendor_contacts_product_email UNIQUE (product_id, email)
);
CREATE INDEX ix_vendor_contacts_vendor_id ON vendor_contacts(vendor_id);

ALTER TABLE vendor_contacts ALTER COLUMN product_id DROP NOT NULL;
CREATE UNIQUE INDEX uq_vendor_contacts_vendor_email
    ON vendor_contacts (vendor_id, email) WHERE product_id IS NULL;

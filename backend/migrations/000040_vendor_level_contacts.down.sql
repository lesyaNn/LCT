DELETE FROM vendor_contacts WHERE product_id IS NULL;
DROP INDEX uq_vendor_contacts_vendor_email;
ALTER TABLE vendor_contacts ALTER COLUMN product_id SET NOT NULL;

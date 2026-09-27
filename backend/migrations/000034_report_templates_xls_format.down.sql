-- SQL migration 000034 (down): restore the pre-XLS template format list.

ALTER TABLE report_templates
    DROP CONSTRAINT IF EXISTS ck_report_templates_format;
ALTER TABLE report_templates
    ADD CONSTRAINT ck_report_templates_format
    CHECK (format IN ('xlsx', 'pdf', 'json'));

-- SQL migration 000034: legacy XLS as a stored report template format.
--
-- ТЗ requires the tabular report to export to XLS, XLSX and PDF. The XLS
-- generator landed in app/modules.analytics.xls, so report_templates.format
-- must accept 'xls' — otherwise saving a template in the new format fails
-- with a CHECK violation instead of a clean 422.
--
-- report_jobs.format deliberately has NO CHECK (see 000018): the job
-- lifecycle validates the format in app.modules.analytics.report_service
-- against FORMAT_GENERATORS, which is the single source of truth. Only the
-- templates table duplicated the list, so only it needs the constraint
-- updated here.
--
-- No index changes: this migration is a constraint widening only.

ALTER TABLE report_templates
    DROP CONSTRAINT IF EXISTS ck_report_templates_format;
ALTER TABLE report_templates
    ADD CONSTRAINT ck_report_templates_format
    CHECK (format IN ('xls', 'xlsx', 'pdf', 'json'));

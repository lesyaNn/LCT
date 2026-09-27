-- SQL migration 000032: report_templates (ТЗ §6/§8: сохраняемые шаблоны отчётов).
--
-- Личные шаблоны (owner_sub) + общие от администратора (is_shared).
-- format/filters/columns — тот же замороженный контракт, что у ReportRequest:
-- worker/генераторы их уже умеют валидировать (resolve_columns/UnifiedFilter).
-- Никаких FK на users: владельцы — Keycloak subjects (как у report_jobs).

CREATE TABLE report_templates (
    id UUID NOT NULL,
    name VARCHAR(256) NOT NULL,
    owner_sub VARCHAR(256) NOT NULL,
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    format VARCHAR(16) NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}',
    columns JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_report_templates PRIMARY KEY (id),
    CONSTRAINT ck_report_templates_format CHECK (format IN ('xlsx', 'pdf', 'json')),
    CONSTRAINT ck_report_templates_name CHECK (char_length(name) BETWEEN 1 AND 256)
);
CREATE INDEX ix_report_templates_owner_sub ON report_templates USING btree (owner_sub);
CREATE INDEX ix_report_templates_is_shared ON report_templates USING btree (is_shared);

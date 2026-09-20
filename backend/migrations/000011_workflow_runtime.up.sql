-- SQL migration 000011: canonical workflow runtime (P2/B2).
--
-- The legacy workflow stub uses integer keys and is intentionally not part of
-- the production schema. These tables use the UUID/timestamptz conventions of
-- the canonical P1 schema and keep the workflow history append-only.

CREATE TABLE workflow_templates (
    id UUID NOT NULL,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_templates PRIMARY KEY (id),
    CONSTRAINT uq_workflow_templates_code UNIQUE (code),
    CONSTRAINT ck_workflow_templates_version_positive CHECK (version > 0)
);

CREATE TABLE workflow_stages (
    id UUID NOT NULL,
    template_id UUID NOT NULL,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    order_index INTEGER NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    default_duration_days INTEGER NOT NULL DEFAULT 7,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_stages PRIMARY KEY (id),
    CONSTRAINT uq_workflow_stages_code UNIQUE (template_id, code),
    CONSTRAINT uq_workflow_stages_order UNIQUE (template_id, order_index),
    CONSTRAINT ck_workflow_stages_order_nonnegative CHECK (order_index >= 0),
    CONSTRAINT ck_workflow_stages_duration_nonnegative CHECK (default_duration_days >= 0),
    CONSTRAINT fk_workflow_stages_template_id_workflow_templates
        FOREIGN KEY (template_id) REFERENCES workflow_templates (id) ON DELETE CASCADE
);
CREATE INDEX ix_workflow_stages_template_id
    ON workflow_stages USING btree (template_id);

CREATE TABLE workflow_instances (
    id UUID NOT NULL,
    template_id UUID NOT NULL,
    university_id UUID NOT NULL,
    program_id UUID,
    product_id UUID,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    revision INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_by_keycloak_sub VARCHAR(256) NOT NULL,
    updated_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_instances PRIMARY KEY (id),
    CONSTRAINT ck_workflow_instances_status CHECK (status IN ('draft', 'active', 'completed', 'cancelled')),
    CONSTRAINT ck_workflow_instances_revision_nonnegative CHECK (revision >= 0),
    CONSTRAINT fk_workflow_instances_template_id_workflow_templates
        FOREIGN KEY (template_id) REFERENCES workflow_templates (id) ON DELETE RESTRICT,
    CONSTRAINT fk_workflow_instances_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_instances_program_id_it_programs
        FOREIGN KEY (program_id) REFERENCES it_programs (id) ON DELETE SET NULL,
    CONSTRAINT fk_workflow_instances_product_id_it_products
        FOREIGN KEY (product_id) REFERENCES it_products (id) ON DELETE SET NULL
);
CREATE INDEX ix_workflow_instances_university_id
    ON workflow_instances USING btree (university_id);
CREATE INDEX ix_workflow_instances_template_id
    ON workflow_instances USING btree (template_id);
CREATE INDEX ix_workflow_instances_status_due_date
    ON workflow_instances USING btree (status, due_date);
CREATE UNIQUE INDEX uq_workflow_instances_active_scope
    ON workflow_instances (university_id, program_id)
    WHERE status = 'active';

CREATE TABLE instance_stages (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    template_stage_id UUID NOT NULL,
    order_index INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    due_date TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    skipped_at TIMESTAMPTZ,
    completed_by_keycloak_sub VARCHAR(256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_instance_stages PRIMARY KEY (id),
    CONSTRAINT uq_instance_stages_stage UNIQUE (instance_id, template_stage_id),
    CONSTRAINT ck_instance_stages_status
        CHECK (status IN ('pending', 'current', 'completed', 'skipped', 'overdue')),
    CONSTRAINT fk_instance_stages_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_instance_stages_template_stage_id_workflow_stages
        FOREIGN KEY (template_stage_id) REFERENCES workflow_stages (id) ON DELETE RESTRICT
);
CREATE INDEX ix_instance_stages_instance_order
    ON instance_stages USING btree (instance_id, order_index);
CREATE UNIQUE INDEX uq_instance_stages_current
    ON instance_stages (instance_id)
    WHERE status = 'current';

CREATE TABLE transitions (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    from_stage_id UUID,
    to_stage_id UUID NOT NULL,
    action VARCHAR(32) NOT NULL DEFAULT 'next',
    actor_keycloak_sub VARCHAR(256) NOT NULL,
    comment TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_transitions PRIMARY KEY (id),
    CONSTRAINT ck_transitions_action CHECK (action IN ('next', 'skip', 'reopen', 'complete')),
    CONSTRAINT fk_transitions_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_transitions_from_stage_id_instance_stages
        FOREIGN KEY (from_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL,
    CONSTRAINT fk_transitions_to_stage_id_instance_stages
        FOREIGN KEY (to_stage_id) REFERENCES instance_stages (id) ON DELETE CASCADE
);
CREATE INDEX ix_transitions_instance_created
    ON transitions USING btree (instance_id, created_at);

CREATE FUNCTION reject_transition_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'workflow transitions are immutable';
END;
$$;

CREATE TRIGGER trg_transitions_immutable
    BEFORE UPDATE OR DELETE ON transitions
    FOR EACH ROW EXECUTE FUNCTION reject_transition_mutation();

CREATE TABLE comments (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    instance_stage_id UUID,
    author_keycloak_sub VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    edited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_comments PRIMARY KEY (id),
    CONSTRAINT ck_comments_content_nonempty CHECK (length(btrim(content)) > 0),
    CONSTRAINT fk_comments_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_comments_stage_id_instance_stages
        FOREIGN KEY (instance_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL
);
CREATE INDEX ix_comments_instance_created
    ON comments USING btree (instance_id, created_at);

CREATE TABLE tasks (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    instance_stage_id UUID,
    title VARCHAR(512) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assignee_keycloak_sub VARCHAR(256),
    due_date TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    completed_at TIMESTAMPTZ,
    completed_by_keycloak_sub VARCHAR(256),
    created_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_tasks PRIMARY KEY (id),
    CONSTRAINT ck_tasks_status CHECK (status IN ('open', 'done', 'cancelled')),
    CONSTRAINT fk_tasks_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_tasks_stage_id_instance_stages
        FOREIGN KEY (instance_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL
);
CREATE INDEX ix_tasks_instance_due
    ON tasks USING btree (instance_id, status, due_date);

CREATE TABLE attachments (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    instance_stage_id UUID,
    document_id UUID NOT NULL,
    created_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_attachments PRIMARY KEY (id),
    CONSTRAINT uq_attachments_document UNIQUE (instance_id, document_id),
    CONSTRAINT fk_attachments_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_attachments_stage_id_instance_stages
        FOREIGN KEY (instance_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL,
    CONSTRAINT fk_attachments_document_id_documents
        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);

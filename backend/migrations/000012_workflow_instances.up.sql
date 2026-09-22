-- SQL migration 000012: workflow instances pipeline (P2-01-03).
--
-- Source of truth for: workflow_instances, workflow_stage_transitions,
-- workflow_comments, workflow_attachments, workflow_tasks.
--
-- Parent: workflow_instances = one university running one template
-- (university x template x current stage x responsible x status x due_date).
-- Children reference the instance (ON DELETE CASCADE); the canonical
-- object-access path for P2-05 file storage is attachment -> instance
-- -> university (no duplicated university_id on children).
--
-- Legacy app/modules/workflow/models.py (workflows, workflow_statuses,
-- workflow_transitions, tasks on DeferredBase, int PKs) is NOT reused and
-- NOT renamed: canonical names use the workflow_stage_* / workflow_*
-- prefix so they never collide with the deferred set pinned by
-- tests/test_p0_deferred_registry.py.
--
-- Conventions (match 000001/000005/000011):
-- * UUID PKs are client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * created_at/updated_at are TIMESTAMPTZ NOT NULL DEFAULT now().
-- * Actor identity is always keycloak_sub VARCHAR(256), never int user_id.
-- * No native ENUM types: lifecycle flags are VARCHAR(32) with defaults.
--
-- FK policies:
-- * instances.university_id -> universities CASCADE (P1 meetings/notes rule).
-- * instances.template_id -> workflow_templates RESTRICT (a template with
--   live instances cannot be deleted; disable via is_active instead).
-- * instances.current_stage_id -> workflow_stages SET NULL (operational
--   pointer; history lives in workflow_stage_transitions).
-- * instances.responsible_id / tasks.responsible_id -> responsibles SET NULL.
-- * children.instance_id -> workflow_instances CASCADE.
-- * children.stage_id + transitions.from/to_stage_id -> workflow_stages
--   SET NULL (anchors survive stage-row removal).
--
-- CHECK quirk preserved (same as 000005): the real DB constraint names are
--   ck_workflow_stage_transitions_ck_workflow_stage_transitions_has_side and
--   ck_workflow_attachments_ck_workflow_attachments_file_size_ge_0 (doubled
--   prefix produced by the SQLAlchemy naming convention
--   ``ck_%(table_name)s_%(constraint_name)s`` on top of the declared short
--   names). The doubled names are kept verbatim so ORM metadata equivalence
--   holds; the Python models declare the short names.
-- * ck_workflow_stage_transitions_has_side: a transition moves somewhere —
--   from_stage_id and to_stage_id cannot both be NULL (creation = NULL
--   from_stage_id; closure = NULL to_stage_id).
-- * ck_workflow_attachments_file_size_ge_0: storage size is never negative.

CREATE TABLE workflow_instances (
    id UUID NOT NULL,
    university_id UUID NOT NULL,
    template_id UUID NOT NULL,
    current_stage_id UUID,
    responsible_id UUID,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    due_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_instances PRIMARY KEY (id),
    CONSTRAINT fk_workflow_instances_university_id_universities
        FOREIGN KEY (university_id) REFERENCES universities (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_instances_template_id_workflow_templates
        FOREIGN KEY (template_id) REFERENCES workflow_templates (id) ON DELETE RESTRICT,
    CONSTRAINT fk_workflow_instances_current_stage_id_workflow_stages
        FOREIGN KEY (current_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT fk_workflow_instances_responsible_id_responsibles
        FOREIGN KEY (responsible_id) REFERENCES responsibles (id) ON DELETE SET NULL
);
CREATE INDEX ix_workflow_instances_university_id ON workflow_instances USING btree (university_id);
CREATE INDEX ix_workflow_instances_template_id ON workflow_instances USING btree (template_id);
CREATE INDEX ix_workflow_instances_current_stage_id ON workflow_instances USING btree (current_stage_id);
CREATE INDEX ix_workflow_instances_status ON workflow_instances USING btree (status);

CREATE TABLE workflow_stage_transitions (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    from_stage_id UUID,
    to_stage_id UUID,
    actor_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_stage_transitions PRIMARY KEY (id),
    CONSTRAINT fk_workflow_stage_transitions_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_stage_transitions_from_stage_id_workflow_stages
        FOREIGN KEY (from_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT fk_workflow_stage_transitions_to_stage_id_workflow_stages
        FOREIGN KEY (to_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT ck_workflow_stage_transitions_ck_workflow_stage_transitions_has_side
        CHECK (NOT ((from_stage_id IS NULL) AND (to_stage_id IS NULL)))
);
CREATE INDEX ix_workflow_stage_transitions_instance_id
    ON workflow_stage_transitions USING btree (instance_id);
CREATE INDEX ix_workflow_stage_transitions_instance_created
    ON workflow_stage_transitions USING btree (instance_id, created_at);

CREATE TABLE workflow_comments (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    stage_id UUID,
    author_keycloak_sub VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    is_internal BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_comments PRIMARY KEY (id),
    CONSTRAINT fk_workflow_comments_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_comments_stage_id_workflow_stages
        FOREIGN KEY (stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL
);
CREATE INDEX ix_workflow_comments_instance_id ON workflow_comments USING btree (instance_id);
CREATE INDEX ix_workflow_comments_instance_created
    ON workflow_comments USING btree (instance_id, created_at);

CREATE TABLE workflow_attachments (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    stage_id UUID,
    original_filename VARCHAR(512) NOT NULL,
    storage_key VARCHAR(1024) NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    mime_type VARCHAR(128) NOT NULL DEFAULT '',
    uploaded_by_keycloak_sub VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_attachments PRIMARY KEY (id),
    CONSTRAINT uq_workflow_attachments_storage_key UNIQUE (storage_key),
    CONSTRAINT fk_workflow_attachments_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_attachments_stage_id_workflow_stages
        FOREIGN KEY (stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT ck_workflow_attachments_ck_workflow_attachments_file_size_ge_0
        CHECK (file_size >= 0)
);
CREATE INDEX ix_workflow_attachments_instance_id ON workflow_attachments USING btree (instance_id);

CREATE TABLE workflow_tasks (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    stage_id UUID,
    title VARCHAR(512) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    responsible_id UUID,
    deadline DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_tasks PRIMARY KEY (id),
    CONSTRAINT fk_workflow_tasks_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_workflow_tasks_stage_id_workflow_stages
        FOREIGN KEY (stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT fk_workflow_tasks_responsible_id_responsibles
        FOREIGN KEY (responsible_id) REFERENCES responsibles (id) ON DELETE SET NULL
);
CREATE INDEX ix_workflow_tasks_instance_id ON workflow_tasks USING btree (instance_id);
CREATE INDEX ix_workflow_tasks_status ON workflow_tasks USING btree (status);
CREATE INDEX ix_workflow_tasks_deadline ON workflow_tasks USING btree (deadline);

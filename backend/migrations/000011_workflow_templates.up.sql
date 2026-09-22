-- SQL migration 000011: workflow templates + stages (P2-01-01).
--
-- Source of truth for: workflow_templates, workflow_stages.
--
-- NOTE on legacy: app/modules/workflow/models.py (workflows,
-- workflow_statuses, workflow_transitions, tasks) predates the P1 UUID
-- decision (int PKs, isolated on DeferredBase) and is NOT reused here.
-- These two tables are standalone and reference only P1-canonical
-- conventions (client-generated UUID PKs, TIMESTAMPTZ); they hold no FK
-- to P1 entities (templates are process definitions, not per-university
-- rows), so no cross-table FK is needed.
--
-- Conventions (match 000001):
-- * UUID PKs are client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * created_at/updated_at are TIMESTAMPTZ NOT NULL DEFAULT now().
-- * No native ENUM types: flags are BOOLEAN, deadlines are INTEGER days.
--
-- Ordering model (P2 order_index contract):
-- * order_index is 1-based, dense, unique per template:
--   UNIQUE (template_id, order_index).
-- * The UNIQUE constraint is DEFERRABLE INITIALLY DEFERRED so a position
--   shift (UPDATE ... SET order_index = order_index + 1 WHERE ...) plus the
--   row INSERT can commit in ONE transaction without tripping on transient
--   duplicates; the final state is still checked at COMMIT time.
-- * CHECK (order_index >= 1) rejects zero/negative positions at the DB level.
-- * Stage name is deliberately NOT unique per template: renames and
--   P2-02-04 reorder/disable flows must not be blocked by a name pin.
-- * Template name IS unique: it is the natural key used by the idempotent
--   seed (migrate -> seed) for the 14-stage standard route.

CREATE TABLE workflow_templates (
    id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_templates PRIMARY KEY (id),
    CONSTRAINT uq_workflow_templates_name UNIQUE (name)
);

CREATE TABLE workflow_stages (
    id UUID NOT NULL,
    template_id UUID NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT,
    order_index INTEGER NOT NULL,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sla_days INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_workflow_stages PRIMARY KEY (id),
    CONSTRAINT fk_workflow_stages_template_id_workflow_templates
        FOREIGN KEY (template_id) REFERENCES workflow_templates (id) ON DELETE CASCADE,
    CONSTRAINT ck_workflow_stages_order_index_ge_1 CHECK (order_index >= 1),
    CONSTRAINT uq_workflow_stages_template_order UNIQUE (template_id, order_index)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ix_workflow_stages_template_id ON workflow_stages USING btree (template_id);
CREATE INDEX ix_workflow_stages_template_order ON workflow_stages USING btree (template_id, order_index);

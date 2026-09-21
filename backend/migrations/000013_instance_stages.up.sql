-- SQL migration 000013: instance runtime stages (P2-01-02 gap).
--
-- Source of truth for: instance_stages (+ two additive columns on
-- workflow_instances: current_instance_stage_id, completed_at).
--
-- Why this table (P2-01-02 contract = workflow_instances + instance_stages):
-- 000012 stores the instance header plus a mutable template pointer
-- (workflow_instances.current_stage_id -> workflow_stages). A template is a
-- living definition (rename / reorder / disable / sla_days edits via the
-- P2-02-0x stages API), so reading runtime state only through the mutable
-- template row rewrites history: an old instance would silently change when
-- the template changes. instance_stages is the per-instance runtime
-- snapshot: at creation the active template stages are copied here
-- (template_stage_id anchor + denormalized name/description/is_required +
-- order_index), and the runtime reads the snapshot afterwards.
--
-- Columns:
-- * instance_id -> workflow_instances CASCADE (runtime dies with instance).
-- * template_stage_id -> workflow_stages SET NULL (nullable anchor: when a
--   template stage row is deleted the snapshot row survives on its copied
--   name/description/is_required/order_index; history is never rewritten).
-- * order_index: 1-based, dense per instance, UNIQUE (instance_id,
--   order_index) DEFERRABLE INITIALLY DEFERRED (same positional contract as
--   000011: snapshot insert of N rows + pointer updates commit in ONE
--   transaction without tripping on transient duplicates).
-- * CHECK (order_index >= 1) rejects zero/negative positions.
-- * status: runtime lifecycle flag, VARCHAR(32), default 'pending'
--   (transitions to in_progress/done belong to P2-02-04, not this DDL).
-- * due_date DATE (cascaded from workflow_stages.sla_days at creation;
--   NULL sla_days -> NULL due_date, never invented).
-- * completed_at TIMESTAMPTZ (stage completion moment; NULL = open).
--
-- workflow_instances additions (both nullable, backward compatible with the
-- B1 Files flow which keys off workflow_instances.id only):
-- * current_instance_stage_id -> instance_stages SET NULL (canonical runtime
--   position; the legacy current_stage_id template pointer is kept in sync
--   on creation for compatibility and left untouched otherwise).
-- * completed_at TIMESTAMPTZ (instance completion moment for P2-06-01
--   overdue math; NULL = open).
--
-- Conventions (match 000001/000011/000012):
-- * UUID PKs are client-generated (uuid4 in Python); NO DEFAULT gen_random_uuid().
-- * created_at/updated_at are TIMESTAMPTZ NOT NULL DEFAULT now().
-- * No native ENUM types.
-- * No IF NOT EXISTS (drift must fail loudly; idempotency is the version table).
--
-- CHECK quirk preserved (same as 000005/000012): the real DB constraint name
-- is ck_instance_stages_ck_instance_stages_order_index_ge_1 (doubled prefix
-- produced by the SQLAlchemy naming convention
-- ``ck_%(table_name)s_%(constraint_name)s`` on top of the declared short
-- name). The doubled name is kept verbatim so ORM metadata equivalence
-- holds; the Python model declares the short name.

CREATE TABLE instance_stages (
    id UUID NOT NULL,
    instance_id UUID NOT NULL,
    template_stage_id UUID,
    order_index INTEGER NOT NULL,
    name VARCHAR(512) NOT NULL,
    description TEXT,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    due_date DATE,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_instance_stages PRIMARY KEY (id),
    CONSTRAINT fk_instance_stages_instance_id_workflow_instances
        FOREIGN KEY (instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE,
    CONSTRAINT fk_instance_stages_template_stage_id_workflow_stages
        FOREIGN KEY (template_stage_id) REFERENCES workflow_stages (id) ON DELETE SET NULL,
    CONSTRAINT ck_instance_stages_ck_instance_stages_order_index_ge_1
        CHECK (order_index >= 1),
    CONSTRAINT uq_instance_stages_instance_order UNIQUE (instance_id, order_index)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ix_instance_stages_instance_id ON instance_stages USING btree (instance_id);
CREATE INDEX ix_instance_stages_instance_order ON instance_stages USING btree (instance_id, order_index);

ALTER TABLE workflow_instances
    ADD COLUMN current_instance_stage_id UUID,
    ADD COLUMN completed_at TIMESTAMPTZ;
ALTER TABLE workflow_instances
    ADD CONSTRAINT fk_workflow_instances_current_instance_stage_id_instance_stages
        FOREIGN KEY (current_instance_stage_id) REFERENCES instance_stages (id) ON DELETE SET NULL;
CREATE INDEX ix_workflow_instances_current_instance_stage_id
    ON workflow_instances USING btree (current_instance_stage_id);

"""P2-01-03: workflow instances pipeline (instances + transitions/comments/attachments/tasks).

PostgreSQL integration tests (``TEST_DATABASE_URL`` at the dedicated test
DB); the schema always comes from the canonical SQL migrations
(``tests/db_helpers.py``). No SQLite, no ``create_all``.

Pure-unit checks (migration chain shape, SQL text conventions, ORM metadata
exactness) run everywhere without a database.

Coverage: 000012 up/down pair + chain order (000011 < 000012 < 000013 <
000014), SQL conventions (no ``IF NOT EXISTS``, client-generated UUIDs,
TIMESTAMPTZ defaults), ORM metadata mirrors SQL (columns/types/nullability/
FK/ON DELETE/indexes/constraints), no collision with the deferred legacy set
(``workflows``, ``workflow_transitions``, ``tasks``, ``files`` stay on
``DeferredBase``), PG: tables/FKs exist, full-graph insert, CASCADE
instance->children, CASCADE university->pipeline, RESTRICT template with live
instances, RESTRICT stage with recorded transitions (history keeps its
anchors), SET NULL operational stage anchors, transition CHECK, storage_key
UNIQUE.
"""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.db.base import Base
from app.models.catalog import Responsible, University
from app.models.workflow_instances import (
    WorkflowAttachment,
    WorkflowComment,
    WorkflowInstance,
    WorkflowStageTransition,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

PIPELINE_TABLES = (
    "workflow_instances",
    "workflow_stage_transitions",
    "workflow_comments",
    "workflow_attachments",
    "workflow_tasks",
)


def _tag() -> str:
    return uuid.uuid4().hex[:8]


# --------------------------------------------------------------- fixtures


@pytest.fixture()
def engine():
    """Fresh isolated PG DB per test (canonical SQL migrations, never ORM)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _mini_graph(db: Session, tag: str | None = None):
    """Minimal valid parents: university/responsible/template/stage."""
    tag = tag or _tag()
    u = University(name=f"WF University {tag}", city="Москва")
    r = Responsible(full_name="Петров П.П.", email=f"wf-{tag}@example.local", role="manager")
    t = WorkflowTemplate(name=f"WF Template {tag}", description="")
    db.add_all([u, r, t])
    db.flush()
    s = WorkflowStage(template_id=t.id, name="Stage 1", order_index=1)
    db.add(s)
    db.flush()
    return {"university": u, "responsible": r, "template": t, "stage": s}


def _mini_instance(db: Session, tag: str | None = None):
    g = _mini_graph(db, tag)
    inst = WorkflowInstance(
        university_id=g["university"].id,
        template_id=g["template"].id,
        current_stage_id=g["stage"].id,
        responsible_id=g["responsible"].id,
    )
    db.add(inst)
    db.flush()
    return g | {"instance": inst}


# ------------------------------------------------- pure-unit: migration chain


def test_migration_000012_pair_discoverable_and_latest():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sql_migrate", Path(__file__).resolve().parent.parent / "scripts" / "migrate.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan = module._discover()
    versions = [v for v, _, _ in plan]
    assert "000012_workflow_instances" in versions
    assert "000013_instance_stages" in versions
    assert "000014_transition_history_restrict" in versions
    assert versions[-1] == "000014_transition_history_restrict"
    assert versions.index("000011_workflow_templates") < versions.index("000012_workflow_instances")
    assert versions.index("000012_workflow_instances") < versions.index("000013_instance_stages")
    assert versions.index("000013_instance_stages") < versions.index(
        "000014_transition_history_restrict"
    )
    assert set(module.EXPECTED_TABLES) >= set(PIPELINE_TABLES)


def test_up_sql_conventions():
    raw = (MIGRATIONS_DIR / "000012_workflow_instances.up.sql").read_text(encoding="utf-8")
    # Strip `--` comments: header documents conventions in prose.
    sql = "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("--"))
    for table in PIPELINE_TABLES:
        assert f"CREATE TABLE {table} (" in sql, table
    assert "IF NOT EXISTS" not in sql
    assert "gen_random_uuid()" not in sql
    assert "create_all" not in sql and "drop_all" not in sql


def test_down_sql_drops_children_before_parent():
    sql = (MIGRATIONS_DIR / "000012_workflow_instances.down.sql").read_text(encoding="utf-8")
    drops = [ln.strip() for ln in sql.splitlines() if ln.strip().startswith("DROP TABLE")]
    assert drops == [
        "DROP TABLE workflow_tasks;",
        "DROP TABLE workflow_attachments;",
        "DROP TABLE workflow_comments;",
        "DROP TABLE workflow_stage_transitions;",
        "DROP TABLE workflow_instances;",
    ]


# ------------------------------------------------- pure-unit: ORM metadata


def test_orm_metadata_registers_five_tables():
    tables = Base.metadata.tables
    for table in PIPELINE_TABLES:
        assert table in tables, table
    # No collision with the deferred legacy set.
    for legacy in ("workflows", "workflow_transitions", "tasks", "files"):
        assert legacy not in tables, legacy


def test_orm_instance_columns():
    cols = Base.metadata.tables["workflow_instances"].c
    assert set(cols.keys()) == {
        "id",
        "university_id",
        "template_id",
        "current_stage_id",
        "current_instance_stage_id",
        "responsible_id",
        "status",
        "due_date",
        "completed_at",
        "created_at",
        "updated_at",
    }
    assert cols["university_id"].nullable is False
    assert cols["template_id"].nullable is False
    assert cols["current_stage_id"].nullable is True
    assert cols["current_instance_stage_id"].nullable is True
    assert cols["responsible_id"].nullable is True
    assert cols["status"].nullable is False
    assert cols["due_date"].nullable is True
    assert cols["completed_at"].nullable is True


def test_orm_children_columns():
    t = Base.metadata.tables["workflow_stage_transitions"].c
    assert set(t.keys()) == {
        "id",
        "instance_id",
        "from_stage_id",
        "to_stage_id",
        "actor_keycloak_sub",
        "created_at",
        "updated_at",
    }
    c = Base.metadata.tables["workflow_comments"].c
    assert set(c.keys()) == {
        "id",
        "instance_id",
        "stage_id",
        "author_keycloak_sub",
        "content",
        "is_internal",
        "created_at",
        "updated_at",
    }
    a = Base.metadata.tables["workflow_attachments"].c
    assert set(a.keys()) == {
        "id",
        "instance_id",
        "stage_id",
        "original_filename",
        "storage_key",
        "file_size",
        "mime_type",
        "uploaded_by_keycloak_sub",
        "created_at",
        "updated_at",
    }
    k = Base.metadata.tables["workflow_tasks"].c
    assert set(k.keys()) == {
        "id",
        "instance_id",
        "stage_id",
        "title",
        "description",
        "responsible_id",
        "deadline",
        "status",
        "completed_at",
        "created_at",
        "updated_at",
    }


def _fk_ondelete(table: str, column: str) -> tuple[str, str]:
    col = Base.metadata.tables[table].c[column]
    (fk,) = col.foreign_keys
    return fk.column.table.name, (fk.ondelete or "").upper()


def test_orm_fk_targets_and_ondelete():
    assert _fk_ondelete("workflow_instances", "university_id") == ("universities", "CASCADE")
    assert _fk_ondelete("workflow_instances", "template_id") == ("workflow_templates", "RESTRICT")
    assert _fk_ondelete("workflow_instances", "current_stage_id") == ("workflow_stages", "SET NULL")
    assert _fk_ondelete("workflow_instances", "current_instance_stage_id") == (
        "instance_stages",
        "SET NULL",
    )
    assert _fk_ondelete("workflow_instances", "responsible_id") == ("responsibles", "SET NULL")
    for table in (
        "workflow_stage_transitions",
        "workflow_comments",
        "workflow_attachments",
        "workflow_tasks",
    ):
        if table == "workflow_stage_transitions":
            # 000014: history keeps its anchors (RESTRICT); operational
            # pointers elsewhere stay SET NULL.
            assert _fk_ondelete(table, "instance_id") == ("workflow_instances", "CASCADE")
            assert _fk_ondelete(table, "from_stage_id") == ("workflow_stages", "RESTRICT")
            assert _fk_ondelete(table, "to_stage_id") == ("workflow_stages", "RESTRICT")
        else:
            assert _fk_ondelete(table, "instance_id") == ("workflow_instances", "CASCADE")
            assert _fk_ondelete(table, "stage_id") == ("workflow_stages", "SET NULL")
    assert _fk_ondelete("workflow_tasks", "responsible_id") == ("responsibles", "SET NULL")


def test_orm_constraints_and_indexes():
    tables = Base.metadata.tables

    def names(table: str, kind) -> set[str]:
        return {c.name for c in tables[table].constraints if isinstance(c, kind)}

    from sqlalchemy import CheckConstraint, UniqueConstraint

    # CHECK quirk (same as 000005 documents): the naming convention doubles
    # the prefix, and SQL keeps the doubled names verbatim.
    assert "ck_workflow_stage_transitions_ck_workflow_stage_transitions_has_side" in names(
        "workflow_stage_transitions", CheckConstraint
    )
    assert "uq_workflow_attachments_storage_key" in names("workflow_attachments", UniqueConstraint)
    assert "ck_workflow_attachments_ck_workflow_attachments_file_size_ge_0" in names(
        "workflow_attachments", CheckConstraint
    )

    idx = {t: {i.name for i in tables[t].indexes} for t in PIPELINE_TABLES}
    assert "ix_workflow_instances_university_id" in idx["workflow_instances"]
    assert "ix_workflow_instances_template_id" in idx["workflow_instances"]
    assert "ix_workflow_instances_status" in idx["workflow_instances"]
    assert "ix_workflow_stage_transitions_instance_created" in idx["workflow_stage_transitions"]
    assert "ix_workflow_comments_instance_created" in idx["workflow_comments"]
    assert "ix_workflow_attachments_instance_id" in idx["workflow_attachments"]
    assert "ix_workflow_tasks_deadline" in idx["workflow_tasks"]


def test_orm_instance_stage_columns_fk_constraints_indexes():
    """P2-01-02 runtime snapshot table mirrors 000013 exactly (pure-unit)."""
    from sqlalchemy import CheckConstraint, UniqueConstraint

    from app.models.workflow_instances import InstanceStage  # noqa: F401

    tables = Base.metadata.tables
    assert "instance_stages" in tables
    cols = tables["instance_stages"].c
    assert set(cols.keys()) == {
        "id",
        "instance_id",
        "template_stage_id",
        "order_index",
        "name",
        "description",
        "is_required",
        "status",
        "due_date",
        "completed_at",
        "created_at",
        "updated_at",
    }
    assert cols["instance_id"].nullable is False
    assert cols["template_stage_id"].nullable is True
    assert cols["order_index"].nullable is False
    assert cols["name"].nullable is False
    assert cols["due_date"].nullable is True
    assert cols["completed_at"].nullable is True
    assert _fk_ondelete("instance_stages", "instance_id") == ("workflow_instances", "CASCADE")
    assert _fk_ondelete("instance_stages", "template_stage_id") == ("workflow_stages", "SET NULL")

    def names(kind) -> set[str]:
        return {c.name for c in tables["instance_stages"].constraints if isinstance(c, kind)}

    assert "uq_instance_stages_instance_order" in names(UniqueConstraint)
    # CHECK quirk (same as 000005/000012): naming convention doubles prefix.
    assert "ck_instance_stages_ck_instance_stages_order_index_ge_1" in names(CheckConstraint)

    idx = {i.name for i in tables["instance_stages"].indexes}
    assert "ix_instance_stages_instance_id" in idx
    assert "ix_instance_stages_instance_order" in idx
    assert "ix_workflow_instances_current_instance_stage_id" in {
        i.name for i in tables["workflow_instances"].indexes
    }


# ------------------------------------------------- PG: schema presence


def test_all_pipeline_tables_exist(engine):
    names = set(inspect(engine).get_table_names())
    assert set(PIPELINE_TABLES) <= names
    assert "instance_stages" in names


def test_foreign_keys_really_created(engine):
    insp = inspect(engine)
    fks = {
        (t, tuple(f["constrained_columns"]), f["referred_table"])
        for t in (*PIPELINE_TABLES, "instance_stages")
        for f in insp.get_foreign_keys(t)
    }
    assert ("workflow_instances", ("university_id",), "universities") in fks
    assert ("workflow_instances", ("template_id",), "workflow_templates") in fks
    assert ("workflow_instances", ("current_instance_stage_id",), "instance_stages") in fks
    assert ("instance_stages", ("instance_id",), "workflow_instances") in fks
    assert ("workflow_stage_transitions", ("instance_id",), "workflow_instances") in fks
    assert ("workflow_comments", ("instance_id",), "workflow_instances") in fks
    assert ("workflow_attachments", ("instance_id",), "workflow_instances") in fks
    assert ("workflow_tasks", ("instance_id",), "workflow_instances") in fks


# ------------------------------------------------- PG: behavior


def _full_children(db: Session, g, key_tag: str):
    tr = WorkflowStageTransition(
        instance_id=g["instance"].id,
        from_stage_id=None,
        to_stage_id=g["stage"].id,
        actor_keycloak_sub="actor-1",
    )
    cm = WorkflowComment(
        instance_id=g["instance"].id,
        stage_id=g["stage"].id,
        author_keycloak_sub="author-1",
        content="Первый комментарий",
    )
    at = WorkflowAttachment(
        instance_id=g["instance"].id,
        stage_id=g["stage"].id,
        original_filename="report.pdf",
        storage_key=f"{key_tag}/report.pdf",
        file_size=10,
        mime_type="application/pdf",
        uploaded_by_keycloak_sub="uploader-1",
    )
    tk = WorkflowTask(
        instance_id=g["instance"].id,
        stage_id=g["stage"].id,
        title="Позвонить в вуз",
        responsible_id=g["responsible"].id,
    )
    db.add_all([tr, cm, at, tk])
    db.flush()
    return tr, cm, at, tk


def test_full_graph_insert_and_relationships(db):
    g = _mini_instance(db)
    tr, cm, at, tk = _full_children(db, g, _tag())
    db.commit()
    inst = db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == g["instance"].id)
    ).scalar_one()
    assert len(inst.transitions) == 1 and inst.transitions[0].id == tr.id
    assert len(inst.comments) == 1 and inst.comments[0].id == cm.id
    assert len(inst.attachments) == 1 and inst.attachments[0].id == at.id
    assert len(inst.tasks) == 1 and inst.tasks[0].id == tk.id
    assert inst.status == "active"
    assert inst.transitions[0].actor_keycloak_sub == "actor-1"


def test_cascade_delete_instance_removes_children(db):
    g = _mini_instance(db)
    _full_children(db, g, _tag())
    db.commit()
    iid = g["instance"].id
    db.delete(db.get(WorkflowInstance, iid))
    db.commit()
    for model in (
        WorkflowStageTransition,
        WorkflowComment,
        WorkflowAttachment,
        WorkflowTask,
    ):
        assert db.execute(select(model.id).where(model.instance_id == iid)).scalars().all() == []


def test_university_cascade_removes_pipeline(db):
    g = _mini_instance(db)
    _full_children(db, g, _tag())
    db.commit()
    iid, uid = g["instance"].id, g["university"].id
    db.delete(db.get(University, uid))
    db.commit()
    assert db.get(WorkflowInstance, iid) is None
    assert (
        db.execute(select(WorkflowTask.id).where(WorkflowTask.instance_id == iid)).scalars().all()
        == []
    )


def test_template_restrict_with_live_instance(db):
    g = _mini_instance(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.delete(db.get(WorkflowTemplate, g["template"].id))
        db.commit()
    db.rollback()


def test_stage_delete_blocked_while_transition_history_references_it(db):
    """000014: a stage with recorded moves cannot be deleted (RESTRICT).

    Replaces the 000012-era expectation (both anchors NULLed, which tripped
    the has_side CHECK): history rows keep previous/new stage links, so the
    stage is retired via ``is_active = FALSE`` instead of DELETE.
    """
    g = _mini_instance(db)
    _full_children(db, g, _tag())
    db.commit()
    with pytest.raises(IntegrityError) as exc:
        db.delete(db.get(WorkflowStage, g["stage"].id))
        db.commit()
    # PostgreSQL reports the RESTRICT refusal as foreign_key_violation (23503).
    assert getattr(exc.value.orig, "sqlstate", None) == "23503"
    db.rollback()


def test_stage_delete_sets_operational_anchors_null(db):
    """Operational (single, CHECK-free) anchors still degrade via SET NULL.

    A stage referenced ONLY by operational pointers (instance current pointer,
    comment/attachment/task anchors — no transition history) is removable;
    those pointers NULL out and runtime snapshots survive.
    """
    g = _mini_graph(db)
    inst = WorkflowInstance(
        university_id=g["university"].id,
        template_id=g["template"].id,
        current_stage_id=g["stage"].id,
    )
    db.add(inst)
    db.flush()
    cm = WorkflowComment(
        instance_id=inst.id,
        stage_id=g["stage"].id,
        author_keycloak_sub="author-1",
        content="anchor me",
    )
    at = WorkflowAttachment(
        instance_id=inst.id,
        stage_id=g["stage"].id,
        original_filename="a.pdf",
        storage_key=f"{_tag()}/a.pdf",
        uploaded_by_keycloak_sub="u-1",
    )
    tk = WorkflowTask(instance_id=inst.id, stage_id=g["stage"].id, title="t")
    db.add_all([cm, at, tk])
    db.commit()
    sid, iid = g["stage"].id, inst.id
    cmid, atid, tkid = cm.id, at.id, tk.id
    db.delete(db.get(WorkflowStage, sid))
    db.commit()
    assert db.get(WorkflowInstance, iid).current_stage_id is None
    assert db.get(WorkflowComment, cmid).stage_id is None
    assert db.get(WorkflowAttachment, atid).stage_id is None
    assert db.get(WorkflowTask, tkid).stage_id is None


def test_transition_check_rejects_null_both_sides(db):
    g = _mini_instance(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(
            WorkflowStageTransition(
                instance_id=g["instance"].id,
                from_stage_id=None,
                to_stage_id=None,
                actor_keycloak_sub="actor-x",
            )
        )
        db.commit()
    db.rollback()


def test_storage_key_unique(db):
    g = _mini_instance(db)
    key = f"{_tag()}/dup.pdf"
    db.add(
        WorkflowAttachment(
            instance_id=g["instance"].id,
            original_filename="dup.pdf",
            storage_key=key,
            uploaded_by_keycloak_sub="u-1",
        )
    )
    db.flush()
    # The duplicate violates uq_workflow_attachments_storage_key (23505) at
    # flush time, so the second INSERT itself must be inside pytest.raises
    # (previously the bare flush fired before the guard and escaped).
    with pytest.raises(IntegrityError) as exc:
        db.add(
            WorkflowAttachment(
                instance_id=g["instance"].id,
                original_filename="dup.pdf",
                storage_key=key,
                uploaded_by_keycloak_sub="u-1",
            )
        )
        db.flush()
    assert getattr(exc.value.orig, "sqlstate", None) == "23505"
    assert "uq_workflow_attachments_storage_key" in str(exc.value.orig)
    db.rollback()


def test_attachment_check_rejects_negative_size(db):
    g = _mini_instance(db)
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(
            WorkflowAttachment(
                instance_id=g["instance"].id,
                original_filename="neg.pdf",
                storage_key=f"{_tag()}/neg.pdf",
                file_size=-1,
                uploaded_by_keycloak_sub="u-1",
            )
        )
        db.commit()
    db.rollback()

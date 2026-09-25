"""P2-01-03/P2-01-02 canonical ORM for the workflow instances pipeline.

Runtime-only description of SQL migrations ``000012_workflow_instances``,
``000013_instance_stages`` and ``000014_transition_history_restrict`` (which
are the schema source of truth): types, nullability, FK, constraints and
indexes mirror the ``*.up.sql`` exactly. Never drives DDL.

Parent ``WorkflowInstance`` = one university running one template; children
(transitions/comments/attachments/tasks/instance_stages) reference the
instance with ``ON DELETE CASCADE``. Object access for P2-05 file storage
resolves via attachment -> instance -> university.

``InstanceStage`` (000013) is the per-instance runtime snapshot of the
template stages: creation copies the active template stages here, so later
template edits never rewrite an old instance's history. The template anchor
(``template_stage_id``) is SET NULL on stage-row removal; the copied
name/description/is_required/order_index survive.

Transition anchors (000014) are ON DELETE RESTRICT: history rows keep their
previous/new stage links, so a stage with recorded moves is retired via
``is_active = FALSE``, not DELETE.

Legacy ``app/modules/workflow/models.py`` (int PKs on ``DeferredBase``) is
intentionally NOT reused; canonical names avoid that set entirely.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class WorkflowInstance(UUIDPKMixin, TimestampMixin, Base):
    """One university running one workflow template."""

    __tablename__ = "workflow_instances"
    __table_args__ = (
        Index("ix_workflow_instances_university_id", "university_id"),
        Index("ix_workflow_instances_template_id", "template_id"),
        Index("ix_workflow_instances_program_id", "program_id"),
        Index("uq_workflow_instances_university_program", "university_id", "program_id", unique=True, postgresql_where=text("program_id IS NOT NULL")),
        Index("ix_workflow_instances_current_stage_id", "current_stage_id"),
        Index("ix_workflow_instances_current_instance_stage_id", "current_instance_stage_id"),
        Index("ix_workflow_instances_status", "status"),
    )

    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "universities.id",
            name="fk_workflow_instances_university_id_universities",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_templates.id",
            name="fk_workflow_instances_template_id_workflow_templates",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("it_programs.id", name="fk_workflow_instances_program_id_it_programs", ondelete="RESTRICT"),
        nullable=True,
        default=None,
    )
    current_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_instances_current_stage_id_workflow_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "responsibles.id",
            name="fk_workflow_instances_responsible_id_responsibles",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    current_instance_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_workflow_instances_current_instance_stage_id_instance_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )

    transitions: Mapped[list["WorkflowStageTransition"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", lazy="selectin"
    )
    comments: Mapped[list["WorkflowComment"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", lazy="selectin"
    )
    attachments: Mapped[list["WorkflowAttachment"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", lazy="selectin"
    )
    tasks: Mapped[list["WorkflowTask"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", lazy="selectin"
    )
    instance_stages: Mapped[list["InstanceStage"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="InstanceStage.order_index",
        lazy="selectin",
        foreign_keys="InstanceStage.instance_id",
    )


class WorkflowStageTransition(UUIDPKMixin, TimestampMixin, Base):
    """Stage-movement log entry: NULL from_stage_id = creation, NULL to = closure.

    ``comment`` (000016, P2-03-03) keeps the required history note: prev
    stage + new stage + actor + comment + timestamp, never NULL.
    """

    __tablename__ = "workflow_stage_transitions"
    __table_args__ = (
        CheckConstraint(
            "NOT ((from_stage_id IS NULL) AND (to_stage_id IS NULL))",
            name="ck_workflow_stage_transitions_has_side",
        ),
        Index("ix_workflow_stage_transitions_instance_id", "instance_id"),
        Index(
            "ix_workflow_stage_transitions_instance_created",
            "instance_id",
            "created_at",
        ),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_workflow_stage_transitions_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_stage_transitions_from_stage_id_workflow_stages",
            ondelete="RESTRICT",
        ),
        nullable=True,
        default=None,
    )
    to_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_stage_transitions_to_stage_id_workflow_stages",
            ondelete="RESTRICT",
        ),
        nullable=True,
        default=None,
    )
    actor_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="transitions")


class WorkflowComment(UUIDPKMixin, TimestampMixin, Base):
    """Instance discussion entry, optionally anchored to a stage."""

    __tablename__ = "workflow_comments"
    __table_args__ = (
        Index("ix_workflow_comments_instance_id", "instance_id"),
        Index("ix_workflow_comments_instance_created", "instance_id", "created_at"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_workflow_comments_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_comments_stage_id_workflow_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    author_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="comments")


class WorkflowAttachment(UUIDPKMixin, TimestampMixin, Base):
    """File metadata for P2-05 storage: original name here, UUID storage_key in /app/storage."""

    __tablename__ = "workflow_attachments"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_workflow_attachments_storage_key"),
        CheckConstraint("file_size >= 0", name="ck_workflow_attachments_file_size_ge_0"),
        Index("ix_workflow_attachments_instance_id", "instance_id"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_workflow_attachments_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_attachments_stage_id_workflow_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    uploaded_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="attachments")


class WorkflowTask(UUIDPKMixin, TimestampMixin, Base):
    """Instance task with optional stage anchor, assignee, deadline and status.

    ``priority`` (000017, P2-07-02) feeds Health Score component T:
    ``critical`` overdue tasks cost -8, other overdue tasks -4.
    """

    __tablename__ = "workflow_tasks"
    __table_args__ = (
        Index("ix_workflow_tasks_instance_id", "instance_id"),
        Index("ix_workflow_tasks_status", "status"),
        Index("ix_workflow_tasks_deadline", "deadline"),
        Index("ix_workflow_tasks_instance_priority", "instance_id", "priority"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_workflow_tasks_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_workflow_tasks_stage_id_workflow_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "responsibles.id",
            name="fk_workflow_tasks_responsible_id_responsibles",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal", server_default="normal"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="tasks")


class InstanceStage(UUIDPKMixin, TimestampMixin, Base):
    """Runtime snapshot of one template stage for one instance (000013).

    Copied from the active ``workflow_stages`` at instance creation, ordered
    by ``order_index`` (1-based, dense, unique per instance). Later template
    edits never touch these rows, so an old instance keeps its history.
    """

    __tablename__ = "instance_stages"
    __table_args__ = (
        UniqueConstraint(
            "instance_id",
            "order_index",
            name="uq_instance_stages_instance_order",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("order_index >= 1", name="ck_instance_stages_order_index_ge_1"),
        Index("ix_instance_stages_instance_id", "instance_id"),
        Index("ix_instance_stages_instance_order", "instance_id", "order_index"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_instance_stages_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    template_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_instance_stages_template_stage_id_workflow_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
        default=None,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    instance: Mapped["WorkflowInstance"] = relationship(
        back_populates="instance_stages", foreign_keys="InstanceStage.instance_id"
    )

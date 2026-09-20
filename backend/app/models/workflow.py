"""Canonical UUID workflow models for the P2 interaction pipeline.

The older ``app.modules.workflow`` package is a deliberately isolated legacy
stub.  These models belong to the canonical ``Base`` metadata and mirror the
``000011_workflow_runtime`` SQL migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.catalog import ITProduct, ITProgram, University


def _overdue_days(due_date: datetime | None, open_status: bool) -> int:
    """Return elapsed whole UTC days for an open item past its deadline."""
    if not open_status or due_date is None:
        return 0
    due = due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - due.astimezone(timezone.utc)
    return max(0, delta.days)


def _is_overdue(due_date: datetime | None, open_status: bool) -> bool:
    if not open_status or due_date is None:
        return False
    due = due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due.astimezone(timezone.utc) < datetime.now(timezone.utc)


class WorkflowTemplate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "workflow_templates"
    __table_args__ = (Index("ix_workflow_templates_active", "is_active"),)

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    stages: Mapped[list["WorkflowTemplateStage"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowTemplateStage.order_index",
    )


class WorkflowTemplateStage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "workflow_stages"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "code", name="uq_workflow_stages_code"
        ),
        UniqueConstraint(
            "template_id", "order_index", name="uq_workflow_stages_order"
        ),
        Index("ix_workflow_stages_template_id", "template_id"),
        Index("ix_workflow_stages_template_order", "template_id", "order_index"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_templates.id",
            name="fk_workflow_stages_template_id_workflow_templates",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(nullable=False, default=True)
    default_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    template: Mapped[WorkflowTemplate] = relationship(back_populates="stages")


class WorkflowInstance(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "workflow_instances"
    __table_args__ = (
        Index("ix_workflow_instances_university_id", "university_id"),
        Index("ix_workflow_instances_template_id", "template_id"),
        Index("ix_workflow_instances_status_due_date", "status", "due_date"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_templates.id",
            name="fk_workflow_instances_template_id_workflow_templates",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    university_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "universities.id",
            name="fk_workflow_instances_university_id_universities",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "it_programs.id",
            name="fk_workflow_instances_program_id_it_programs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "it_products.id",
            name="fk_workflow_instances_product_id_it_products",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    template: Mapped[WorkflowTemplate] = relationship()
    university: Mapped["University"] = relationship()
    program: Mapped["ITProgram | None"] = relationship()
    product: Mapped["ITProduct | None"] = relationship()
    stages: Mapped[list["WorkflowInstanceStage"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowInstanceStage.order_index",
    )
    transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowTransition.created_at",
    )
    comments: Mapped[list["WorkflowComment"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowComment.created_at",
    )
    tasks: Mapped[list["WorkflowTask"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["WorkflowAttachment"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )

    @property
    def current_stage(self) -> "WorkflowInstanceStage | None":
        return next((stage for stage in self.stages if stage.status == "current"), None)

    @property
    def current_stage_code(self) -> str | None:
        current = self.current_stage
        return current.template_stage.code if current and current.template_stage else None

    @property
    def progress_percent(self) -> float:
        if not self.stages:
            return 0.0
        done = sum(stage.status in {"completed", "skipped"} for stage in self.stages)
        return round(done / len(self.stages) * 100, 2)

    @property
    def is_overdue(self) -> bool:
        return _is_overdue(self.due_date, self.status == "active")

    @property
    def days_overdue(self) -> int:
        return _overdue_days(self.due_date, self.status == "active")


class WorkflowInstanceStage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "instance_stages"
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "template_stage_id", name="uq_instance_stages_stage"
        ),
        Index("ix_instance_stages_instance_order", "instance_id", "order_index"),
        Index("ix_instance_stages_status_due", "status", "due_date"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_instance_stages_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    template_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_stages.id",
            name="fk_instance_stages_template_stage_id_workflow_stages",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_keycloak_sub: Mapped[str | None] = mapped_column(String(256), nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="stages")
    template_stage: Mapped[WorkflowTemplateStage] = relationship()

    @property
    def is_overdue(self) -> bool:
        return _is_overdue(
            self.due_date, self.status in {"pending", "current", "overdue"}
        )

    @property
    def days_overdue(self) -> int:
        return _overdue_days(
            self.due_date, self.status in {"pending", "current", "overdue"}
        )


class WorkflowTransition(UUIDPKMixin, Base):
    __tablename__ = "transitions"
    __table_args__ = (Index("ix_transitions_instance_created", "instance_id", "created_at"),)

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_transitions_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_transitions_from_stage_id_instance_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_transitions_to_stage_id_instance_stages",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="next")
    actor_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    instance: Mapped[WorkflowInstance] = relationship(back_populates="transitions")


class WorkflowComment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_instance_created", "instance_id", "created_at"),)

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_comments_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    instance_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_comments_stage_id_instance_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    author_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="comments")


class WorkflowTask(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_instance_due", "instance_id", "status", "due_date"),)

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_tasks_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    instance_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_tasks_stage_id_instance_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assignee_keycloak_sub: Mapped[str | None] = mapped_column(String(256), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_keycloak_sub: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="tasks")

    @property
    def is_overdue(self) -> bool:
        return _is_overdue(self.due_date, self.status == "open")

    @property
    def days_overdue(self) -> int:
        return _overdue_days(self.due_date, self.status == "open")


class WorkflowAttachment(UUIDPKMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "document_id", name="uq_attachments_document"
        ),
        Index("ix_attachments_instance", "instance_id"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "workflow_instances.id",
            name="fk_attachments_instance_id_workflow_instances",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    instance_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "instance_stages.id",
            name="fk_attachments_stage_id_instance_stages",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            name="fk_attachments_document_id_documents",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    created_by_keycloak_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    instance: Mapped[WorkflowInstance] = relationship(back_populates="attachments")

"""P2-01-01 canonical ORM for workflow templates/stages.

Runtime-only description of SQL migration ``000011_workflow_templates``
(which is the schema source of truth): types, nullability, FK, constraints
and indexes mirror the ``*.up.sql`` exactly. Never drives DDL.

Legacy ``app/modules/workflow/models.py`` (int PKs on ``DeferredBase``) is
intentionally NOT reused.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class WorkflowTemplate(UUIDPKMixin, TimestampMixin, Base):
    """Process definition (e.g. the standard 14-stage university route)."""

    __tablename__ = "workflow_templates"
    __table_args__ = (UniqueConstraint("name", name="uq_workflow_templates_name"),)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stages: Mapped[list["WorkflowStage"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowStage.order_index",
        lazy="selectin",
    )


class WorkflowStage(UUIDPKMixin, TimestampMixin, Base):
    """One ordered step of a template. ``order_index`` is 1-based and dense."""

    __tablename__ = "workflow_stages"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "order_index",
            name="uq_workflow_stages_template_order",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("order_index >= 1", name="ck_workflow_stages_order_index_ge_1"),
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
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sla_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    template: Mapped["WorkflowTemplate"] = relationship(back_populates="stages")

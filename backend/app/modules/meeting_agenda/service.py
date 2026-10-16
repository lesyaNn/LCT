"""Bounded column queries only: no relationship loading, N+1, files or LLMs."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, SecurityError
from app.core.policies import ensure_university_visible
from app.core.security import CurrentUser
from app.models.catalog import ITDirection, ITProduct, ITProgram, License, University
from app.models.enums import EXPIRY_WARNING_DAYS
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowComment, WorkflowInstance
from app.modules.meeting_agenda.schemas import (
    AgendaLicense,
    AgendaProgram,
    AgendaQuestion,
    AgendaSection,
    MeetingAgenda,
)
from app.schemas.errors import ErrorCode

PREVIEW_LIMIT = 100
MEETING_STAGE_ORDER = 3


def _section(db: Session, statement, dto, *, transform=None):
    # One snapshot/query per section: count and page cannot disagree if another
    # request closes a question concurrently. Window runs before LIMIT.
    rows = list(
        db.execute(
            statement.add_columns(
                func.count().over().label("_total"),
            ).limit(PREVIEW_LIMIT)
        ).mappings()
    )
    total = rows[0]["_total"] if rows else 0
    items = [dto.model_validate(transform(row) if transform else row) for row in rows]
    return AgendaSection[dto](items=items, total=total, omitted=max(0, total - len(items)))


def build_agenda(db: Session, instance_id: UUID, user: CurrentUser) -> MeetingAgenda:
    # Fetch only the scope key before authorization. In particular, don't load
    # comments through WorkflowInstance's selectin relationships before the gate.
    instance = (
        db.execute(
            select(
                WorkflowInstance.university_id,
                WorkflowInstance.status,
                WorkflowInstance.current_instance_stage_id,
            ).where(WorkflowInstance.id == instance_id)
        )
        .mappings()
        .one_or_none()
    )
    if instance is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    ensure_university_visible(instance["university_id"], user)
    stage = (
        db.execute(
            select(InstanceStage.id, InstanceStage.name, InstanceStage.order_index).where(
                InstanceStage.id == instance["current_instance_stage_id"],
                InstanceStage.instance_id == instance_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        instance["status"] != "active"
        or stage is None
        or stage["order_index"] != MEETING_STAGE_ORDER
    ):
        raise BusinessException(
            ErrorCode.CONFLICT, details={"reason": "meeting_agenda_requires_stage_3"}
        )
    university_id = instance["university_id"]
    university = (
        db.execute(
            select(University.name, University.city).where(
                University.id == university_id,
            )
        )
        .mappings()
        .one()
    )
    generated = datetime.now(UTC)
    today = generated.date()
    through = today + timedelta(days=EXPIRY_WARNING_DAYS)

    programs = (
        select(
            ITProgram.id.label("program_id"),
            ITProgram.name,
            ITDirection.name.label("direction"),
            UniversityProgram.status,
            UniversityProgram.launch_date,
        )
        .select_from(UniversityProgram)
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .join(
            ITDirection,
            ITDirection.id == ITProgram.direction_id,
        )
        .where(
            UniversityProgram.university_id == university_id,
            UniversityProgram.status.in_(("active", "launched")),
        )
        .order_by(ITProgram.name, ITProgram.id)
    )

    licenses = (
        select(
            License.id.label("license_id"),
            License.license_number,
            ITProduct.name.label("product"),
            License.expires_at,
        )
        .join(ITProduct, ITProduct.id == License.product_id)
        .where(
            License.university_id == university_id,
            License.expires_at.between(today, through),
        )
        .order_by(License.expires_at, License.id)
    )
    # Compute the day offset in Python, preserving the shared inclusive 0..30
    # calendar-day rule without a DB-specific DATE subtraction expression.
    questions = (
        select(
            WorkflowComment.id.label("comment_id"),
            WorkflowComment.instance_id,
            WorkflowComment.stage_id,
            WorkflowComment.content,
            WorkflowComment.created_at,
        )
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowComment.instance_id)
        .where(
            WorkflowInstance.university_id == university_id,
            WorkflowInstance.status != "archived",
            WorkflowComment.question_status == "open",
        )
        .order_by(WorkflowComment.created_at, WorkflowComment.id)
    )
    return MeetingAgenda(
        university_id=university_id,
        university_name=university["name"],
        city=university["city"],
        instance_id=instance_id,
        stage_id=stage["id"],
        stage_name=stage["name"],
        stage_order=stage["order_index"],
        generated_at=generated,
        as_of=today,
        expires_through=through,
        warning_days=EXPIRY_WARNING_DAYS,
        programs=_section(db, programs, AgendaProgram),
        expiring_licenses=_section(
            db,
            licenses,
            AgendaLicense,
            transform=lambda row: {
                **row,
                "days_left": (row["expires_at"] - today).days,
            },
        ),
        open_questions=_section(db, questions, AgendaQuestion),
    )


def set_question_status(
    db: Session, comment_id: UUID, status: str, user: CurrentUser
) -> WorkflowComment:
    row = (
        db.execute(
            select(WorkflowComment.instance_id, WorkflowComment.author_keycloak_sub).where(
                WorkflowComment.id == comment_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    instance = (
        db.execute(
            select(WorkflowInstance.university_id, WorkflowInstance.status).where(
                WorkflowInstance.id == row["instance_id"],
            )
        )
        .mappings()
        .one()
    )
    ensure_university_visible(instance["university_id"], user)
    if row["author_keycloak_sub"] != user.id and not {"admin", "manager"}.intersection(
        user.roles or ()
    ):
        raise SecurityError(ErrorCode.FORBIDDEN)
    if instance["status"] == "archived":
        raise BusinessException(ErrorCode.CONFLICT, details={"reason": "workflow_archived"})
    if status not in {"none", "open", "resolved"}:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    comment = db.get(WorkflowComment, comment_id)
    if comment is None:  # deleted concurrently after the scope lookup
        raise BusinessException(ErrorCode.NOT_FOUND)
    comment.question_status = status
    # The before_flush audit listener stores status/actor/time, never the text.
    db.commit()
    db.refresh(comment)
    return comment

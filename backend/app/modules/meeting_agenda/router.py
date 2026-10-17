"""Backend endpoints for visited Workflow meeting stages."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.audit.service import (
    AuditAction,
    AuditEntityType,
    AuditService,
    context_for,
    get_audit_db,
)
from app.modules.meeting_agenda import service
from app.modules.meeting_agenda.pdf import generate_agenda_pdf
from app.modules.meeting_agenda.schemas import MeetingAgenda
from app.modules.workflow_transitions.schemas import WorkflowCommentRead, WorkflowQuestionUpdate
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/workflow", tags=["Meeting agenda"])
READ = require_permission("workflow.read")
WRITE = require_permission("workflow.comment.update")
logger = logging.getLogger(__name__)
Database = Annotated[Session, Depends(get_audit_db)]
Reader = Annotated[CurrentUser, Depends(READ)]
Writer = Annotated[CurrentUser, Depends(WRITE)]


@router.get(
    "/instances/{instance_id}/meeting-agenda",
    response_model=MeetingAgenda,
    summary="Данные повестки этапа встречи",
)
def get_agenda(instance_id: UUID, response: Response, db: Database, user: Reader, stage_id: UUID | None = None) -> MeetingAgenda:
    response.headers["Cache-Control"] = "no-store"
    return service.build_agenda(db, instance_id, user, stage_id)


@router.get(
    "/instances/{instance_id}/meeting-agenda.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Одностраничный A4 PDF"}},
    summary="Скачать PDF-повестку этапа встречи",
)
def download_agenda(instance_id: UUID, db: Database, user: Reader, stage_id: UUID | None = None) -> Response:
    agenda = service.build_agenda(db, instance_id, user, stage_id)
    try:
        content = generate_agenda_pdf(agenda)
    except Exception as exc:
        # Do not log exception strings, SQL values or question contents.
        logger.error("meeting_agenda_pdf_failed error_type=%s", type(exc).__name__)
        raise BusinessException(ErrorCode.REPORT_FAILED) from exc
    AuditService(db).log_event(
        context=context_for(db),
        action=AuditAction.REPORT_GENERATE,
        entity_type=AuditEntityType.WORKFLOW_INSTANCE,
        entity_id=instance_id,
        university_id=agenda.university_id,
        new_value={
            "report_kind": "meeting_agenda",
            "format": "pdf",
            "program_count": agenda.programs.total,
            "expiring_license_count": agenda.expiring_licenses.total,
            "open_question_count": agenda.open_questions.total,
        },
    )
    db.commit()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="meeting-agenda-{instance_id}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch(
    "/comments/{comment_id}/question-status",
    response_model=WorkflowCommentRead,
    summary="Отметить, закрыть или переоткрыть вопрос",
)
def set_question_status(
    comment_id: UUID, data: WorkflowQuestionUpdate, response: Response, db: Database, user: Writer
):
    response.headers["Cache-Control"] = "no-store"
    return service.set_question_status(db, comment_id, data.status, user)

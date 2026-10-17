"""Authenticated JSON API for the documentation assistant and private conversations."""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BusinessException
from app.core.permissions import effective_role, require_permission
from app.core.rate_limit import bucket_key, check_rate_limit, hash_client_id
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.assistant.knowledge import get_knowledge
from app.modules.assistant.provider import Ollama
from app.modules.assistant.quick_replies import QUICK_REPLIES, QUICK_REPLY_VERSION
from app.modules.assistant.repository import Conversations
from app.modules.assistant.schemas import (
    ChatIn,
    ChatOut,
    ConversationPage,
    StatusOut,
    TurnPage,
    QuickReplyCatalog,
    QuickReplyOption,
)
from app.modules.assistant.service import Assistant
from app.schemas.errors import ErrorCode, ErrorResponse

router = APIRouter(
    prefix="/assistant",
    tags=["Assistant"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503, 504)},
)
User = Annotated[CurrentUser, Depends(require_permission("assistant.use"))]
Database = Annotated[Session, Depends(get_db)]


@lru_cache(maxsize=1)
def get_assistant() -> Assistant:
    return Assistant(settings, get_knowledge(settings), Ollama(settings))


Engine = Annotated[Assistant, Depends(get_assistant)]


@router.get("/quick-replies", response_model=QuickReplyCatalog, summary="Быстрые вопросы помощника")
def quick_replies(user: User) -> QuickReplyCatalog:
    """Согласованные вопросы для кнопок. Не обращается к модели, индексу или базе.

    Для ответа отправьте question обычным POST /assistant/chat. Проверки прав,
    включения помощника, ограничения частоты и приватной истории сохраняются.
    """
    return QuickReplyCatalog(
        version=QUICK_REPLY_VERSION,
        items=[QuickReplyOption(id=reply.id, question=reply.question) for reply in QUICK_REPLIES],
    )


@router.get("/status", response_model=StatusOut, summary="Готовность помощника")
def status(user: User, db: Database, engine: Engine) -> StatusOut:
    """Доступность модели и документации; не загружает и не скачивает модели."""
    return engine.status(
        effective_role(user), Conversations(db, user.id, effective_role(user), settings)
    )


@router.post("/chat", response_model=ChatOut, summary="Задать вопрос по документации")
def chat(data: ChatIn, user: User, db: Database, engine: Engine) -> ChatOut:
    """Обычный JSON ответ с источниками. conversation_id продолжает собственный диалог.

    expected_revision позволяет отклонить устаревший запрос до генерации ответа.
    После параллельного изменения диалога возвращается 409. Ошибка модели не
    сохраняет незавершённую пару сообщений. Вопросы ограничены 2000 символами.
    """
    key = bucket_key("assistant.chat", hash_client_id(user.id))
    allowed, retry = check_rate_limit(key, settings.assistant_rate_limit_per_minute)
    if not allowed:
        raise BusinessException(ErrorCode.RATE_LIMITED, details={"retry_after_seconds": retry})
    return engine.chat(
        data, effective_role(user), Conversations(db, user.id, effective_role(user), settings)
    )


@router.get("/conversations", response_model=ConversationPage, summary="Мои диалоги")
def conversations(
    user: User,
    db: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> ConversationPage:
    """Диалоги текущего пользователя и роли за срок хранения, новые в начале."""
    return Conversations(db, user.id, effective_role(user), settings).list(page, page_size)


@router.get(
    "/conversations/{conversation_id}", response_model=TurnPage, summary="История моего диалога"
)
def history(
    conversation_id: UUID,
    user: User,
    db: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
) -> TurnPage:
    """Полные пары вопрос/ответ в хронологическом порядке. Чужой диалог возвращает 404."""
    return Conversations(db, user.id, effective_role(user), settings).history(
        conversation_id, page, page_size
    )


@router.delete("/conversations/{conversation_id}", status_code=204, summary="Удалить мой диалог")
def remove(conversation_id: UUID, user: User, db: Database) -> Response:
    """Удаляет диалог вместе с сообщениями. Чужой или отсутствующий диалог возвращает 404."""
    Conversations(db, user.id, effective_role(user), settings).remove(conversation_id)
    return Response(status_code=204)

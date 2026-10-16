"""Owner-scoped SQL persistence; no open transaction while Ollama generates a reply."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import BusinessException
from app.models.assistant import AssistantConversation, AssistantTurn
from app.modules.assistant.schemas import (
    ChatIn,
    ChatOut,
    ConversationOut,
    ConversationPage,
    TurnOut,
    TurnPage,
)
from app.schemas.errors import ErrorCode


@dataclass(frozen=True)
class Prepared:
    id: uuid.UUID
    revision: int
    history: tuple[tuple[str, str], ...]
    is_new: bool


class Conversations:
    def __init__(self, db: Session, subject: str, role: str, config: Settings):
        self.db, self.subject, self.role, self.config = db, subject, role, config

    def _scope(self):
        return (
            AssistantConversation.owner_sub == self.subject,
            AssistantConversation.role == self.role,
            AssistantConversation.updated_at >= self.cutoff(),
        )

    def cutoff(self):
        return datetime.now(UTC) - timedelta(days=self.config.assistant_retention_days)

    def ready(self) -> bool:
        """Probe both required tables without reading anyone's chat contents."""
        try:
            self.db.execute(select(AssistantConversation.id).limit(0))
            self.db.execute(select(AssistantTurn.id).limit(0))
            return True
        except SQLAlchemyError:
            return False
        finally:
            self.db.rollback()

    def owned(self, conversation_id: uuid.UUID) -> AssistantConversation:
        row = self.db.scalar(
            select(AssistantConversation).where(
                AssistantConversation.id == conversation_id, *self._scope()
            )
        )
        if row is None:
            raise BusinessException(ErrorCode.NOT_FOUND)
        return row

    def prepare(self, data: ChatIn) -> Prepared:
        try:
            if data.conversation_id is None:
                if data.expected_revision not in {None, 0}:
                    raise BusinessException(ErrorCode.CONFLICT, details={"field": "revision"})
                return Prepared(uuid.uuid4(), 0, (), True)
            row = self.owned(data.conversation_id)
            if data.expected_revision is not None and row.revision != data.expected_revision:
                raise BusinessException(ErrorCode.CONFLICT, details={"field": "revision"})
            if row.revision >= self.config.assistant_max_turns:
                raise BusinessException(ErrorCode.CONFLICT, details={"reason": "turn_limit"})
            turns = []
            if self.config.assistant_history_turns:
                turns = list(
                    self.db.scalars(
                        select(AssistantTurn)
                        .where(AssistantTurn.conversation_id == row.id)
                        .order_by(AssistantTurn.position.desc())
                        .limit(self.config.assistant_history_turns)
                    )
                )
            return Prepared(
                row.id,
                row.revision,
                tuple((turn.question, turn.answer) for turn in reversed(turns)),
                False,
            )
        except SQLAlchemyError:
            raise BusinessException(ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE) from None
        finally:
            # Release the read transaction/connection before any HTTP inference.
            self.db.rollback()

    def save(self, prepared: Prepared, question: str, result: ChatOut) -> ChatOut:
        try:
            if prepared.is_new:
                self.db.add(
                    AssistantConversation(
                        id=prepared.id,
                        owner_sub=self.subject,
                        role=self.role,
                        title=" ".join(question.split())[:120],
                        revision=result.revision,
                        created_at=result.created_at,
                        updated_at=result.created_at,
                    )
                )
                self.db.flush()
            else:
                changed = self.db.execute(
                    update(AssistantConversation)
                    .where(
                        AssistantConversation.id == prepared.id,
                        AssistantConversation.revision == prepared.revision,
                        *self._scope(),
                    )
                    .values(revision=result.revision, updated_at=result.created_at)
                )
                if changed.rowcount != 1:
                    raise BusinessException(ErrorCode.CONFLICT, details={"field": "revision"})
            self.db.add(
                AssistantTurn(
                    id=result.turn_id,
                    conversation_id=prepared.id,
                    position=result.revision,
                    question=question,
                    answer=result.answer,
                    basis=result.basis,
                    sources=[source.model_dump() for source in result.sources],
                    knowledge_version=result.knowledge_version,
                    retrieval_mode=result.retrieval_mode,
                    model=result.model,
                    created_at=result.created_at,
                )
            )
            self.db.commit()
            return result
        except SQLAlchemyError:
            self.db.rollback()
            # SQLAlchemy exceptions can contain question/answer bind parameters.
            # Do not send those to the global exception logger.
            raise BusinessException(ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE) from None
        except BusinessException:
            self.db.rollback()
            raise

    def list(self, page: int, page_size: int) -> ConversationPage:
        try:
            total = (
                self.db.scalar(
                    select(func.count()).select_from(AssistantConversation).where(*self._scope())
                )
                or 0
            )
            rows = self.db.scalars(
                select(AssistantConversation)
                .where(*self._scope())
                .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return ConversationPage(
                items=[ConversationOut.model_validate(row) for row in rows],
                total=total,
                page=page,
                page_size=page_size,
            )
        except SQLAlchemyError:
            self.db.rollback()
            raise BusinessException(ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE) from None

    def history(self, conversation_id: uuid.UUID, page: int, page_size: int) -> TurnPage:
        try:
            conversation = ConversationOut.model_validate(self.owned(conversation_id))
            rows = self.db.scalars(
                select(AssistantTurn)
                .where(AssistantTurn.conversation_id == conversation_id)
                .order_by(AssistantTurn.position)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return TurnPage(
                conversation=conversation,
                total=conversation.revision,
                page=page,
                page_size=page_size,
                items=[
                    TurnOut(
                        conversation_id=row.conversation_id,
                        turn_id=row.id,
                        revision=row.position,
                        question=row.question,
                        answer=row.answer,
                        basis=row.basis,
                        sources=row.sources,
                        knowledge_version=row.knowledge_version,
                        retrieval_mode=row.retrieval_mode,
                        model=row.model,
                        created_at=row.created_at,
                    )
                    for row in rows
                ],
            )
        except SQLAlchemyError:
            self.db.rollback()
            raise BusinessException(ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE) from None

    def remove(self, conversation_id: uuid.UUID) -> None:
        try:
            changed = self.db.execute(
                delete(AssistantConversation).where(
                    AssistantConversation.id == conversation_id,
                    AssistantConversation.owner_sub == self.subject,
                    AssistantConversation.role == self.role,
                )
            )
            if changed.rowcount != 1:
                raise BusinessException(ErrorCode.NOT_FOUND)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise BusinessException(ErrorCode.ASSISTANT_STORAGE_UNAVAILABLE) from None
        except BusinessException:
            self.db.rollback()
            raise

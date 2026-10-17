"""Small, permission-scoped search over user-facing CRM records."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.permissions import effective_role, user_permissions
from app.core.policies import apply_university_scope
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.catalog import Contract, ITProduct, ITProgram, Responsible, University, UniversityResponsible
from app.models.interactions import Document, UniversityProduct
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.config import settings
from app.modules.assistant.knowledge import get_knowledge, lexical_ranking
from app.modules.catalog.repository import like_pattern, list_universities

router = APIRouter(prefix="/search", tags=["search"])
LIMIT = 5


class SearchHit(BaseModel):
    id: UUID
    title: str
    subtitle: str | None = None
    university_id: UUID | None = None


class WorkflowHit(SearchHit):
    status: str
    stage: str | None = None


class DocumentationHit(BaseModel):
    id: str
    title: str
    subtitle: str
    href: str


class SearchResults(BaseModel):
    universities: list[SearchHit] = []
    workflows: list[WorkflowHit] = []
    documents: list[SearchHit] = []
    contracts: list[SearchHit] = []
    products: list[SearchHit] = []
    responsibles: list[SearchHit] = []
    documentation: list[DocumentationHit] = []


def search(db: Session, user: CurrentUser, q: str, records_q: str | None = None) -> SearchResults:
    term = q.strip()
    if len(term) < 2:
        return SearchResults()
    permissions = user_permissions(user)
    record_term = term if records_q is None else records_q.strip()
    pattern = like_pattern(record_term)
    result = SearchResults()
    if len(record_term) >= 2 and "university.read" in permissions:
        rows, _ = list_universities(
            db, page=1, page_size=LIMIT, search=record_term, city=None,
            responsible_id=None, sort_by="name", sort_order="asc", user=user,
        )
        result.universities = [SearchHit(id=row.id, title=row.name, subtitle=row.city) for row in rows]
        docs = apply_university_scope(
            select(Document.id, Document.title, Document.university_id, University.name)
            .join(University, University.id == Document.university_id)
            .where(or_(Document.title.ilike(pattern, escape="\\"), University.name.ilike(pattern, escape="\\"))), Document.university_id, user,
        )
        result.documents = [SearchHit(id=id, title=title, subtitle=name, university_id=university_id)
                            for id, title, university_id, name in db.execute(docs.order_by(Document.title, Document.id).limit(LIMIT))]
        contracts = apply_university_scope(
            select(Contract.id, Contract.contract_number, Contract.university_id, University.name)
            .join(University, University.id == Contract.university_id)
            .where(or_(Contract.contract_number.ilike(pattern, escape="\\"), University.name.ilike(pattern, escape="\\"))), Contract.university_id, user,
        )
        result.contracts = [SearchHit(id=id, title=number, subtitle=name, university_id=university_id)
                            for id, number, university_id, name in db.execute(contracts.order_by(Contract.contract_number, Contract.id).limit(LIMIT))]
        products = apply_university_scope(
            select(ITProduct.id, ITProduct.name, UniversityProduct.university_id, University.name)
            .join(UniversityProduct, UniversityProduct.product_id == ITProduct.id)
            .join(University, University.id == UniversityProduct.university_id)
            .where(ITProduct.name.ilike(pattern, escape="\\")), UniversityProduct.university_id, user,
        )
        result.products = [SearchHit(id=id, title=name, subtitle=university_name, university_id=university_id)
                           for id, name, university_id, university_name in db.execute(products.order_by(ITProduct.name, UniversityProduct.university_id).limit(LIMIT))]
        responsibles = apply_university_scope(
            select(Responsible.id, Responsible.full_name, UniversityResponsible.university_id, University.name)
            .join(UniversityResponsible, UniversityResponsible.responsible_id == Responsible.id)
            .join(University, University.id == UniversityResponsible.university_id)
            .where(Responsible.full_name.ilike(pattern, escape="\\")), UniversityResponsible.university_id, user,
        )
        result.responsibles = [SearchHit(id=id, title=name, subtitle=university_name, university_id=university_id)
                              for id, name, university_id, university_name in db.execute(responsibles.order_by(Responsible.full_name, UniversityResponsible.university_id).limit(LIMIT))]
    if len(record_term) >= 2 and "workflow.read" in permissions:
        workflows = apply_university_scope(
            select(WorkflowInstance.id, WorkflowInstance.status, WorkflowInstance.university_id,
                   University.name, ITProgram.name, InstanceStage.name)
            .join(University, University.id == WorkflowInstance.university_id)
            .outerjoin(ITProgram, ITProgram.id == WorkflowInstance.program_id)
            .outerjoin(InstanceStage, InstanceStage.id == WorkflowInstance.current_instance_stage_id)
            .where(WorkflowInstance.status != "archived")
            .where(or_(University.name.ilike(pattern, escape="\\"), ITProgram.name.ilike(pattern, escape="\\"), InstanceStage.name.ilike(pattern, escape="\\"))),
            WorkflowInstance.university_id, user,
        )
        result.workflows = [WorkflowHit(id=id, title=f"{university_name} · {program_name or 'Workflow'}",
                                        subtitle="Завершён" if status == "completed" else stage_name or "В работе",
                                        university_id=university_id, status=status, stage=stage_name)
                            for id, status, university_id, university_name, program_name, stage_name
                            in db.execute(workflows.order_by(University.name, WorkflowInstance.id).limit(LIMIT))]
    if "assistant.use" in permissions:
        ranked = lexical_ranking(term, get_knowledge(settings).snapshot().visible(effective_role(user)))
        seen: set[str] = set()
        for chunk, _ in ranked:
            if chunk.article_id in seen:
                continue
            seen.add(chunk.article_id)
            result.documentation.append(DocumentationHit(
                id=chunk.article_id,
                title=chunk.title,
                subtitle=" ".join(chunk.text.split())[:150],
                href=chunk.url,
            ))
            if len(result.documentation) == LIMIT:
                break
    return result


@router.get(
    "",
    response_model=SearchResults,
    summary="Глобальный поиск по CRM",
    description="Ищет доступные записи CRM и материалы документации по строке q (минимум 2 символа, до 5 совпадений на раздел). Состав выдачи зависит от прав пользователя.",
)
def global_search(q: str = Query(default="", max_length=100), db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user),
                  records_q: str | None = Query(default=None, max_length=100)) -> SearchResults:
    return search(db, user, q, records_q)

"""P1-03 catalog HTTP API (mounted under /api/v1).

Thin routes: query params -> RBAC -> service -> DTO. No SQL and no business
logic here. RBAC uses ``university.read`` for GET, ``catalog.manage``
for catalog mutations, and ``university.edit`` for passport relationships. Includes the read-only
``/catalog/overview`` import viewer.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, require_role
from app.core.policies import ensure_university_visible
from app.core.security import CurrentUser
from app.modules.analytics.filters import UnifiedFilter, get_unified_filter
from app.modules.audit.service import get_audit_db
from app.modules.catalog import passport_relations, service
from app.modules.catalog.contract_files import attach_contract_file, contract_or_404, detach_contract_file
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import StorageBackend
from app.modules.catalog.schemas import (
    ContractCreate,
    ContractDetail,
    ContractRead,
    ContractUpdate,
    DirectionDetail,
    DirectionRead,
    LicenseCreate,
    LicenseRead,
    LicenseUpdate,
    ProductDetail,
    ProductRead,
    PrimaryResponsibleChange,
    ProgramDetail,
    ProgramRead,
    ResponsibleAssign,
    ResponsibleCreate,
    ResponsibleDetail,
    ResponsibleRead,
    ResponsibleUpdate,
    UniversityDetail,
    UniversityListItem,
    UniversityResponsibleRead,
    UniversityProgramAttach,
    UniversityProgramRead,
    UniversityProductAttach,
    UniversityProductRead,
    VendorDetail,
    VendorRead,
)
from app.schemas.catalog import (
    DirectionCreate,
    DirectionUpdate,
    ProductCreate,
    ProductUpdate,
    ProgramCreate,
    ProgramUpdate,
    VendorCreate,
    VendorUpdate,
)
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.university import UniversityCreate, UniversityUpdate

router = APIRouter()

READ = require_permission("university.read")
WRITE = require_permission("university.edit")
CATALOG_WRITE = require_permission("catalog.manage")


UniversitySortBy = Literal["name", "city", "created_at"]
HealthStatusFilter = Literal["green", "yellow", "red"]
DirectionSortBy = Literal["code", "name", "created_at"]
ProgramSortBy = Literal["name", "created_at"]
ProductSortBy = Literal["name", "version", "created_at"]
VendorSortBy = Literal["name", "created_at"]
ResponsibleSortBy = Literal["full_name", "email", "created_at"]
ContractSortBy = Literal["contract_number", "signed_at", "expires_at", "created_at"]
LicenseSortBy = Literal["license_number", "signed_at", "expires_at", "created_at"]
SortOrder = Literal["asc", "desc"]


def _norm(search: str | None) -> str | None:
    """Empty/blank search behaves as no filter."""
    if search is None or not search.strip():
        return None
    return search.strip()


# ------------------------------------------------------------- universities


@router.post(
    "/universities",
    response_model=UniversityDetail,
    status_code=201,
    tags=["Universities"],
    summary="Создать вуз",
    description="Создаёт вуз с названием и городом. Требуется право catalog.manage.",
)
def create_university(
    data: UniversityCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> UniversityDetail:
    return service.create_university(db, name=data.name, city=data.city)


@router.get(
    "/universities",
    response_model=PaginatedResponse[UniversityListItem],
    tags=["Universities"],
    summary="Список вузов",
    description="Возвращает страницу вузов с поиском по названию и городу, фильтрами (город, ответственный, стадия Workflow) и сортировкой. Требуется право university.read.",
)
def list_universities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name/city"),
    city: str | None = Query(default=None, description="Exact city filter"),
    responsible_id: uuid.UUID | None = Query(
        default=None, description="Only universities linked to this responsible"
    ),
    region: str | None = Query(
        default=None,
        deprecated=True,
        description="Legacy param, accepted and ignored (no region column in P1 schema)",
    ),
    sort_by: UniversitySortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    external_source: Literal["website"] | None = Query(default=None),
    workflow_stage: str | None = Query(default=None, description="Current stage name of the latest Workflow"),
    unified: UnifiedFilter = Depends(get_unified_filter),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[UniversityListItem]:
    _ = region  # deprecated no-op, kept for backward compatibility (P1-11-03)
    items, total = service.list_university_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        city=city,
        responsible_id=responsible_id,
        sort_by=sort_by,
        sort_order=sort_order,
        unified_filter=unified,
        user=user,
        external_source=external_source,
        workflow_stage=workflow_stage,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/universities/stage-options",
    response_model=list[str],
    tags=["Universities"],
    summary="Стадии Workflow вузов",
    description="Возвращает названия текущих стадий Workflow для видимых пользователю вузов. Требуется право university.read.",
)
def university_stage_options(
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> list[str]:
    from app.modules.catalog.repository import list_university_stage_names

    return list_university_stage_names(db, user=user)


@router.get(
    "/universities/{university_id}",
    response_model=UniversityDetail,
    tags=["Universities"],
    summary="Получить вуз по id",
    description="Возвращает вуз по id вместе со связанными ответственными. Требуется право university.read.",
)
def get_university(
    university_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> UniversityDetail:
    # H5: scope is enforced inside the SELECT (404 for missing and foreign
    # alike) — no unscoped load followed by a second check query.
    return service.get_university_detail(db, university_id, user=user)


@router.patch(
    "/universities/{university_id}",
    response_model=UniversityDetail,
    tags=["Universities"],
    summary="Частично обновить вуз",
    description="Частично обновляет название и город вуза. Требуется право catalog.manage.",
)
def patch_university(
    university_id: uuid.UUID,
    data: UniversityUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> UniversityDetail:
    ensure_university_visible(university_id, user)
    fields = data.model_fields_set
    return service.patch_university(
        db,
        university_id,
        name=data.name if "name" in fields else None,
        city=data.city if "city" in fields else None,
        update_name="name" in fields,
        update_city="city" in fields,
    )


@router.delete(
    "/universities/{university_id}",
    response_model=None,
    status_code=204,
    tags=["Universities"],
    summary="Удалить вуз",
    description="Безвозвратно удаляет вуз; при наличии связанных записей возвращается 409. Требуется право catalog.manage.",
)
def delete_university(
    university_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    ensure_university_visible(university_id, user)
    service.delete_university(db, university_id)


@router.post(
    "/universities/{university_id}/programs",
    response_model=UniversityProgramRead,
    status_code=201,
    tags=["Universities"],
    summary="Привязать программу к вузу",
    description="Привязывает существующую программу каталога к вузу. Требуется право university.edit.",
)
def attach_university_program(
    university_id: uuid.UUID,
    data: UniversityProgramAttach,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> UniversityProgramRead:
    ensure_university_visible(university_id, user)
    return passport_relations.attach_program(db, university_id, data)


@router.post(
    "/universities/{university_id}/products",
    response_model=UniversityProductRead,
    status_code=201,
    tags=["Universities"],
    summary="Привязать продукт к вузу",
    description="Привязывает существующий продукт каталога к вузу. Требуется право university.edit.",
)
def attach_university_product(
    university_id: uuid.UUID,
    data: UniversityProductAttach,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> UniversityProductRead:
    ensure_university_visible(university_id, user)
    return passport_relations.attach_product(db, university_id, data)


@router.patch(
    "/universities/{university_id}/responsibles/primary",
    response_model=UniversityResponsibleRead,
    tags=["Universities"],
    summary="Сменить основного ответственного",
    description="Атомарно меняет основного ответственного вуза. Требуется право university.edit.",
)
def change_primary_responsible(
    university_id: uuid.UUID,
    data: PrimaryResponsibleChange,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> UniversityResponsibleRead:
    ensure_university_visible(university_id, user)
    return passport_relations.change_primary_responsible(db, university_id, data)


@router.post(
    "/universities/{university_id}/responsibles/{responsible_id}",
    response_model=UniversityResponsibleRead,
    tags=["Universities"],
    summary="Назначить ответственного вузу",
    description="Назначает ответственного вузу (идемпотентно: 201 при создании связи, 200 если связь уже есть). Требуются роли admin или manager.",
)
def assign_responsible(
    university_id: uuid.UUID,
    responsible_id: uuid.UUID,
    data: ResponsibleAssign | None = Body(default=None),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_role("admin", "manager")),
):
    ensure_university_visible(university_id, user)
    link, created = service.assign_responsible(db, university_id, responsible_id, data)
    return JSONResponse(
        status_code=201 if created else 200,
        content=link.model_dump(mode="json"),
    )


@router.delete(
    "/universities/{university_id}/responsibles/{responsible_id}",
    response_model=None,
    status_code=204,
    tags=["Universities"],
    summary="Отвязать ответственного от вуза",
    description="Отвязывает ответственного от вуза. Требуются роли admin или manager.",
)
def unassign_responsible(
    university_id: uuid.UUID,
    responsible_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_role("admin", "manager")),
) -> None:
    ensure_university_visible(university_id, user)
    service.unassign_responsible(db, university_id, responsible_id)


# ------------------------------------------------------------- directions


@router.post(
    "/directions",
    response_model=DirectionDetail,
    status_code=201,
    tags=["Directions"],
    summary="Создать направление",
    description="Создаёт ИТ-направление с кодом и названием. Требуется право catalog.manage.",
)
def create_direction(
    data: DirectionCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> DirectionDetail:
    return service.create_direction(db, code=data.code, name=data.name)


@router.get(
    "/directions",
    response_model=PaginatedResponse[DirectionRead],
    tags=["Directions"],
    summary="Список направлений",
    description="Возвращает страницу направлений с поиском по коду и названию, пагинацией и сортировкой. Требуется право university.read.",
)
def list_directions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on code/name"),
    sort_by: DirectionSortBy = Query(default="code"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[DirectionRead]:
    items, total = service.list_direction_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/directions/{direction_id}",
    response_model=DirectionDetail,
    tags=["Directions"],
    summary="Получить направление по id",
    description="Возвращает направление по id вместе с программами. Требуется право university.read.",
)
def get_direction(
    direction_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> DirectionDetail:
    return service.get_direction_detail(db, direction_id)


@router.patch(
    "/directions/{direction_id}",
    response_model=DirectionDetail,
    tags=["Directions"],
    summary="Частично обновить направление",
    description="Частично обновляет код и название направления. Требуется право catalog.manage.",
)
def patch_direction(
    direction_id: uuid.UUID,
    data: DirectionUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> DirectionDetail:
    return service.patch_direction(db, direction_id, code=data.code, name=data.name)


@router.delete(
    "/directions/{direction_id}",
    response_model=None,
    status_code=204,
    tags=["Directions"],
    summary="Удалить направление",
    description="Безвозвратно удаляет направление; при наличии программ — ошибка (RESTRICT). Требуется право catalog.manage.",
)
def delete_direction(
    direction_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    service.delete_direction(db, direction_id)


# --------------------------------------------------------------- programs


@router.post(
    "/programs",
    response_model=ProgramDetail,
    status_code=201,
    tags=["Programs"],
    summary="Создать программу",
    description="Создаёт программу внутри направления. Требуется право catalog.manage.",
)
def create_program(
    data: ProgramCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ProgramDetail:
    return service.create_program(
        db, direction_id=data.direction_id, name=data.name, description=data.description
    )


@router.get(
    "/programs",
    response_model=PaginatedResponse[ProgramRead],
    tags=["Programs"],
    summary="Список программ",
    description="Возвращает страницу программ с поиском по названию, фильтром по направлению, пагинацией и сортировкой. Требуется право university.read.",
)
def list_programs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    direction_id: uuid.UUID | None = Query(default=None, description="Filter by direction"),
    sort_by: ProgramSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[ProgramRead]:
    items, total = service.list_program_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        direction_id=direction_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/programs/{program_id}",
    response_model=ProgramDetail,
    tags=["Programs"],
    summary="Получить программу по id",
    description="Возвращает программу по id вместе с направлением. Требуется право university.read.",
)
def get_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> ProgramDetail:
    return service.get_program_detail(db, program_id)


@router.patch(
    "/programs/{program_id}",
    response_model=ProgramDetail,
    tags=["Programs"],
    summary="Частично обновить программу",
    description="Частично обновляет программу (направление, название, описание). Требуется право catalog.manage.",
)
def patch_program(
    program_id: uuid.UUID,
    data: ProgramUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ProgramDetail:
    return service.patch_program(
        db,
        program_id,
        direction_id=data.direction_id,
        name=data.name,
        description=data.description,
    )


@router.delete(
    "/programs/{program_id}",
    response_model=None,
    status_code=204,
    tags=["Programs"],
    summary="Удалить программу",
    description="Безвозвратно удаляет программу; при наличии связей — ошибка (RESTRICT). Требуется право catalog.manage.",
)
def delete_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    service.delete_program(db, program_id)


# --------------------------------------------------------------- products


@router.post(
    "/products",
    response_model=ProductDetail,
    status_code=201,
    tags=["Products"],
    summary="Создать продукт",
    description="Создаёт продукт с вендором, программой, названием и версией. Требуется право catalog.manage.",
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ProductDetail:
    return service.create_product(
        db, vendor_id=data.vendor_id, program_id=data.program_id,
        name=data.name, version=data.version,
    )


@router.get(
    "/products",
    response_model=PaginatedResponse[ProductRead],
    tags=["Products"],
    summary="Список продуктов",
    description="Возвращает страницу продуктов с поиском по названию, фильтрами по вендору и направлению, пагинацией и сортировкой. Требуется право university.read.",
)
def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    vendor_id: uuid.UUID | None = Query(default=None, description="Filter by vendor"),
    direction_id: uuid.UUID | None = Query(default=None, description="Filter by direction (via product_directions)"),
    sort_by: ProductSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[ProductRead]:
    items, total = service.list_product_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        vendor_id=vendor_id,
        direction_id=direction_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    tags=["Products"],
    summary="Получить продукт по id",
    description="Возвращает продукт по id вместе с вендором. Требуется право university.read.",
)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> ProductDetail:
    return service.get_product_detail(db, product_id)


@router.patch(
    "/products/{product_id}",
    response_model=ProductDetail,
    tags=["Products"],
    summary="Частично обновить продукт",
    description="Частично обновляет продукт (вендор, название, версия, программа). Требуется право catalog.manage.",
)
def patch_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ProductDetail:
    program_id = data.program_id if "program_id" in data.model_fields_set else service.UNSET
    return service.patch_product(
        db, product_id, vendor_id=data.vendor_id, name=data.name,
        version=data.version, program_id=program_id,
    )


@router.delete(
    "/products/{product_id}",
    response_model=None,
    status_code=204,
    tags=["Products"],
    summary="Удалить продукт",
    description="Безвозвратно удаляет продукт; при наличии лицензий или связей — ошибка (RESTRICT). Требуется право catalog.manage.",
)
def delete_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    service.delete_product(db, product_id)


# ---------------------------------------------------------------- vendors


@router.post(
    "/vendors",
    response_model=VendorDetail,
    status_code=201,
    tags=["Vendors"],
    summary="Создать вендора",
    description="Создаёт вендора с названием и контактами. Требуется право catalog.manage.",
)
def create_vendor(
    data: VendorCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> VendorDetail:
    return service.create_vendor(db, name=data.name, contacts=data.contacts)


@router.get(
    "/vendors",
    response_model=PaginatedResponse[VendorRead],
    tags=["Vendors"],
    summary="Список вендоров",
    description="Возвращает страницу вендоров с поиском по названию, пагинацией и сортировкой. Требуется право university.read.",
)
def list_vendors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    sort_by: VendorSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[VendorRead]:
    items, total = service.list_vendor_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/vendors/{vendor_id}",
    response_model=VendorDetail,
    tags=["Vendors"],
    summary="Получить вендора по id",
    description="Возвращает вендора по id вместе с продуктами. Требуется право university.read.",
)
def get_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> VendorDetail:
    return service.get_vendor_detail(db, vendor_id)


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorDetail,
    tags=["Vendors"],
    summary="Частично обновить вендора",
    description="Частично обновляет название и контакты вендора. Требуется право catalog.manage.",
)
def patch_vendor(
    vendor_id: uuid.UUID,
    data: VendorUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> VendorDetail:
    return service.patch_vendor(db, vendor_id, name=data.name, contacts=data.contacts)


@router.delete(
    "/vendors/{vendor_id}",
    response_model=None,
    status_code=204,
    tags=["Vendors"],
    summary="Удалить вендора",
    description="Безвозвратно удаляет вендора; при наличии продуктов — ошибка (RESTRICT). Требуется право catalog.manage.",
)
def delete_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    service.delete_vendor(db, vendor_id)


# ---------------------------------------------------- contracts & licenses
#
# University-scoped business records (P1-06-01). ``vendor`` is resolved via
# the product: Contract has no vendor_id column by design. Both lists apply
# the caller's university scope, so a manager never sees foreign rows.


@router.post(
    "/contracts",
    response_model=ContractDetail,
    status_code=201,
    tags=["Contracts"],
    summary="Создать договор",
    description="Создаёт договор, привязанный к вузу и продукту. Требуется право catalog.manage.",
)
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> ContractDetail:
    ensure_university_visible(data.university_id, user)
    return service.create_contract(db, data)


@router.get(
    "/contracts",
    response_model=PaginatedResponse[ContractRead],
    tags=["Contracts"],
    summary="Список договоров",
    description="Возвращает страницу договоров с поиском по номеру, фильтрами по вузу, продукту и статусу, пагинацией и сортировкой. Требуется право university.read.",
)
def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on contract number"),
    university_id: uuid.UUID | None = Query(default=None, description="Only contracts of this university"),
    product_id: uuid.UUID | None = Query(default=None, description="Only contracts for this product"),
    status: Literal["draft", "signed", "active", "expired", "terminated"] | None = Query(
        default=None, description="Derived status (never stored): draft/signed/active/expired/terminated"
    ),
    sort_by: ContractSortBy = Query(default="contract_number"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[ContractRead]:
    items, total = service.list_contract_page(
        db, page=page, page_size=page_size, search=_norm(search),
        university_id=university_id, product_id=product_id, status=status,
        sort_by=sort_by, sort_order=sort_order, user=user,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/contracts/{contract_id}",
    response_model=ContractDetail,
    tags=["Contracts"],
    summary="Получить договор по id",
    description="Возвращает договор по id вместе с лицензиями. Требуется право university.read.",
)
def get_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> ContractDetail:
    detail = service.get_contract_detail(db, contract_id)
    ensure_university_visible(detail.university_id, user)
    return detail


@router.patch(
    "/contracts/{contract_id}",
    response_model=ContractDetail,
    tags=["Contracts"],
    summary="Обновить договор",
    description="Обновляет договор, включая смену вуза с проверкой видимости. Требуется право catalog.manage.",
)
def patch_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> ContractDetail:
    detail = service.get_contract_detail(db, contract_id)
    ensure_university_visible(detail.university_id, user)
    if data.university_id is not None:
        ensure_university_visible(data.university_id, user)
    return service.patch_contract(db, contract_id, data)


@router.post(
    "/contracts/{contract_id}/file",
    response_model=ContractDetail,
    tags=["Contracts"],
    summary="Загрузить файл договора",
    description="Загружает файл договора (скан или копия) в хранилище. Требуется право catalog.manage.",
)
def upload_contract_file(
    contract_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> ContractDetail:
    contract = contract_or_404(db, contract_id)
    ensure_university_visible(contract.university_id, user)
    attach_contract_file(db, storage, contract, file)
    return service.get_contract_detail(db, contract_id)


@router.get(
    "/contracts/{contract_id}/file",
    tags=["Contracts"],
    summary="Скачать файл договора",
    description="Скачивает файл договора потоком; 404 если файла нет. Требуется право university.read.",
)
def download_contract_file(
    contract_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(READ),
) -> StreamingResponse:
    contract = contract_or_404(db, contract_id)
    ensure_university_visible(contract.university_id, user)
    if not contract.file_path or not storage.exists(contract.file_path):
        raise HTTPException(status_code=404, detail="Contract file not found")

    def stream():
        with storage.open_stream(contract.file_path) as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    from urllib.parse import quote
    name = contract.file_name or "contract"
    return StreamingResponse(stream(), media_type=contract.file_mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.delete(
    "/contracts/{contract_id}/file",
    response_model=None,
    status_code=204,
    tags=["Contracts"],
    summary="Удалить файл договора",
    description="Удаляет файл договора из хранилища, сам договор сохраняется. Требуется право catalog.manage.",
)
def delete_contract_file(
    contract_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    contract = contract_or_404(db, contract_id)
    ensure_university_visible(contract.university_id, user)
    detach_contract_file(db, storage, contract)


@router.delete(
    "/contracts/{contract_id}",
    response_model=None,
    status_code=204,
    tags=["Contracts"],
    summary="Удалить договор",
    description="Безвозвратно удаляет договор вместе с файлом; при наличии лицензий — 409. Требуется право catalog.manage.",
)
def delete_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    detail = service.get_contract_detail(db, contract_id)
    ensure_university_visible(detail.university_id, user)
    key = contract_or_404(db, contract_id).file_path
    service.delete_contract(db, contract_id)
    if key:
        try:
            storage.delete(key)
        except Exception:
            pass


@router.post(
    "/licenses",
    response_model=LicenseRead,
    status_code=201,
    tags=["Licenses"],
    summary="Создать лицензию",
    description="Создаёт лицензию, привязанную к вузу, продукту и договору. Требуется право catalog.manage.",
)
def create_license(
    data: LicenseCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> LicenseRead:
    ensure_university_visible(data.university_id, user)
    return service.create_license(db, data)


@router.get(
    "/licenses",
    response_model=PaginatedResponse[LicenseRead],
    tags=["Licenses"],
    summary="Список лицензий",
    description="Возвращает страницу лицензий с поиском по номеру, фильтрами по вузу, продукту и статусу, пагинацией и сортировкой. Требуется право university.read.",
)
def list_licenses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on license number"),
    university_id: uuid.UUID | None = Query(default=None, description="Only licenses of this university"),
    product_id: uuid.UUID | None = Query(default=None, description="Only licenses for this product"),
    status: Literal["active", "expires_soon", "expired"] | None = Query(
        default=None, description="Derived status (never stored): active/expires_soon/expired"
    ),
    sort_by: LicenseSortBy = Query(default="license_number"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[LicenseRead]:
    items, total = service.list_license_page(
        db, page=page, page_size=page_size, search=_norm(search),
        university_id=university_id, product_id=product_id, status=status,
        sort_by=sort_by, sort_order=sort_order, user=user,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/licenses/{license_id}",
    response_model=LicenseRead,
    tags=["Licenses"],
    summary="Получить лицензию по id",
    description="Возвращает лицензию по id. Требуется право university.read.",
)
def get_license(
    license_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> LicenseRead:
    detail = service.get_license_detail(db, license_id)
    ensure_university_visible(detail.university_id, user)
    return detail


@router.patch(
    "/licenses/{license_id}",
    response_model=LicenseRead,
    tags=["Licenses"],
    summary="Обновить лицензию",
    description="Обновляет лицензию, включая смену вуза с проверкой видимости. Требуется право catalog.manage.",
)
def patch_license(
    license_id: uuid.UUID,
    data: LicenseUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> LicenseRead:
    detail = service.get_license_detail(db, license_id)
    ensure_university_visible(detail.university_id, user)
    if data.university_id is not None:
        ensure_university_visible(data.university_id, user)
    return service.patch_license(db, license_id, data)


@router.delete(
    "/licenses/{license_id}",
    response_model=None,
    status_code=204,
    tags=["Licenses"],
    summary="Удалить лицензию",
    description="Безвозвратно удаляет лицензию. Требуется право catalog.manage.",
)
def delete_license(
    license_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    detail = service.get_license_detail(db, license_id)
    ensure_university_visible(detail.university_id, user)
    service.delete_license(db, license_id)


# ----------------------------------------------------------- responsibles

@router.post(
    "/responsibles",
    response_model=ResponsibleDetail,
    status_code=201,
    tags=["Responsibles"],
    summary="Создать ответственного",
    description="Создаёт ответственного с ФИО, email, телефоном и ролью. Требуется право catalog.manage.",
)
def create_responsible(
    data: ResponsibleCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ResponsibleDetail:
    return service.create_responsible(
        db,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        keycloak_sub=data.keycloak_sub,
    )


@router.get(
    "/responsibles",
    response_model=PaginatedResponse[ResponsibleRead],
    tags=["Responsibles"],
    summary="Список ответственных",
    description="Возвращает страницу ответственных с поиском по имени и email, фильтрами по роли и вузу, пагинацией и сортировкой. Требуется право university.read.",
)
def list_responsibles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name/email"),
    role: str | None = Query(default=None, description="Exact role filter"),
    university_id: uuid.UUID | None = Query(
        default=None, description="Only responsibles linked to this university"
    ),
    sort_by: ResponsibleSortBy = Query(default="full_name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[ResponsibleRead]:
    items, total = service.list_responsible_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        role=role,
        university_id=university_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/responsibles/{responsible_id}",
    response_model=ResponsibleDetail,
    tags=["Responsibles"],
    summary="Получить ответственного по id",
    description="Возвращает ответственного по id вместе с вузами. Требуется право university.read.",
)
def get_responsible(
    responsible_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(READ),
) -> ResponsibleDetail:
    return service.get_responsible_detail(db, responsible_id)


@router.patch(
    "/responsibles/{responsible_id}",
    response_model=ResponsibleDetail,
    tags=["Responsibles"],
    summary="Частично обновить ответственного",
    description="Частично обновляет данные ответственного. Требуется право catalog.manage.",
)
def patch_responsible(
    responsible_id: uuid.UUID,
    data: ResponsibleUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> ResponsibleDetail:
    fields = data.model_fields_set
    return service.patch_responsible(
        db,
        responsible_id,
        full_name=data.full_name if "full_name" in fields else None,
        email=data.email if "email" in fields else None,
        phone=data.phone if "phone" in fields else None,
        role=data.role if "role" in fields else None,
        keycloak_sub=data.keycloak_sub if "keycloak_sub" in fields else None,
        update_full_name="full_name" in fields,
        update_email="email" in fields,
        update_phone="phone" in fields,
        update_role="role" in fields,
        update_keycloak_sub="keycloak_sub" in fields,
    )


@router.delete(
    "/responsibles/{responsible_id}",
    response_model=None,
    status_code=204,
    tags=["Responsibles"],
    summary="Удалить ответственного",
    description="Безвозвратно удаляет ответственного; связи с вузами каскадируются, вузы сохраняются. Требуется право catalog.manage.",
)
def delete_responsible(
    responsible_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(CATALOG_WRITE),
) -> None:
    service.delete_responsible(db, responsible_id)

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
}


@router.get(
    "/catalog/overview",
    tags=["Catalog"],
    summary="Загруженные в БД данные (просмотр)",
    description=(
        "Возвращает строки каталога (вуз, вендор, ПО, договор, лицензия, "
        "ответственные) и справочник ИТ-направлений. Только чтение. Требуется право catalog.read."
    ),
    responses=ERROR_RESPONSES,
)
def catalog_overview(
    page: int = Query(1, ge=1, description="Страница, с 1"),
    page_size: int = Query(100, ge=1, le=500, description="Строк лицензий на странице"),
    limit: int | None = Query(
        None, ge=1, le=500,
        description="Deprecated: use page_size. Overrides page_size when set.",
    ),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("catalog.read")),
):
    size = limit if limit is not None else page_size
    return service.get_catalog_overview(db, user, page=page, size=size)


@router.get("/contracts/{contract_id}/file/preview", summary="Предпросмотр файла договора")
def preview_contract_file(
    contract_id: uuid.UUID, offset: int = Query(default=0, ge=0, le=9900),
    db: Session = Depends(get_audit_db), storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(READ),
):
    from app.modules.workflow_attachments.preview import preview_response
    contract = contract_or_404(db, contract_id)
    ensure_university_visible(contract.university_id, user)
    if not contract.file_path:
        raise HTTPException(404, "Contract file not found")
    return preview_response(storage, contract.file_path, contract.file_name or "contract", offset)

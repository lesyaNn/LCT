"""P1-03 catalog HTTP API (mounted under /api/v1).

Thin routes: query params -> RBAC -> service -> DTO. No SQL and no business
logic here. RBAC reuses the frozen permission names: ``university.read``
for GET, ``university.edit`` for mutations (there are no separate
create/update/delete permissions in the frozen model — curator and admin
can write, manager/user can only read). Includes the read-only
``/catalog/overview`` import viewer.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.catalog import service
from app.modules.catalog.schemas import (
    DirectionDetail,
    DirectionRead,
    ProductDetail,
    ProductRead,
    ProgramDetail,
    ProgramRead,
    ResponsibleAssign,
    ResponsibleCreate,
    ResponsibleDetail,
    ResponsibleRead,
    ResponsibleUpdate,
    UniversityDetail,
    UniversityRead,
    UniversityResponsibleRead,
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
from app.models.catalog import ITDirection, ITProgram, License, University
from app.models.interactions import UniversityProgram
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.university import UniversityCreate, UniversityUpdate

router = APIRouter()

READ = require_permission("university.read")
WRITE = require_permission("university.edit")


UniversitySortBy = Literal["name", "city", "created_at"]
DirectionSortBy = Literal["code", "name", "created_at"]
ProgramSortBy = Literal["name", "created_at"]
ProductSortBy = Literal["name", "version", "created_at"]
VendorSortBy = Literal["name", "created_at"]
ResponsibleSortBy = Literal["full_name", "email", "created_at"]
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
    summary="Create university",
)
def create_university(
    data: UniversityCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> UniversityDetail:
    return service.create_university(db, name=data.name, city=data.city)


@router.get(
    "/universities",
    response_model=PaginatedResponse[UniversityRead],
    tags=["Universities"],
    summary="List universities (paginated, search, filters, sorting)",
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
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[UniversityRead]:
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
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/universities/{university_id}",
    response_model=UniversityDetail,
    tags=["Universities"],
    summary="Get university by id (with responsibles)",
)
def get_university(
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> UniversityDetail:
    return service.get_university_detail(db, university_id)


@router.patch(
    "/universities/{university_id}",
    response_model=UniversityDetail,
    tags=["Universities"],
    summary="Partially update university",
)
def patch_university(
    university_id: uuid.UUID,
    data: UniversityUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> UniversityDetail:
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
    summary="Hard-delete university (RESTRICT when referenced)",
)
def delete_university(
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_university(db, university_id)


@router.post(
    "/universities/{university_id}/responsibles/{responsible_id}",
    response_model=UniversityResponsibleRead,
    tags=["Universities"],
    summary="Assign a responsible to a university (idempotent)",
)
def assign_responsible(
    university_id: uuid.UUID,
    responsible_id: uuid.UUID,
    data: ResponsibleAssign | None = Body(default=None),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
):
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
    summary="Unassign a responsible from a university",
)
def unassign_responsible(
    university_id: uuid.UUID,
    responsible_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.unassign_responsible(db, university_id, responsible_id)


# ------------------------------------------------------------- directions


@router.post(
    "/directions",
    response_model=DirectionDetail,
    status_code=201,
    tags=["Directions"],
    summary="Create direction",
)
def create_direction(
    data: DirectionCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> DirectionDetail:
    return service.create_direction(db, code=data.code, name=data.name)


@router.get(
    "/directions",
    response_model=PaginatedResponse[DirectionRead],
    tags=["Directions"],
    summary="List directions (paginated, search, sorting)",
)
def list_directions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on code/name"),
    sort_by: DirectionSortBy = Query(default="code"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_db),
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
    summary="Get direction by id (with programs)",
)
def get_direction(
    direction_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> DirectionDetail:
    return service.get_direction_detail(db, direction_id)


@router.patch(
    "/directions/{direction_id}",
    response_model=DirectionDetail,
    tags=["Directions"],
    summary="Partially update direction",
)
def patch_direction(
    direction_id: uuid.UUID,
    data: DirectionUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> DirectionDetail:
    return service.patch_direction(db, direction_id, code=data.code, name=data.name)


@router.delete(
    "/directions/{direction_id}",
    response_model=None,
    status_code=204,
    tags=["Directions"],
    summary="Hard-delete direction (RESTRICT when programs exist)",
)
def delete_direction(
    direction_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_direction(db, direction_id)


# --------------------------------------------------------------- programs


@router.post(
    "/programs",
    response_model=ProgramDetail,
    status_code=201,
    tags=["Programs"],
    summary="Create program (global, belongs to a direction)",
)
def create_program(
    data: ProgramCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> ProgramDetail:
    return service.create_program(
        db, direction_id=data.direction_id, name=data.name, description=data.description
    )


@router.get(
    "/programs",
    response_model=PaginatedResponse[ProgramRead],
    tags=["Programs"],
    summary="List programs (paginated, search, direction filter, sorting)",
)
def list_programs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    direction_id: uuid.UUID | None = Query(default=None, description="Filter by direction"),
    sort_by: ProgramSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_db),
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
    summary="Get program by id (with direction)",
)
def get_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> ProgramDetail:
    return service.get_program_detail(db, program_id)


@router.patch(
    "/programs/{program_id}",
    response_model=ProgramDetail,
    tags=["Programs"],
    summary="Partially update program",
)
def patch_program(
    program_id: uuid.UUID,
    data: ProgramUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
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
    summary="Hard-delete program (RESTRICT when linked)",
)
def delete_program(
    program_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_program(db, program_id)


# --------------------------------------------------------------- products


@router.post(
    "/products",
    response_model=ProductDetail,
    status_code=201,
    tags=["Products"],
    summary="Create product",
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> ProductDetail:
    return service.create_product(
        db, vendor_id=data.vendor_id, name=data.name, version=data.version
    )


@router.get(
    "/products",
    response_model=PaginatedResponse[ProductRead],
    tags=["Products"],
    summary="List products (paginated, search, vendor filter, sorting)",
)
def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    vendor_id: uuid.UUID | None = Query(default=None, description="Filter by vendor"),
    sort_by: ProductSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> PaginatedResponse[ProductRead]:
    items, total = service.list_product_page(
        db,
        page=page,
        page_size=page_size,
        search=_norm(search),
        vendor_id=vendor_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    tags=["Products"],
    summary="Get product by id (with vendor)",
)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> ProductDetail:
    return service.get_product_detail(db, product_id)


@router.patch(
    "/products/{product_id}",
    response_model=ProductDetail,
    tags=["Products"],
    summary="Partially update product",
)
def patch_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> ProductDetail:
    return service.patch_product(
        db, product_id, vendor_id=data.vendor_id, name=data.name, version=data.version
    )


@router.delete(
    "/products/{product_id}",
    response_model=None,
    status_code=204,
    tags=["Products"],
    summary="Hard-delete product (RESTRICT when licensed/linked)",
)
def delete_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_product(db, product_id)


# ---------------------------------------------------------------- vendors


@router.post(
    "/vendors",
    response_model=VendorDetail,
    status_code=201,
    tags=["Vendors"],
    summary="Create vendor",
)
def create_vendor(
    data: VendorCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> VendorDetail:
    return service.create_vendor(db, name=data.name)


@router.get(
    "/vendors",
    response_model=PaginatedResponse[VendorRead],
    tags=["Vendors"],
    summary="List vendors (paginated, search, sorting)",
)
def list_vendors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Case-insensitive match on name"),
    sort_by: VendorSortBy = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    db: Session = Depends(get_db),
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
    summary="Get vendor by id (with products)",
)
def get_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> VendorDetail:
    return service.get_vendor_detail(db, vendor_id)


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorDetail,
    tags=["Vendors"],
    summary="Partially update vendor",
)
def patch_vendor(
    vendor_id: uuid.UUID,
    data: VendorUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> VendorDetail:
    return service.patch_vendor(db, vendor_id, name=data.name)


@router.delete(
    "/vendors/{vendor_id}",
    response_model=None,
    status_code=204,
    tags=["Vendors"],
    summary="Hard-delete vendor (RESTRICT when products exist)",
)
def delete_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
) -> None:
    service.delete_vendor(db, vendor_id)


# ----------------------------------------------------------- responsibles


@router.post(
    "/responsibles",
    response_model=ResponsibleDetail,
    status_code=201,
    tags=["Responsibles"],
    summary="Create responsible",
)
def create_responsible(
    data: ResponsibleCreate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
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
    summary="List responsibles (paginated, search, filters, sorting)",
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
    db: Session = Depends(get_db),
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
    summary="Get responsible by id (with universities)",
)
def get_responsible(
    responsible_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(READ),
) -> ResponsibleDetail:
    return service.get_responsible_detail(db, responsible_id)


@router.patch(
    "/responsibles/{responsible_id}",
    response_model=ResponsibleDetail,
    tags=["Responsibles"],
    summary="Partially update responsible",
)
def patch_responsible(
    responsible_id: uuid.UUID,
    data: ResponsibleUpdate,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
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
    summary="Hard-delete responsible (links cascade, university survives)",
)
def delete_responsible(
    responsible_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(WRITE),
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
        "ответственные) и справочник ИТ-направлений. Только чтение."
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
    db: Session = Depends(get_db),
    _u: CurrentUser = Depends(require_permission("catalog.read")),
):
    size = limit if limit is not None else page_size
    offset = (page - 1) * size
    total_universities = db.execute(
        select(func.count()).select_from(University)
    ).scalar() or 0
    total_licenses = db.execute(
        select(func.count()).select_from(License)
    ).scalar() or 0

    licenses = (
        db.execute(
            select(License)
            .options(
                selectinload(License.university).selectinload(
                    University.university_responsibles
                ),
                selectinload(License.university).selectinload(
                    University.university_programs
                ).selectinload(UniversityProgram.program).selectinload(
                    ITProgram.direction
                ),
                selectinload(License.product),
                selectinload(License.contract),
                selectinload(License.program).selectinload(ITProgram.direction),
                selectinload(License.direction),
            )
            .order_by(License.expires_at)
            .limit(size)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    rows = []
    for lic in licenses:
        uni = lic.university
        managers: list[str] = []
        contacts: list[str] = []
        # Направление именно этой строки (одна строка = один договор/лицензия).
        # Fallback — направления вуза (старые строки без direction_id).
        if lic.direction is not None:
            directions = [lic.direction.name]
        elif lic.program is not None and lic.program.direction is not None:
            directions = [lic.program.direction.name]
        else:
            directions = []
            if uni is not None:
                for upl in uni.university_programs:
                    if upl.program is not None and upl.program.direction is not None:
                        name = upl.program.direction.name
                        if name not in directions:
                            directions.append(name)
        if uni is not None:
            for link in uni.university_responsibles:
                if link.responsible is None:
                    continue
                if link.role_in_university == "our_manager":
                    managers.append(link.responsible.full_name)
                else:
                    contacts.append(link.responsible.full_name)
        product = lic.product
        rows.append({
            "university": uni.name if uni else None,
            "vendor": product.vendor.name if product and product.vendor else None,
            "product": product.name if product else None,
            "contract_number": lic.contract.contract_number if lic.contract else lic.license_number,
            "signed_at": lic.signed_at.isoformat() if lic.signed_at else None,
            "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
            "transfer_status": lic.transfer_status_raw,
            "manager": "; ".join(managers) or None,
            "responsibles": contacts,
            "comment": lic.comment,
            "direction": "; ".join(directions) or None,
        })

    directions = (
        db.execute(select(ITDirection).order_by(ITDirection.code)).scalars().all()
    )
    programs = db.execute(select(ITProgram)).scalars().all()
    prog_by_dir: dict[str, int] = {}
    for p in programs:
        key = str(p.direction_id)
        prog_by_dir[key] = prog_by_dir.get(key, 0) + 1

    return {
        "total_universities": total_universities,
        "total_licenses": total_licenses,
        "page": page,
        "page_size": size,
        "rows": rows,
        "directions": [
            {
                "code": d.code,
                "name": d.name,
                "programs": prog_by_dir.get(str(d.id), 0),
            }
            for d in directions
        ],
    }

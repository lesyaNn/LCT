"""P1-03 catalog HTTP API (mounted under /api/v1).

Thin routes: query params -> RBAC -> service -> DTO. No SQL and no business
logic here. RBAC reuses the frozen permission names: ``university.read``
for GET, ``university.edit`` for mutations (there are no separate
create/update/delete permissions in the frozen model — manager and admin
can write, manager/user can only read). Includes the read-only
``/catalog/overview`` import viewer.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission, require_role
from app.core.policies import ensure_university_visible
from app.core.security import CurrentUser
from app.modules.analytics.filters import UnifiedFilter, get_unified_filter
from app.modules.audit.service import get_audit_db
from app.modules.catalog import passport_relations, service
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
LEGACY_CATALOG_WRITE = require_role("admin", "manager")


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
    summary="Create university",
)
def create_university(
    data: UniversityCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(require_role("admin", "manager")),
) -> UniversityDetail:
    return service.create_university(db, name=data.name, city=data.city)


@router.get(
    "/universities",
    response_model=PaginatedResponse[UniversityListItem],
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
    external_source: Literal["website"] | None = Query(default=None),
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
    summary="Partially update university",
)
def patch_university(
    university_id: uuid.UUID,
    data: UniversityUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
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
    summary="Hard-delete university (409 while referenced, M4 policy)",
)
def delete_university(
    university_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_role("admin", "manager")),
) -> None:
    ensure_university_visible(university_id, user)
    service.delete_university(db, university_id)


@router.post(
    "/universities/{university_id}/programs",
    response_model=UniversityProgramRead,
    status_code=201,
    tags=["Universities"],
    summary="Attach an existing catalog program to a university",
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
    summary="Attach an existing catalog product to a university",
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
    summary="Atomically change the primary responsible",
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
    summary="Assign a responsible to a university (idempotent)",
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
    summary="Unassign a responsible from a university",
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
    summary="Create direction",
)
def create_direction(
    data: DirectionCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Get direction by id (with programs)",
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
    summary="Partially update direction",
)
def patch_direction(
    direction_id: uuid.UUID,
    data: DirectionUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Get program by id (with direction)",
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
    summary="Partially update program",
)
def patch_program(
    program_id: uuid.UUID,
    data: ProgramUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
) -> ProductDetail:
    return service.create_product(
        db, vendor_id=data.vendor_id, program_id=data.program_id,
        name=data.name, version=data.version,
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
    summary="Get product by id (with vendor)",
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
    summary="Partially update product",
)
def patch_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Hard-delete product (RESTRICT when licensed/linked)",
)
def delete_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Get vendor by id (with products)",
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
    summary="Partially update vendor",
)
def patch_vendor(
    vendor_id: uuid.UUID,
    data: VendorUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Create contract",
)
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
) -> ContractDetail:
    ensure_university_visible(data.university_id, user)
    return service.create_contract(db, data)


@router.get(
    "/contracts",
    response_model=PaginatedResponse[ContractRead],
    tags=["Contracts"],
    summary="List contracts (paginated, search, filters, sorting)",
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
    summary="Get contract by id (with its licenses)",
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
    summary="Update contract",
)
def patch_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
) -> ContractDetail:
    detail = service.get_contract_detail(db, contract_id)
    ensure_university_visible(detail.university_id, user)
    if data.university_id is not None:
        ensure_university_visible(data.university_id, user)
    return service.patch_contract(db, contract_id, data)


@router.delete(
    "/contracts/{contract_id}",
    response_model=None,
    status_code=204,
    tags=["Contracts"],
    summary="Hard-delete contract (409 while licenses reference it)",
)
def delete_contract(
    contract_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
) -> None:
    detail = service.get_contract_detail(db, contract_id)
    ensure_university_visible(detail.university_id, user)
    service.delete_contract(db, contract_id)


@router.post(
    "/licenses",
    response_model=LicenseRead,
    status_code=201,
    tags=["Licenses"],
    summary="Create license",
)
def create_license(
    data: LicenseCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
) -> LicenseRead:
    ensure_university_visible(data.university_id, user)
    return service.create_license(db, data)


@router.get(
    "/licenses",
    response_model=PaginatedResponse[LicenseRead],
    tags=["Licenses"],
    summary="List licenses (paginated, search, filters, sorting)",
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
    summary="Get license by id",
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
    summary="Update license",
)
def patch_license(
    license_id: uuid.UUID,
    data: LicenseUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Hard-delete license",
)
def delete_license(
    license_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Create responsible",
)
def create_responsible(
    data: ResponsibleCreate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    summary="Get responsible by id (with universities)",
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
    summary="Partially update responsible",
)
def patch_responsible(
    responsible_id: uuid.UUID,
    data: ResponsibleUpdate,
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    _user: CurrentUser = Depends(LEGACY_CATALOG_WRITE),
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
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(require_permission("catalog.read")),
):
    size = limit if limit is not None else page_size
    return service.get_catalog_overview(db, user, page=page, size=size)

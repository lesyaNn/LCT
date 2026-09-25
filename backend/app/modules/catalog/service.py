"""P1-03 service layer: repository rows -> DTOs, NotFound mapping.

No SQL here (only repository calls). UNIQUE/FK violations surface as
``IntegrityError`` and are mapped centrally to HTTP 409 — never caught
per-endpoint, never leaked to the client.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.modules.catalog import repository as repo
from app.modules.catalog.schemas import (
    DirectionDetail,
    DirectionRead,
    ProductDetail,
    ProductRead,
    ProgramDetail,
    ProgramRead,
    ResponsibleAssign,
    ResponsibleDetail,
    ResponsibleRead,
    ResponsibleShort,
    UniversityDetail,
    UniversityRead,
    UniversityResponsibleRead,
    VendorDetail,
    VendorRead,
)
from app.schemas.catalog import (
    DirectionShort,
    ProductShort,
    ProgramShort,
    VendorShort,
)

# -------------------------------------------------------------- universities


HEALTH_STATUSES = ("green", "yellow", "red")


def list_university_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    city: str | None,
    responsible_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
    unified_filter=None,
    unified_today=None,
    user=None,
    health_status: str | None = None,
) -> tuple[list[UniversityRead], int]:
    """List universities from the materialized health projection.

    Health filtering, sorting, count and pagination stay in SQL so query
    work is independent of the number of universities. Missing projections
    remain ``NULL`` until the deployment backfill/refresh job runs.
    """
    if health_status is not None and health_status not in HEALTH_STATUSES:
        raise ValueError(f"Unknown health_status: {health_status!r}")
    if health_status is None and sort_by != "health_score":
        rows, total = repo.list_universities(
            db,
            page=page,
            page_size=page_size,
            search=search,
            city=city,
            responsible_id=responsible_id,
            sort_by=sort_by,
            sort_order=sort_order,
            unified_filter=unified_filter,
            unified_today=unified_today,
            user=user,
        )
        return [UniversityRead.model_validate(r) for r in rows], total
    rows, total = repo.list_universities_health(
        db, page=page, page_size=page_size, search=search, city=city,
        responsible_id=responsible_id, sort_order=sort_order,
        health_status=health_status, unified_filter=unified_filter,
        unified_today=unified_today, user=user,
    )
    items = []
    for u, score, status in rows:
        dto = UniversityRead.model_validate(u)
        dto.health_score = score
        dto.health_status = status
        items.append(dto)
    return items, total


def get_university_detail(
    db: Session, university_id: uuid.UUID, user=None,
) -> UniversityDetail:
    """H5: with ``user`` the row is loaded scope-first (one SELECT, 404 for
    both missing and out-of-scope); without it the legacy unscoped load."""
    obj = (
        repo.get_university_scoped(db, university_id, user)
        if user is not None
        else repo.get_university(db, university_id)
    )
    if obj is None:
        raise NotFound("University not found")
    detail = UniversityDetail.model_validate(obj)
    detail.responsibles = [
        ResponsibleShort.model_validate(resp)
        for resp, _link in repo.university_responsibles(db, university_id)
    ]
    return detail


def create_university(db: Session, *, name: str, city: str | None) -> UniversityDetail:
    obj = repo.add_and_flush(db, University(name=name, city=city))
    return UniversityDetail.model_validate(obj)


def patch_university(
    db: Session,
    university_id: uuid.UUID,
    *,
    name: str | None,
    city: str | None,
    update_name: bool,
    update_city: bool,
) -> UniversityDetail:
    obj = repo.get_university(db, university_id)
    if obj is None:
        raise NotFound("University not found")
    if update_name:
        obj.name = name
    if update_city:
        obj.city = city
    repo.save(db, obj)
    return get_university_detail(db, university_id)


def delete_university(db: Session, university_id: uuid.UUID) -> None:
    """Hard-delete with the unified M4 policy: refuse (409) while ANY
    business data references the university — catalog rows (DB RESTRICT
    backstop) AND history/links (DB CASCADE, must never be wiped silently).
    """
    if repo.get_university(db, university_id) is None:
        raise NotFound("University not found")
    blockers = repo.university_delete_blockers(db, university_id)
    if blockers:
        raise Conflict(
            f"University has {', '.join(blockers)}; deletion blocked"
        )
    repo.delete_by_id(db, University, university_id)


# -------------------------------------------------------------- directions


def list_direction_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[DirectionRead], int]:
    rows, total = repo.list_directions(
        db,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [DirectionRead.model_validate(r) for r in rows], total


def get_direction_detail(db: Session, direction_id: uuid.UUID) -> DirectionDetail:
    obj = repo.get_direction(db, direction_id)
    if obj is None:
        raise NotFound("Direction not found")
    detail = DirectionDetail.model_validate(obj)
    detail.programs = [
        ProgramShort(id=prog.id, name=prog.name, direction_name=direction_name)
        for prog, direction_name in repo.direction_programs(db, direction_id)
    ]
    return detail


def create_direction(db: Session, *, code: str, name: str) -> DirectionDetail:
    obj = repo.add_and_flush(db, ITDirection(code=code, name=name))
    return get_direction_detail(db, obj.id)


def patch_direction(
    db: Session, direction_id: uuid.UUID, *, code: str | None, name: str | None
) -> DirectionDetail:
    obj = repo.get_direction(db, direction_id)
    if obj is None:
        raise NotFound("Direction not found")
    if code is not None:
        obj.code = code
    if name is not None:
        obj.name = name
    repo.save(db, obj)
    return get_direction_detail(db, direction_id)


def delete_direction(db: Session, direction_id: uuid.UUID) -> None:
    if repo.get_direction(db, direction_id) is None:
        raise NotFound("Direction not found")
    repo.delete_by_id(db, ITDirection, direction_id)


# ---------------------------------------------------------------- programs


def _program_read(prog: ITProgram, direction_name: str | None) -> ProgramRead:
    item = ProgramRead.model_validate(prog)
    item.direction_name = direction_name
    return item


def list_program_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    direction_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[ProgramRead], int]:
    rows, total = repo.list_programs(
        db,
        page=page,
        page_size=page_size,
        search=search,
        direction_id=direction_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [_program_read(prog, direction_name) for prog, direction_name in rows], total


def get_program_detail(db: Session, program_id: uuid.UUID) -> ProgramDetail:
    row = repo.get_program(db, program_id)
    if row is None:
        raise NotFound("Program not found")
    prog, direction = row
    detail = ProgramDetail.model_validate(prog)
    detail.direction_name = direction.name if direction is not None else None
    detail.direction = DirectionShort.model_validate(direction) if direction is not None else None
    return detail


def create_program(
    db: Session, *, direction_id: uuid.UUID, name: str, description: str
) -> ProgramDetail:
    obj = repo.add_and_flush(
        db, ITProgram(direction_id=direction_id, name=name, description=description)
    )
    return get_program_detail(db, obj.id)


def patch_program(
    db: Session,
    program_id: uuid.UUID,
    *,
    direction_id: uuid.UUID | None,
    name: str | None,
    description: str | None,
) -> ProgramDetail:
    row = repo.get_program(db, program_id)
    if row is None:
        raise NotFound("Program not found")
    prog = row[0]
    if direction_id is not None:
        prog.direction_id = direction_id
    if name is not None:
        prog.name = name
    if description is not None:
        prog.description = description
    repo.save(db, prog)
    return get_program_detail(db, program_id)


def delete_program(db: Session, program_id: uuid.UUID) -> None:
    if repo.get_program(db, program_id) is None:
        raise NotFound("Program not found")
    repo.delete_by_id(db, ITProgram, program_id)


# ---------------------------------------------------------------- products


def _product_read(prod: ITProduct, vendor_name: str | None) -> ProductRead:
    item = ProductRead.model_validate(prod)
    item.vendor_name = vendor_name
    return item


def list_product_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    vendor_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[ProductRead], int]:
    rows, total = repo.list_products(
        db,
        page=page,
        page_size=page_size,
        search=search,
        vendor_id=vendor_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [_product_read(prod, vendor_name) for prod, vendor_name in rows], total


def get_product_detail(db: Session, product_id: uuid.UUID) -> ProductDetail:
    row = repo.get_product(db, product_id)
    if row is None:
        raise NotFound("Product not found")
    prod, vendor = row
    detail = ProductDetail.model_validate(prod)
    detail.vendor_name = vendor.name if vendor is not None else None
    detail.vendor = VendorShort.model_validate(vendor) if vendor is not None else None
    return detail


def create_product(db: Session, *, vendor_id: uuid.UUID, name: str, version: str) -> ProductDetail:
    obj = repo.add_and_flush(db, ITProduct(vendor_id=vendor_id, name=name, version=version))
    return get_product_detail(db, obj.id)


def patch_product(
    db: Session,
    product_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID | None,
    name: str | None,
    version: str | None,
) -> ProductDetail:
    row = repo.get_product(db, product_id)
    if row is None:
        raise NotFound("Product not found")
    prod = row[0]
    if vendor_id is not None:
        prod.vendor_id = vendor_id
    if name is not None:
        prod.name = name
    if version is not None:
        prod.version = version
    repo.save(db, prod)
    return get_product_detail(db, product_id)


def delete_product(db: Session, product_id: uuid.UUID) -> None:
    if repo.get_product(db, product_id) is None:
        raise NotFound("Product not found")
    repo.delete_by_id(db, ITProduct, product_id)


# ----------------------------------------------------------------- vendors


def list_vendor_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[VendorRead], int]:
    rows, total = repo.list_vendors(
        db,
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [VendorRead.model_validate(r) for r in rows], total


def get_vendor_detail(db: Session, vendor_id: uuid.UUID) -> VendorDetail:
    obj = repo.get_vendor(db, vendor_id)
    if obj is None:
        raise NotFound("Vendor not found")
    detail = VendorDetail.model_validate(obj)
    detail.products = [
        ProductShort(id=p.id, name=p.name, version=p.version, vendor_name=obj.name)
        for p in repo.vendor_products(db, vendor_id)
    ]
    return detail


def create_vendor(db: Session, *, name: str) -> VendorDetail:
    obj = repo.add_and_flush(db, Vendor(name=name))
    return get_vendor_detail(db, obj.id)


def patch_vendor(db: Session, vendor_id: uuid.UUID, *, name: str | None) -> VendorDetail:
    obj = repo.get_vendor(db, vendor_id)
    if obj is None:
        raise NotFound("Vendor not found")
    if name is not None:
        obj.name = name
    repo.save(db, obj)
    return get_vendor_detail(db, vendor_id)


def delete_vendor(db: Session, vendor_id: uuid.UUID) -> None:
    if repo.get_vendor(db, vendor_id) is None:
        raise NotFound("Vendor not found")
    repo.delete_by_id(db, Vendor, vendor_id)


# ------------------------------------------------------------- responsibles


def list_responsible_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    role: str | None,
    university_id: uuid.UUID | None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[ResponsibleRead], int]:
    rows, total = repo.list_responsibles(
        db,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        university_id=university_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [ResponsibleRead.model_validate(r) for r in rows], total


def get_responsible_detail(db: Session, responsible_id: uuid.UUID) -> ResponsibleDetail:
    obj = repo.get_responsible(db, responsible_id)
    if obj is None:
        raise NotFound("Responsible not found")
    detail = ResponsibleDetail.model_validate(obj)
    detail.universities = [
        UniversityRead.model_validate(u) for u in repo.responsible_universities(db, responsible_id)
    ]
    return detail


def create_responsible(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone: str | None,
    role: str,
    keycloak_sub: str | None,
) -> ResponsibleDetail:
    obj = repo.add_and_flush(
        db,
        Responsible(
            full_name=full_name, email=email, phone=phone, role=role, keycloak_sub=keycloak_sub
        ),
    )
    return get_responsible_detail(db, obj.id)


def patch_responsible(
    db: Session,
    responsible_id: uuid.UUID,
    *,
    full_name: str | None,
    email: str | None,
    phone: str | None,
    role: str | None,
    keycloak_sub: str | None,
    update_full_name: bool,
    update_email: bool,
    update_phone: bool,
    update_role: bool,
    update_keycloak_sub: bool,
) -> ResponsibleDetail:
    obj = repo.get_responsible(db, responsible_id)
    if obj is None:
        raise NotFound("Responsible not found")
    if update_full_name:
        obj.full_name = full_name
    if update_email:
        obj.email = email
    if update_phone:
        obj.phone = phone
    if update_role:
        obj.role = role
    if update_keycloak_sub:
        obj.keycloak_sub = keycloak_sub
    repo.save(db, obj)
    return get_responsible_detail(db, responsible_id)


def delete_responsible(db: Session, responsible_id: uuid.UUID) -> None:
    if repo.get_responsible(db, responsible_id) is None:
        raise NotFound("Responsible not found")
    repo.delete_by_id(db, Responsible, responsible_id)


# ------------------------------------------------- university <-> responsible


def assign_responsible(
    db: Session, university_id: uuid.UUID, responsible_id: uuid.UUID, data: ResponsibleAssign | None
) -> tuple[UniversityResponsibleRead, bool]:
    """Link a responsible to a university. Returns (link, created)."""
    if repo.get_university(db, university_id) is None:
        raise NotFound("University not found")
    if repo.get_responsible(db, responsible_id) is None:
        raise NotFound("Responsible not found")
    existing = repo.get_link(db, university_id, responsible_id)
    if existing is not None:
        return UniversityResponsibleRead.model_validate(existing), False
    link = repo.add_and_flush(
        db,
        UniversityResponsible(
            university_id=university_id,
            responsible_id=responsible_id,
            role_in_university=data.role_in_university if data else None,
            is_primary=data.is_primary if data else False,
        ),
    )
    return UniversityResponsibleRead.model_validate(link), True


def unassign_responsible(db: Session, university_id: uuid.UUID, responsible_id: uuid.UUID) -> None:
    link = repo.get_link(db, university_id, responsible_id)
    if link is None:
        if repo.get_university(db, university_id) is None:
            raise NotFound("University not found")
        if repo.get_responsible(db, responsible_id) is None:
            raise NotFound("Responsible not found")
        raise NotFound("UniversityResponsible link not found")
    repo.delete_link(db, link)


# ---------------------------------------------------------- catalog overview


def get_catalog_overview(db: Session, user, *, page: int, size: int) -> dict:
    """Assemble the read-only /catalog/overview payload (H4).

    SQL lives in the repository (scoped counts/page + GROUP BY counters);
    this function only maps rows to plain dicts. Returns the exact shape the
    router previously built inline.
    """
    total_universities, total_licenses = repo.count_overview(db, user)
    licenses = repo.page_overview_licenses(
        db, user, limit=size, offset=(page - 1) * size
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

    directions, prog_by_dir = repo.direction_program_counts(db, user)
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

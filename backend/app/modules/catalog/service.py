"""P1-03 service layer: repository rows -> DTOs, NotFound mapping.

No SQL here (only repository calls). UNIQUE/FK violations surface as
``IntegrityError`` and are mapped centrally to HTTP 409 — never caught
per-endpoint, never leaked to the client.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.modules.catalog import repository as repo
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
    VendorContactRead,
)
from app.schemas.catalog import (
    DirectionShort,
    ProductShort,
    ProgramShort,
    VendorShort,
)
from app.schemas.licenses import LicenseShort

# -------------------------------------------------------------- universities


def list_university_page(
    db,
    *,
    page: int,
    page_size: int,
    search: str | None,
    city: str | None,
    responsible_id=None,
    sort_by: str = "name",
    sort_order: str = "asc",
    unified_filter=None,
    unified_today=None,
    user=None,
    health_status: str | None = None,
    external_source: str | None = None,
):
    """List universities (plain, no health score)."""
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
        external_source=external_source,
    )
    return [UniversityRead.model_validate(r) for r in rows], total


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


def _product_read(
    prod: ITProduct, vendor_name: str | None, program_name: str | None = None
) -> ProductRead:
    item = ProductRead.model_validate(prod)
    item.vendor_name = vendor_name
    item.program_name = program_name
    return item


def list_product_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    search: str | None,
    vendor_id: uuid.UUID | None,
    direction_id: uuid.UUID | None = None,
    sort_by: str,
    sort_order: str,
) -> tuple[list[ProductRead], int]:
    rows, total = repo.list_products(
        db,
        page=page,
        page_size=page_size,
        search=search,
        vendor_id=vendor_id,
        direction_id=direction_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return [_product_read(prod, vendor_name, program_name) for prod, vendor_name, program_name in rows], total


def get_product_detail(db: Session, product_id: uuid.UUID) -> ProductDetail:
    row = repo.get_product(db, product_id)
    if row is None:
        raise NotFound("Product not found")
    prod, vendor, program = row
    detail = ProductDetail.model_validate(prod)
    detail.vendor_name = vendor.name if vendor is not None else None
    detail.vendor = VendorShort.model_validate(vendor) if vendor is not None else None
    detail.program_name = program.name if program is not None else None
    detail.contacts = [VendorContactRead.model_validate(contact) for contact in repo.product_contacts(db, product_id)]
    return detail


def _require_program(db: Session, program_id: uuid.UUID) -> None:
    if repo.get_program(db, program_id) is None:
        raise NotFound("Program not found")


def create_product(
    db: Session, *, vendor_id: uuid.UUID, name: str, version: str,
    program_id: uuid.UUID | None = None,
) -> ProductDetail:
    if program_id is not None:
        _require_program(db, program_id)
    obj = repo.add_and_flush(
        db, ITProduct(vendor_id=vendor_id, program_id=program_id, name=name, version=version)
    )
    return get_product_detail(db, obj.id)


#: Sentinel for patch omit (field absent from the body = leave unchanged;
#: explicit null clears the product->program link).
UNSET: Any = object()


def patch_product(
    db: Session,
    product_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID | None,
    name: str | None,
    version: str | None,
    program_id: uuid.UUID | None | Any = UNSET,
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
    if program_id is not UNSET:
        if program_id is not None:
            _require_program(db, program_id)
        prod.program_id = program_id
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
    detail.contacts = [VendorContactRead.model_validate(contact) for contact in repo.vendor_contacts(db, vendor_id)]
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
    # Universities for the whole page in ONE extra query, so a list page costs
    # two queries instead of one per row.
    grouped = repo.responsible_universities_by_id(db, [r.id for r in rows])
    items = []
    for r in rows:
        item = ResponsibleRead.model_validate(r)
        item.universities = [UniversityRead.model_validate(u) for u in grouped.get(r.id, [])]
        items.append(item)
    return items, total


def get_responsible_detail(db: Session, responsible_id: uuid.UUID) -> ResponsibleDetail:
    obj = repo.get_responsible(db, responsible_id)
    if obj is None:
        raise NotFound("Responsible not found")
    detail = ResponsibleDetail.model_validate(obj)
    detail.universities = [
        UniversityRead.model_validate(u) for u in repo.responsible_universities(db, responsible_id)
    ]
    return detail


# ----------------------------------------------------- contracts & licenses


def _agreement_labels(db: Session) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, uuid.UUID]]:
    """(id -> label for every referenced entity, product -> vendor) in one pass."""
    return repo._agreement_names(db, None), repo._vendor_id_by_product(db)


def _fill_contract(db: Session, dto: ContractRead, obj: Contract) -> ContractRead:
    names, product_vendor = _agreement_labels(db)
    dto.university_name = names.get(obj.university_id, "")
    dto.product_name = names.get(obj.product_id) if obj.product_id else None
    dto.vendor_name = names.get(product_vendor[obj.product_id]) if obj.product_id else None
    dto.license_count = repo.contract_license_counts(db, [obj.id]).get(obj.id, 0)
    return dto


def _fill_license(db: Session, dto: LicenseRead, obj: License) -> LicenseRead:
    names, product_vendor = _agreement_labels(db)
    dto.university_name = names.get(obj.university_id, "")
    dto.product_name = names.get(obj.product_id, "")
    dto.vendor_name = names.get(product_vendor.get(obj.product_id)) if obj.product_id else None
    dto.contract_number = names.get(obj.contract_id) if obj.contract_id else None
    dto.program_name = names.get(obj.program_id) if obj.program_id else None
    dto.direction_name = names.get(obj.direction_id) if obj.direction_id else None
    return dto


def list_contract_page(
    db: Session, *, page: int, page_size: int, search: str | None,
    university_id: uuid.UUID | None, product_id: uuid.UUID | None,
    status: str | None, sort_by: str, sort_order: str, user=None,
) -> tuple[list[ContractRead], int]:
    rows, total = repo.list_contracts(
        db, page=page, page_size=page_size, search=search, university_id=university_id,
        product_id=product_id, status=status, sort_by=sort_by, sort_order=sort_order, user=user,
    )
    names, product_vendor = _agreement_labels(db)
    counts = repo.contract_license_counts(db, [r.id for r in rows])
    items = []
    for r in rows:
        dto = ContractRead.model_validate(r)
        dto.university_name = names.get(r.university_id, "")
        dto.product_name = names.get(r.product_id) if r.product_id else None
        dto.vendor_name = names.get(product_vendor[r.product_id]) if r.product_id else None
        dto.license_count = counts.get(r.id, 0)
        items.append(dto)
    return items, total


def get_contract_detail(db: Session, contract_id: uuid.UUID) -> ContractDetail:
    obj = repo.get_contract(db, contract_id)
    if obj is None:
        raise NotFound("Contract not found")
    detail = ContractDetail.model_validate(obj)
    _fill_contract(db, detail, obj)
    detail.licenses = [
        LicenseShort.model_validate(lic) for lic in repo.contract_licenses(db, contract_id)
    ]
    return detail


def create_contract(db: Session, data: ContractCreate) -> ContractDetail:
    obj = repo.add_and_flush(db, Contract(**data.model_dump()))
    return get_contract_detail(db, obj.id)


def patch_contract(db: Session, contract_id: uuid.UUID, data: ContractUpdate) -> ContractDetail:
    obj = repo.get_contract(db, contract_id)
    if obj is None:
        raise NotFound("Contract not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    repo.save(db, obj)
    return get_contract_detail(db, obj.id)


def delete_contract(db: Session, contract_id: uuid.UUID) -> None:
    """Hard delete, but only while no license points at the contract.

    The FK is declared ON DELETE SET NULL, so a plain delete would silently
    orphan every license of that contract. Refuse with 409 instead and let the
    user re-point the licenses first.
    """
    if repo.get_contract(db, contract_id) is None:
        raise NotFound("Contract not found")
    if repo.contract_license_counts(db, [contract_id]).get(contract_id, 0) > 0:
        raise Conflict("Contract still has licenses")
    repo.delete_by_id(db, Contract, contract_id)


def list_license_page(
    db: Session, *, page: int, page_size: int, search: str | None,
    university_id: uuid.UUID | None, product_id: uuid.UUID | None,
    status: str | None, sort_by: str, sort_order: str, user=None,
) -> tuple[list[LicenseRead], int]:
    rows, total = repo.list_licenses(
        db, page=page, page_size=page_size, search=search, university_id=university_id,
        product_id=product_id, status=status, sort_by=sort_by, sort_order=sort_order, user=user,
    )
    names, product_vendor = _agreement_labels(db)
    items = []
    for r in rows:
        dto = LicenseRead.model_validate(r)
        dto.university_name = names.get(r.university_id, "")
        dto.product_name = names.get(r.product_id, "")
        dto.vendor_name = names.get(product_vendor.get(r.product_id)) if r.product_id else None
        dto.contract_number = names.get(r.contract_id) if r.contract_id else None
        dto.program_name = names.get(r.program_id) if r.program_id else None
        dto.direction_name = names.get(r.direction_id) if r.direction_id else None
        items.append(dto)
    return items, total


def get_license_detail(db: Session, license_id: uuid.UUID) -> LicenseRead:
    obj = repo.get_license(db, license_id)
    if obj is None:
        raise NotFound("License not found")
    return _fill_license(db, LicenseRead.model_validate(obj), obj)


def create_license(db: Session, data: LicenseCreate) -> LicenseRead:
    obj = repo.add_and_flush(db, License(**data.model_dump()))
    return get_license_detail(db, obj.id)


def patch_license(db: Session, license_id: uuid.UUID, data: LicenseUpdate) -> LicenseRead:
    obj = repo.get_license(db, license_id)
    if obj is None:
        raise NotFound("License not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    repo.save(db, obj)
    return get_license_detail(db, obj.id)


def delete_license(db: Session, license_id: uuid.UUID) -> None:
    """Licenses reference only products (RESTRICT is on the product side), so
    a license can be removed once no contract still expects it."""
    if repo.get_license(db, license_id) is None:
        raise NotFound("License not found")
    repo.delete_by_id(db, License, license_id)


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

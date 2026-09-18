"""Read-only catalog overview (what was loaded into the DB via import).

Simple viewer for the demo: universities + licenses/contracts with
vendor/product, managers/contacts and IT-directions. No write operations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.catalog import (
    ITDirection,
    ITProgram,
    License,
    University,
)
from app.models.interactions import UniversityProgram
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/catalog", tags=["Catalog"])

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет Bearer токена"},
}


@router.get(
    "/overview",
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

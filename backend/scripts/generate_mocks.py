"""Generate P3 mock JSON from the demo seed.

Usage (from ``backend/``)::

    python scripts/generate_mocks.py [--out ../docs/mocks]

Builds the ``UniversityPassport`` DTO from a freshly seeded database and
dumps it as JSON, so P3 can mock ``GET /universities/{id}/passport``
without a backend. The file is re-validated against the Pydantic schema on
every run (round-trip parse) — the script fails loudly on schema drift.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.seed import seed_demo
from app.models.catalog import Contract, ITProduct, ITProgram, License, University
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    UniversityProduct,
    UniversityProgram,
)
from app.schemas import (
    ContractShort,
    DocumentShort,
    DocumentStatus,
    InteractionShort,
    LicenseShort,
    MeetingShort,
    ProductShort,
    ProgramShort,
    ResponsibleDetail,
    ResponsibleShort,
    StageShort,
    UniversityDetail,
    UniversityPassport,
    WorkflowSummary,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(REPO_ROOT) == "backend":
    REPO_ROOT = os.path.dirname(REPO_ROOT)

UNIVERSITY_NAME = "МГУ им. М.В. Ломоносова"
WORKFLOW_STAGE = {"code": "control", "name": "Контроль исполнения"}


def _program_short(prog: ITProgram) -> ProgramShort:
    return ProgramShort(
        id=prog.id,
        name=prog.name,
        direction_name=prog.direction.name if prog.direction else None,
    )


def build_university_passport(session: Session, uni_name: str) -> UniversityPassport:
    uni = session.execute(select(University).filter_by(name=uni_name)).scalar_one()

    links = sorted(uni.university_responsibles, key=lambda link: (not link.is_primary))
    primary = links[0].responsible if links else None
    responsible = (
        ResponsibleDetail(
            id=primary.id,
            full_name=primary.full_name,
            email=primary.email,
            phone=primary.phone,
            role=primary.role,
        )
        if primary is not None
        else None
    )
    university = UniversityDetail(
        id=uni.id,
        name=uni.name,
        city=uni.city,
        responsible=responsible,
        created_at=uni.created_at,
        updated_at=uni.updated_at,
    )

    uni_progs = session.execute(
        select(UniversityProgram, ITProgram)
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .filter(UniversityProgram.university_id == uni.id)
    ).all()
    programs = [_program_short(prog) for _, prog in uni_progs]

    uni_products = session.execute(
        select(UniversityProduct, ITProduct)
        .join(ITProduct, ITProduct.id == UniversityProduct.product_id)
        .filter(UniversityProduct.university_id == uni.id)
    ).all()
    products = [
        ProductShort(
            id=prod.id,
            name=prod.name,
            version=prod.version,
            vendor_name=prod.vendor.name if prod.vendor else None,
        )
        for _, prod in uni_products
    ]

    licenses = []
    for lic in session.execute(
        select(License).filter_by(university_id=uni.id)
    ).scalars().all():
        prod = session.get(ITProduct, lic.product_id)
        licenses.append(
            LicenseShort(
                id=lic.id,
                license_number=lic.license_number,
                product_name=prod.name if prod else None,
                expires_at=lic.expires_at,
            )
        )

    contracts = [
        ContractShort.model_validate(c)
        for c in session.execute(
            select(Contract).filter_by(university_id=uni.id)
        ).scalars().all()
    ]

    documents = [
        DocumentShort(
            id=doc.id,
            document_type=doc.document_type,
            title=doc.title,
            status=DocumentStatus(doc.status_raw),
            expires_at=doc.expires_at,
        )
        for doc in session.execute(
            select(Document).filter_by(university_id=uni.id)
        ).scalars().all()
    ]

    meetings = [
        MeetingShort.model_validate(m)
        for m in session.execute(
            select(Meeting)
            .filter_by(university_id=uni.id)
            .order_by(Meeting.meeting_at.desc())
        ).scalars().all()
    ]

    responsibles = [
        ResponsibleShort(id=link.responsible.id, full_name=link.responsible.full_name)
        for link in links
    ]

    notes = session.execute(
        select(InteractionNote)
        .filter_by(university_id=uni.id)
        .order_by(InteractionNote.created_at.desc())
        .limit(5)
    ).scalars().all()
    last_interactions = [InteractionShort.model_validate(n) for n in notes]

    return UniversityPassport(
        university=university,
        programs=programs,
        products=products,
        licenses=licenses,
        contracts=contracts,
        documents=documents,
        meetings=meetings,
        responsibles=responsibles,
        workflow_summary=WorkflowSummary(
            current_stage=StageShort(**WORKFLOW_STAGE),
            stages_total=14,
            stages_completed=14,
        ),
        last_interactions=last_interactions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate P3 mock JSON.")
    parser.add_argument(
        "--out",
        default=os.path.join(REPO_ROOT, "docs", "mocks"),
        help="output directory for mock JSON files",
    )
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL must point to an already migrated PostgreSQL database"
        )
    engine = create_engine(database_url)
    if engine.dialect.name != "postgresql":
        raise SystemExit("generate_mocks requires an already migrated PostgreSQL database")
    with Session(engine) as session:
        seed_demo(session)
        university_passport = build_university_passport(session, UNIVERSITY_NAME)

    payload = university_passport.model_dump(mode="json")
    UniversityPassport.model_validate(payload)
    path = os.path.join(args.out, "university-passport.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("WROTE", path)
    print(
        "university: " + UNIVERSITY_NAME
        + " (" + str(len(university_passport.programs)) + " programs, "
        + str(len(university_passport.licenses)) + " licenses)"
    )


if __name__ == "__main__":
    main()

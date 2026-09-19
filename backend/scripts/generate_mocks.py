"""Generate P3 mock JSON from the demo seed (P1-12-01).

Usage (from ``backend/``)::

    python scripts/generate_mocks.py [--out ../docs/mocks]

Builds ``UniversityPassport`` / ``TeacherPassport`` DTOs from a freshly
seeded database and dumps them as JSON, so P3 can mock
``GET /universities/{id}/passport`` and ``GET /teachers/{id}/passport``
without a backend. Files are re-validated against the Pydantic schemas on
every run (round-trip parse) — the script fails loudly on schema drift.

Illustrative placeholders (P2-owned, filled with demo values until the
real services land):
* ``health_score`` / ``health_status`` — target values from P1-09-01.
* ``workflow_summary`` — stage pointer; workflow instances are P2-owned.
* ``trainings`` — empty; no training entity exists in P1.
"""

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.seed import seed_demo
from app.models.catalog import Contract, ITProduct, ITProgram, License, University
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import Teacher
from app.schemas import (
    CertificateShort,
    ContractShort,
    DocumentShort,
    DocumentStatus,
    InteractionShort,
    LicenseShort,
    MeetingShort,
    ProductShort,
    ProgramShort,
    QualificationShort,
    ResponsibleDetail,
    ResponsibleShort,
    StageShort,
    StudentsSummary,
    TeacherDetail,
    TeacherPassport,
    TeacherReadiness,
    TeacherShort,
    UniversityDetail,
    UniversityPassport,
    WorkflowSummary,
)
from app.services.teacher_readiness import compute_teacher_readiness

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# When run from backend/, repo root is one level up.
if os.path.basename(REPO_ROOT) == "backend":
    REPO_ROOT = os.path.dirname(REPO_ROOT)

UNIVERSITY_NAME = "МГУ им. М.В. Ломоносова"
TEACHER_UNIVERSITY = "СПбГУ"
TEACHER_READINESS = "attention"

# Illustrative P2-owned values (see module docstring).
HEALTH_SCORE = {UNIVERSITY_NAME: (92, "green")}
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
    score, status = HEALTH_SCORE.get(uni_name, (None, None))
    university = UniversityDetail(
        id=uni.id,
        name=uni.name,
        city=uni.city,
        responsible=responsible,
        health_score=score,
        health_status=status,
        created_at=uni.created_at,
        updated_at=uni.updated_at,
    )

    uni_progs = session.execute(
        select(UniversityProgram, ITProgram)
        .join(ITProgram, ITProgram.id == UniversityProgram.program_id)
        .filter(UniversityProgram.university_id == uni.id)
    ).all()
    programs = [_program_short(prog) for _, prog in uni_progs]

    teachers = []
    for teacher in sorted(uni.teachers, key=lambda t: t.full_name):
        result = compute_teacher_readiness(
            certificates=teacher.certificates,
            qualifications=teacher.qualifications,
        )
        teachers.append(
            TeacherShort(
                id=teacher.id,
                full_name=teacher.full_name,
                position=teacher.position,
                readiness=result.readiness,
            )
        )

    student_statuses = Counter(
        s.status
        for s in session.execute(
            select(Student).filter_by(university_id=uni.id)
        ).scalars().all()
    )
    students_summary = StudentsSummary(
        total=sum(student_statuses.values()),
        active=student_statuses.get("active", 0),
        graduated=student_statuses.get("graduated", 0),
        expelled=student_statuses.get("expelled", 0),
        academic_leave=student_statuses.get("academic_leave", 0),
    )

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
        teachers=teachers,
        students_summary=students_summary,
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


def _certificate_short(cert) -> CertificateShort:
    return CertificateShort(
        id=cert.id,
        name=cert.certificate_name,
        issued_by=cert.issued_by,
        issued_at=cert.issued_at,
        expires_at=cert.expires_at,
        is_mandatory=cert.is_mandatory,
        program_name=cert.program.name if cert.program else None,
    )


def build_teacher_passport(
    session: Session, uni_name: str, readiness: str = "attention"
) -> TeacherPassport:
    uni = session.execute(select(University).filter_by(name=uni_name)).scalar_one()
    teachers = session.execute(
        select(Teacher).filter_by(university_id=uni.id)
    ).scalars().all()
    scored = []
    for teacher in teachers:
        result = compute_teacher_readiness(
            certificates=teacher.certificates,
            qualifications=teacher.qualifications,
        )
        scored.append((teacher, result))
    teacher, result = next(
        (t, r) for t, r in scored if r.readiness.value == readiness
    )

    allowed = []
    for link in teacher.teacher_programs:
        prog = session.get(ITProgram, link.program_id)
        if prog is not None:
            allowed.append(_program_short(prog))

    detail = TeacherDetail(
        id=teacher.id,
        university_id=teacher.university_id,
        university_name=uni.name,
        full_name=teacher.full_name,
        email=teacher.email,
        phone=teacher.phone,
        position=teacher.position,
        readiness=result.readiness,
        next_qualification_date=result.next_qualification_date,
        qualifications=[
            QualificationShort(
                id=q.id,
                name=q.qualification_name,
                obtained_at=q.obtained_at,
                expires_at=q.expires_at,
            )
            for q in teacher.qualifications
        ],
        certificates=[_certificate_short(c) for c in teacher.certificates],
        allowed_programs=allowed,
        created_at=teacher.created_at,
        updated_at=teacher.updated_at,
    )
    return TeacherPassport(
        teacher=detail,
        trainings=[],
        certificates=detail.certificates,
        qualifications=detail.qualifications,
        allowed_programs=allowed,
        next_qualification_date=result.next_qualification_date,
        readiness=result.readiness,
        readiness_reasons=result.reasons,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate P3 mock JSON (P1-12-01).")
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
        teacher_passport = build_teacher_passport(
            session, TEACHER_UNIVERSITY, TEACHER_READINESS
        )

    outputs = {
        "university-passport.json": UniversityPassport,
        "teacher-passport.json": TeacherPassport,
    }
    passports = {
        "university-passport.json": university_passport,
        "teacher-passport.json": teacher_passport,
    }
    for filename, model in outputs.items():
        passport = passports[filename]
        payload = passport.model_dump(mode="json")
        # Round-trip validation: fails loudly on schema drift.
        model.model_validate(payload)
        path = os.path.join(args.out, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        assert TeacherReadiness  # keep import used for future variants
        print(f"WROTE {path}")

    print(
        f"university: {UNIVERSITY_NAME} "
        f"({len(university_passport.programs)} programs, "
        f"{len(university_passport.teachers)} teachers, "
        f"{len(university_passport.licenses)} licenses)"
    )
    print(
        f"teacher: {teacher_passport.teacher.full_name} "
        f"readiness={teacher_passport.readiness.value}"
    )


if __name__ == "__main__":
    main()

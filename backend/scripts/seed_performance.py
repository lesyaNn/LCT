"""P1-10-02 performance dataset seeder (deterministic, idempotent).

Adds a ``PERF-`` prefixed synthetic load ON TOP of the demo seed so the
PostgreSQL planner sees realistic table sizes. Never runs at startup;
explicit invocation only::

    DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk \\
        python scripts/seed_performance.py

Determinism: ``random.Random(42)`` drives every choice. Idempotency: every
entity uses a natural unique key (``PERF-...`` numbers, e-mails,
``external_id``s, license/contract numbers, note contents); re-runs skip
existing rows and only fill the gap to the target counts.

Scale targets (additive, totals include the 10-university demo seed):

* universities:          +50  (~60 total)
* it_programs:           +100 (~106 total, global catalog)
* university_programs:   ~6/univ (~325 total)
* teachers:              10/univ (500 new, ~534 total)
* teacher_programs:      3/teacher (1500 new, ~1550 total)
* students:              100/univ (5000 new, ~5750 total)
* licenses:              10/univ (500 new, ~520 total)
* contracts:             4/univ (200 new, ~230 total)
* documents:             60/univ (3000 new, ~3040 total)
* meetings:              20/univ (1000 new, ~1035 total)
* interaction_notes:     40/univ (2000 new, ~2020 total)
* audit_events:          60/univ (3000 new, ~3000 total)

Timestamps are spread over the past ~730 days so ``ORDER BY x DESC LIMIT n``
branches exercise the composite per-university indexes instead of sorting a
handful of same-second rows.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.seed import seed_demo  # noqa: E402
from app.models.catalog import (  # noqa: E402
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
)
from app.models.interactions import (  # noqa: E402
    Document,
    InteractionNote,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import (  # noqa: E402
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)

RNG = random.Random(42)

N_PERF_UNIVS = 50
N_EXTRA_PROGRAMS = 100
TEACHERS_PER_UNIV = 10
LINKS_PER_TEACHER = 3
STUDENTS_PER_UNIV = 100
LICENSES_PER_UNIV = 10
CONTRACTS_PER_UNIV = 4
DOCS_PER_UNIV = 60
MEETINGS_PER_UNIV = 20
NOTES_PER_UNIV = 40
AUDIT_PER_UNIV = 60

SYSTEM_SUB = "perf-seed"

STATUSES = ["active"] * 80 + ["graduated"] * 10 + ["expelled"] * 5 + ["academic_leave"] * 5


def _get_or_create(session: Session, model, defaults: dict, **key):
    obj = session.execute(select(model).filter_by(**key)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**{**key, **defaults})
    session.add(obj)
    session.flush()
    return obj, True


def _past_ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        days=days_ago, seconds=RNG.randint(0, 86399)
    )


def seed_performance(session: Session) -> dict:
    seed_demo(session)  # demo baseline first (idempotent)
    today = date.today()

    directions = session.execute(select(ITDirection)).scalars().all()
    products = session.execute(select(ITProduct)).scalars().all()
    assert directions and products, "demo seed must provide directions/products"

    # --- extra catalog programs (deterministic names) ---
    for i in range(N_EXTRA_PROGRAMS):
        name = f"PERF Программа {i:03d}"
        session.execute(select(ITProgram).filter_by(name=name)).scalar_one_or_none()
        _get_or_create(
            session,
            ITProgram,
            {
                "direction_id": directions[i % len(directions)].id,
                "description": "performance catalog entry",
            },
            name=name,
        )
    all_programs = session.execute(select(ITProgram)).scalars().all()

    # --- late import (legacy audit model path) to avoid circulars ---
    from app.modules.audit.models import AuditEvent

    for u_idx in range(N_PERF_UNIVS):
        uname = f"PERF Университет {u_idx:02d}"
        city = f"PERF City {u_idx % 7}"
        uni, _ = _get_or_create(session, University, {"city": city}, name=uname)

        # responsibles: 2 contacts + 1 shared manager (mirrors demo seed)
        for r in range(2):
            email = f"perf-contact{r + 1}.u{u_idx:02d}@example.local"
            resp, _ = _get_or_create(
                session,
                Responsible,
                {
                    "full_name": f"PERF Контакт {u_idx:02d}-{r}",
                    "phone": None,
                    "role": "university_contact",
                },
                email=email,
            )
            _get_or_create(
                session,
                UniversityResponsible,
                {"role_in_university": "university_contact", "is_primary": r == 0},
                university_id=uni.id,
                responsible_id=resp.id,
            )
        mgr, _ = _get_or_create(
            session,
            Responsible,
            {"full_name": f"PERF Менеджер {u_idx % 3}", "phone": None, "role": "our_manager"},
            email=f"perf-manager{(u_idx % 3)}@example.local",
        )
        _get_or_create(
            session,
            UniversityResponsible,
            {"role_in_university": "our_manager", "is_primary": False},
            university_id=uni.id,
            responsible_id=mgr.id,
        )

        # university_programs: 6 deterministic links
        uni_prog_ids: list = []
        for k in range(6):
            prog = all_programs[(u_idx * 6 + k) % len(all_programs)]
            up, _ = _get_or_create(
                session,
                UniversityProgram,
                {"status": "active" if k < 4 else "planned"},
                university_id=uni.id,
                program_id=prog.id,
            )
            uni_prog_ids.append(prog.id)

        # teachers + certs + quals + links
        for t_idx in range(TEACHERS_PER_UNIV):
            email = f"perf.u{u_idx:02d}.t{t_idx:02d}@example.local"
            teacher, created = _get_or_create(
                session,
                Teacher,
                {
                    "university_id": uni.id,
                    "full_name": f"PERF Преподаватель {u_idx:02d}-{t_idx:02d}",
                    "position": "доцент",
                },
                email=email,
            )
            if not created:
                continue
            for lk in range(LINKS_PER_TEACHER):
                prog_id = uni_prog_ids[(t_idx + lk) % len(uni_prog_ids)]
                session.add(
                    TeacherProgram(
                        teacher_id=teacher.id,
                        program_id=prog_id,
                        can_teach=True,
                        assigned_at=today - timedelta(days=300),
                    )
                )
            # 1 qualification (mixed expiry) + 2 mandatory certs + 1 optional
            delta_q = RNG.choice([400, 200, 15, -30])
            session.add(
                TeacherQualification(
                    teacher_id=teacher.id,
                    qualification_name="ПК PERF",
                    obtained_at=today - timedelta(days=400),
                    expires_at=today + timedelta(days=delta_q),
                )
            )
            for c_idx in range(2):
                delta_c = RNG.choice([500, 300, 20, 10, -10, -60])
                session.add(
                    TeacherCertificate(
                        teacher_id=teacher.id,
                        certificate_name=f"PERF Mandatory {c_idx}",
                        issued_by="PERF Center",
                        issued_at=today - timedelta(days=900),
                        expires_at=today + timedelta(days=delta_c),
                        is_mandatory=True,
                    )
                )
            session.add(
                TeacherCertificate(
                    teacher_id=teacher.id,
                    certificate_name="PERF Optional",
                    issued_by="PERF Center",
                    issued_at=today - timedelta(days=200),
                    expires_at=today + timedelta(days=600),
                    is_mandatory=False,
                )
            )
            session.flush()

        # students: 100/univ bulk
        existing = set(
            session.execute(
                select(Student.external_id).filter_by(university_id=uni.id)
            ).scalars().all()
        )
        to_add = []
        for s_idx in range(STUDENTS_PER_UNIV):
            ext = f"perf-u{u_idx:02d}-{s_idx:03d}"
            if ext in existing:
                continue
            st = RNG.choice(STATUSES)
            prog_id = uni_prog_ids[s_idx % len(uni_prog_ids)]
            to_add.append(
                Student(
                    external_id=ext,
                    university_id=uni.id,
                    program_id=prog_id,
                    full_name=f"PERF Студент {u_idx:02d}-{s_idx:03d}",
                    group_name=f"Группа {(s_idx % 4) + 1}",
                    status=st,
                    started_at=today - timedelta(days=400),
                    finished_at=(
                        today - timedelta(days=30) if st == "graduated" else None
                    ),
                )
            )
        session.add_all(to_add)
        session.flush()

        # contracts + licenses + university_products
        for c_idx in range(CONTRACTS_PER_UNIV):
            con_no = f"PERF-DOG-{u_idx:02d}-{c_idx:02d}"
            prod = products[(u_idx + c_idx) % len(products)] if c_idx < 2 else None
            _get_or_create(
                session,
                Contract,
                {
                    "university_id": uni.id,
                    "product_id": prod.id if prod else None,
                    "signed_at": today - timedelta(days=200),
                    "expires_at": today + timedelta(days=RNG.choice([400, 200, 25, -15])),
                    "status_raw": "signed",
                    "transfer_status_raw": "accepted",
                },
                contract_number=con_no,
            )
        for l_idx in range(LICENSES_PER_UNIV):
            lic_no = f"PERF-LIC-{u_idx:02d}-{l_idx:02d}"
            prod = products[(u_idx + l_idx) % len(products)]
            lic, lic_created = _get_or_create(
                session,
                License,
                {
                    "university_id": uni.id,
                    "product_id": prod.id,
                    "contract_id": None,
                    "signed_at": today - timedelta(days=180),
                    "expires_at": today + timedelta(days=RNG.choice([500, 250, 20, 5, -20])),
                    "transfer_status_raw": "accepted",
                },
                license_number=lic_no,
            )
            if lic_created and l_idx < 2:
                _get_or_create(
                    session,
                    UniversityProduct,
                    {"license_id": lic.id, "status": "active"},
                    university_id=uni.id,
                    product_id=prod.id,
                )

        # documents (spread created_at over 700 days)
        for d_idx in range(DOCS_PER_UNIV):
            title = f"PERF Документ {u_idx:02d}-{d_idx:03d}"
            if session.execute(select(Document).filter_by(title=title)).scalar_one_or_none():
                continue
            session.add(
                Document(
                    university_id=uni.id,
                    document_type=["contract", "license", "act", "protocol"][d_idx % 4],
                    title=title,
                    file_path=f"perf/u{u_idx:02d}/doc{d_idx:03d}.pdf",
                    file_name=f"doc{d_idx:03d}.pdf",
                    file_size=1024 * (50 + d_idx % 500),
                    mime_type="application/pdf",
                    signed_at=today - timedelta(days=120),
                    expires_at=today + timedelta(days=RNG.choice([300, 100, -20])),
                    status_raw="signed" if d_idx % 2 == 0 else "draft",
                    uploaded_by_keycloak_sub=SYSTEM_SUB,
                    created_at=_past_ts(RNG.randint(0, 700)),
                )
            )

        # meetings (spread meeting_at)
        for m_idx in range(MEETINGS_PER_UNIV):
            subject = f"PERF Встреча {u_idx:02d}-{m_idx:02d}"
            if session.execute(select(Meeting).filter_by(subject=subject)).scalar_one_or_none():
                continue
            session.add(
                Meeting(
                    university_id=uni.id,
                    meeting_type=["online", "offline", "phone", "email"][m_idx % 4],
                    subject=subject,
                    participants=[{"name": "PERF Участник", "role": "Менеджер"}],
                    outcome=f"PERF итог {m_idx}",
                    next_action=None,
                    next_action_due=None,
                    meeting_at=_past_ts(RNG.randint(0, 700)),
                    created_by_keycloak_sub=SYSTEM_SUB,
                )
            )

        # notes (spread created_at)
        for n_idx in range(NOTES_PER_UNIV):
            content = f"PERF Заметка {u_idx:02d}-{n_idx:03d}"
            if session.execute(
                select(InteractionNote).filter_by(
                    university_id=uni.id, content=content
                )
            ).scalar_one_or_none():
                continue
            session.add(
                InteractionNote(
                    university_id=uni.id,
                    author_keycloak_sub=SYSTEM_SUB,
                    content=content,
                    is_internal=True,
                    created_at=_past_ts(RNG.randint(0, 700)),
                )
            )

        # audit events (spread created_at)
        for a_idx in range(AUDIT_PER_UNIV):
            marker = f"perf-{u_idx:02d}-{a_idx:03d}"
            if session.execute(
                select(AuditEvent).filter_by(
                    entity_type="perf", entity_id=u_idx * 1000 + a_idx
                )
            ).scalar_one_or_none():
                continue
            session.add(
                AuditEvent(
                    user_id=1,
                    entity_type="perf",
                    entity_id=u_idx * 1000 + a_idx,
                    action="update",
                    before_data="{}",
                    after_data='{"marker": "%s"}' % marker,
                    ip_address="",
                    university_id=uni.id,
                    created_at=_past_ts(RNG.randint(0, 700)),
                )
            )
        session.flush()
    session.commit()

    stats: dict[str, int] = {}
    for model, label in [
        (University, "universities"),
        (ITProgram, "programs"),
        (UniversityProgram, "university_programs"),
        (Teacher, "teachers"),
        (TeacherProgram, "teacher_programs"),
        (Student, "students"),
        (License, "licenses"),
        (Contract, "contracts"),
        (Document, "documents"),
        (Meeting, "meetings"),
        (InteractionNote, "interaction_notes"),
    ]:
        stats[label] = session.execute(select(model.id)).scalars().all().__len__()
    from app.modules.audit.models import AuditEvent as _AE

    stats["audit_events"] = session.execute(select(_AE.id)).scalars().all().__len__()
    return stats


def main() -> None:
    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    with Session(engine) as session:
        stats = seed_performance(session)
    print("PERF SEED OK:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

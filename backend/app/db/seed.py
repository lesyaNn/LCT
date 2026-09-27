"""P1 demo seed (P1-09-01 / P1-09-02 / P1-09-03).

* ``python -m app.db.seed`` — canonical entry (works from ``backend/``).
* Idempotent: every entity is get-or-created by its natural unique key, so
  re-runs never duplicate data (verified by tests).
* Dates are relative to ``date.today()`` so expiry scenarios (expiring
  licenses, expired documents) stay valid
  whenever the seed runs.
* Creates the full chain: catalogs -> universities -> programs/products ->
  responsibles -> licenses/contracts ->
  meetings -> documents -> notes, with no dangling FKs.

Workflow instances (P1-09-02 progress table) are P2-owned tables and are
intentionally NOT seeded here. The P2-01-04 standard
14-stage workflow *template* IS seeded here via ``seed_workflow_templates``
(idempotent, runs after ``migrate``).
"""

import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
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
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    MeetingDocument,
    UniversityProduct,
    UniversityProgram,
)

from app.db.seed_workflow import seed_workflow_templates

SYSTEM_SUB = "system-seed"

# ---------------------------------------------------------------- catalogs

DIRECTIONS = [
    ("09.03.01", "Информатика и вычислительная техника"),
    ("09.03.02", "Информационные системы и технологии"),
    ("10.03.01", "Информационная безопасность"),
    ("01.03.02", "Прикладная математика и информатика"),
    ("11.03.02", "Инфокоммуникационные технологии и системы связи"),
]

PROGRAMS = [  # (name, direction_code, description)
    ("Искусственный интеллект", "09.03.01", "ML, нейросети и анализ данных"),
    ("Кибербезопасность", "10.03.01", "Защита информации и сетей"),
    ("Программная инженерия", "09.03.02", "Разработка и сопровождение ПО"),
    ("Анализ данных", "01.03.02", "Статистика, BI и большие данные"),
    ("Сетевые технологии", "11.03.02", "Телеком-инфраструктура и связь"),
    ("Прикладная информатика", "09.03.02", "Информатизация предприятий"),
]

VENDORS_PRODUCTS = [  # (vendor, [(product, version), ...])
    ("Ростелеком", [("РТК Платформа ВКС", "4.2"), ("РТК Облако", "2.7")]),
    ("РЕД СОФТ", [("РЕД ОС", "8.0")]),
    ("Астра", [("Astra Linux Special Edition", "1.8")]),
    ("Базальт СПО", [("Альт Образование", "10.2")]),
]

# ------------------------------------------------------------- universities
# (name, city, programs[2-3], license plan, doc plan)
UNIVERSITIES = [
    ("МГУ им. М.В. Ломоносова", "Москва"),
    ("СПбГУ", "Санкт-Петербург"),
    ("НИУ ВШЭ", "Москва"),
    ("МФТИ", "Долгопрудный"),
    ("ИТМО", "Санкт-Петербург"),
    ("УрФУ", "Екатеринбург"),
    ("Тюменский государственный университет", "Тюмень"),
    ("Дальневосточный федеральный университет", "Владивосток"),
    ("СибГУТИ", "Новосибирск"),
    ("КФУ", "Казань"),
]

# The teacher/readiness seed plan was removed together with the
# students/teachers/health-score entities (commit 26fa4a9).

# P1-09-02 license expiry plan: university -> [days_to_expiry, ...]
LICENSE_EXPIRY: dict[str, list[int]] = {
    "МГУ им. М.В. Ломоносова": [5, 400],
    "СПбГУ": [15, 25],
    "ИТМО": [3, 10, 28],
    "УрФУ": [90, 200],
    "МФТИ": [120, 300],
    "НИУ ВШЭ": [60, 150],
    "Тюменский государственный университет": [-30, -5],
    "Дальневосточный федеральный университет": [200],
    "СибГУТИ": [45, 180],
    "КФУ": [-10, 50],
}


# ---------------------------------------------------------------- helpers


def _get_or_create(session: Session, model, defaults: dict, **key):
    obj = session.execute(select(model).filter_by(**key)).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**{**key, **defaults})
    session.add(obj)
    session.flush()
    return obj, True


def seed_demo(session: Session, skip_universities: bool | None = None) -> dict:
    """Run the full idempotent demo seed. Returns entity counts.

    ``skip_universities=True`` (or ``SEED_SKIP_UNIVERSITIES=1``) seeds only
    the standalone catalogs (directions/programs/vendors/products) and skips
    everything bound to universities (universities themselves, responsibles,
    licenses/contracts, meetings, documents, notes) —
    e.g. to fill universities later via XLSX import.
    """
    if skip_universities is None:
        skip_universities = os.getenv("SEED_SKIP_UNIVERSITIES", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    today = date.today()
    stats: dict[str, int] = {}

    # --- directions / programs ---
    directions = {}
    for code, name in DIRECTIONS:
        d, _ = _get_or_create(session, ITDirection, {"name": name}, code=code)
        directions[code] = d
    programs = {}
    for name, code, desc in PROGRAMS:
        p, _ = _get_or_create(
            session,
            ITProgram,
            {"direction_id": directions[code].id, "description": desc},
            name=name,
        )
        programs[name] = p

    # --- vendors / products (program links are NOT seeded: binding is
    # specified at workflow creation or via the catalog UI, never invented) ---
    products = []
    for vendor_name, prods in VENDORS_PRODUCTS:
        v, _ = _get_or_create(session, Vendor, {}, name=vendor_name)
        for pname, version in prods:
            pr, _ = _get_or_create(
                session,
                ITProduct,
                {"vendor_id": v.id},
                vendor_id=v.id,
                name=pname,
                version=version,
            )
            products.append(pr)

    prog_names = list(programs.keys())

    if skip_universities:
        session.commit()
        return _collect_stats(session)

    # --- per-university data ---
    first_names = [
        "Александр",
        "Мария",
        "Дмитрий",
        "Елена",
        "Игорь",
        "Ольга",
        "Сергей",
        "Анна",
        "Павел",
        "Наталья",
    ]
    last_names = [
        "Иванов",
        "Петрова",
        "Сидоров",
        "Кузнецова",
        "Смирнов",
        "Попова",
        "Соколов",
        "Морозова",
        "Волков",
        "Новикова",
    ]

    for u_idx, (uname, city) in enumerate(UNIVERSITIES):
        uni, _ = _get_or_create(session, University, {"city": city}, name=uname)

        # responsibles: 2 university contacts + shared manager on even idx
        uni_resps = []
        for r in range(2):
            email = f"contact{r + 1}.u{u_idx}@example.local"
            resp, _ = _get_or_create(
                session,
                Responsible,
                {
                    "full_name": f"{last_names[(u_idx + r) % 10]} "
                              f"{first_names[(u_idx + r * 3) % 10]} "
                              f"{'А.' if r == 0 else 'Б.'}",
                 "phone": f"+7 (495) 000-00-{u_idx:02d}{r}",
                    "role": "university_contact",
                },
                email=email,
            )
            uni_resps.append(resp)
            _get_or_create(
                session,
                UniversityResponsible,
                {"role_in_university": "university_contact", "is_primary": r == 0},
                university_id=uni.id,
                responsible_id=resp.id,
            )
        mgr_email = f"manager{(u_idx % 3) + 1}@example.local"
        mgr, _ = _get_or_create(
            session,
            Responsible,
            {
                "full_name": f"Менеджеров Менеджер {(u_idx % 3) + 1}",
                "phone": None,
                "role": "our_manager",
            },
            email=mgr_email,
        )
        _get_or_create(
            session,
            UniversityResponsible,
            {"role_in_university": "our_manager", "is_primary": False},
            university_id=uni.id,
            responsible_id=mgr.id,
        )

        # university_programs: 2-3 programs
        n_progs = 2 + (u_idx % 2)
        uni_progs = []
        for k in range(n_progs):
            prog = programs[prog_names[(u_idx + k) % len(prog_names)]]
            status = "launched" if u_idx < 5 else ("active" if k == 0 else "planned")
            if uname.startswith("Дальневосточный"):
                status = "planned"
            up, _ = _get_or_create(
                session,
                UniversityProgram,
                {
                    "status": status,
                    "launch_date": (today - timedelta(days=200) if status == "launched" else None),
                    "responsible_id": uni_resps[0].id,
                },
                university_id=uni.id,
                program_id=prog.id,
            )
            uni_progs.append((prog, up))

        # --- licenses + contracts (P1-09-02 expiry plan) ---
        exp_plan = LICENSE_EXPIRY.get(uname, [180])
        for l_idx, delta in enumerate(exp_plan):
            prod = products[(u_idx + l_idx) % len(products)]
            lic_no = f"LIC-{u_idx:02d}-{l_idx:02d}"
            con_no = f"DOG-{u_idx:02d}-{l_idx:02d}"
            signed = today - timedelta(days=335)
            expires = today + timedelta(days=delta)
            is_expired_contract = uname == "НИУ ВШЭ" and l_idx == 0
            contract, _ = _get_or_create(
                session,
                Contract,
                {
                    "university_id": uni.id,
                 "product_id": prod.id if l_idx == 0 else None,
                 "signed_at": signed,
                    "expires_at": (today - timedelta(days=12) if is_expired_contract else expires),
                 "status_raw": "signed",
                 "transfer_status_raw": "accepted",
                    "comment": None,
                },
                contract_number=con_no,
            )
            lic, lic_created = _get_or_create(
                session,
                License,
                {
                    "university_id": uni.id,
                    "product_id": prod.id,
                    # No program/direction links here: binding is specified
                    # at workflow creation (or directly on the license).
                    "contract_id": contract.id,
                    "signed_at": signed,
                    "expires_at": expires,
                    "transfer_status_raw": "accepted",
                    "comment": None,
                },
                license_number=lic_no,
            )
            if lic_created:
                _get_or_create(
                    session,
                    UniversityProduct,
                    {"license_id": lic.id, "status": "active"},
                    university_id=uni.id,
                    product_id=prod.id,
                )
        # extra framework contract (no product) per university
        fw_no = f"DOG-{u_idx:02d}-FW"
        _get_or_create(
            session,
            Contract,
            {
                "university_id": uni.id,
                "product_id": None,
             "signed_at": today - timedelta(days=100),
             "expires_at": today + timedelta(days=600),
                "status_raw": "signed",
                "transfer_status_raw": "transferred",
                "comment": "Рамочный договор",
            },
            contract_number=fw_no,
        )

        # --- documents (P1-09-02 overdue plan) ---
        n_docs = 4
        for d_idx in range(n_docs):
            title = f"Документ {d_idx + 1} ({uname[:10]})"
            if uname.startswith("Тюменский"):
                exp = today - timedelta(days=10 + d_idx)  # all expired
                st = "signed"
            elif uname.startswith("Дальневосточный"):
                exp = today - timedelta(days=50) if d_idx < 2 else None
                st = "draft" if d_idx >= 2 else "signed"
            elif uname == "МФТИ" and d_idx < 2:
                exp = today - timedelta(days=3 + d_idx)  # 2 expired
                st = "signed"
            else:
                exp = today + timedelta(days=200 + d_idx * 30)
                st = "signed" if d_idx % 2 == 0 else "draft"
            doc, doc_created = _get_or_create(
                session,
                Document,
                {
                    "university_id": uni.id,
                    "document_type": ["contract", "license", "act", "protocol"][d_idx % 4],
                 "file_path": f"storage/u{u_idx}/doc{d_idx}.pdf",
                 "file_name": f"doc{d_idx}.pdf",
                 "file_size": 1024 * (100 + d_idx),
                 "mime_type": "application/pdf",
                    "license_id": None,
                    "contract_id": None,
                 "signed_at": today - timedelta(days=120),
                    "expires_at": exp,
                    "status_raw": st,
                    "uploaded_by_keycloak_sub": SYSTEM_SUB,
                },
                title=title,
            )
            void = doc_created  # noqa: F841 (readability)

        # --- meetings ---
        mtypes = ["online", "offline", "phone", "email"]
        for m_idx in range(3 + (u_idx % 2)):
            subject = f"Встреча {m_idx + 1}: {uname[:12]}"
            mat = datetime.now(timezone.utc) - timedelta(days=m_idx * 40 + u_idx)
            meeting, m_created = _get_or_create(
                session,
                Meeting,
                {
                    "university_id": uni.id,
                 "meeting_type": mtypes[(u_idx + m_idx) % 4],
                 "participants": [
                        {"name": "Иванов И.И.", "role": "Ректор", "side": "university"},
                        {"name": "Петров П.П.", "role": "Менеджер", "side": "our"},
                 ],
                 "outcome": f"Итог встречи {m_idx + 1}",
                    "next_action": ("Подготовить документы" if m_idx == 0 else None),
                    "next_action_due": (
                        today - timedelta(days=5) if m_idx == 0 and u_idx % 3 == 0 else None
                    ),
                 "meeting_at": mat,
                    "created_by_keycloak_sub": SYSTEM_SUB,
                },
                subject=subject,
            )
            if m_created and m_idx == 0:
                # attachment link: meeting <-> first document
                first_doc = session.execute(
                    select(Document).filter_by(university_id=uni.id).limit(1)
                ).scalar_one_or_none()
                if first_doc is not None:
                    session.add(MeetingDocument(meeting_id=meeting.id, document_id=first_doc.id))

        # --- interaction notes ---
        for n_idx in range(2):
            _get_or_create(
                session,
                InteractionNote,
                {
                    "university_id": uni.id,
                 "author_keycloak_sub": SYSTEM_SUB,
                 "content": f"Заметка {n_idx + 1} по {uname[:20]}",
                    "is_internal": True,
                },
                university_id=uni.id,
                content=f"Заметка {n_idx + 1} по {uname[:20]}",
            )

    session.commit()

    wf_stats = seed_workflow_templates(session)

    stats = _collect_stats(session)
    stats.update(wf_stats)
    return stats


def _collect_stats(session: Session) -> dict:
    stats: dict[str, int] = {}
    for model, label in [
        (University, "universities"),
        (ITDirection, "directions"),
        (ITProgram, "programs"),
        (Vendor, "vendors"),
        (ITProduct, "products"),
        (Responsible, "responsibles"),
        (License, "licenses"),
        (Contract, "contracts"),
        (Meeting, "meetings"),
        (Document, "documents"),
        (InteractionNote, "interaction_notes"),
        (UniversityProgram, "university_programs"),
        (UniversityProduct, "university_products"),
    ]:
        stats[label] = session.execute(select(model.id)).scalars().all().__len__()
    return stats


def main() -> None:
    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    with Session(engine) as session:
        stats = seed_demo(session)
    logging.getLogger("rtk.seed").info("SEED OK: %s", stats)


if __name__ == "__main__":
    main()

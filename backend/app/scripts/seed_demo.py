"""Production-ready idempotent demo seed for the RTK EdTech CRM.

One command after a clean deploy::

    docker compose exec -e SEED_DEMO_DATA=true backend python -m app.scripts.seed_demo

Dataset (stable natural/demo keys, never hardcoded UUIDs):

* 5 universities (key: ``name``)
* 6 directions (key: ``code`` — ``IB-DEMO`` … ``NET-DEMO``)
* 9 programs (key: ``name`` + direction; existing ``DevOps-инженерия``
  is reused, never duplicated)
* 5 vendors (key: ``name``)
* 10 products (key: ``vendor_id`` + ``name`` + ``version``)
* 5 responsibles (key: ``email``) + primary university links
* 9 university_programs, 10 university_products links
* 4 contracts (key: ``contract_number``), 4 licenses (key: ``license_number``)
* 1 demo workflow template + 5 stages (key: ``name``)
* 5 workflow instances — one per university (key: university + template)
* 5 meetings (key: university + ``subject``)

Idempotency: every entity is looked up by its natural key first and only
created when missing. Relative dates (``today ± N days``) are computed
ONLY at first creation — reruns never rewrite existing rows, so the second
run is a NO-OP: no duplicates, no extra transitions, no audit noise.

Audit: the seed session never carries ``audit_context`` in ``db.info``,
so plain ORM writes emit no audit events at all. Workflow moves go through
the canonical ``transition_instance`` service and therefore enqueue one
``WORKFLOW_TRANSITION`` outbox row per *actual* move — reruns that find
the instance already on the target stage perform no move and enqueue
nothing.

Transactions: plain ORM rows are added/flushed in ONE session and committed
once at the end (``ROLLBACK`` on any error). ``create_instance`` /
``transition_instance`` manage their own transaction internally (project
pattern — they ``commit()`` inside the service); they run LAST, after the
ORM part is committed, so a workflow failure can never leave catalog rows
half-written, and a rerun simply resumes. See ``TRANSACTION`` below.

Production safety: without ``SEED_DEMO_DATA=true`` (or
``--confirm-production``) the script prints a notice and exits WITHOUT
touching the database. ``--dry-run`` never writes (ORM work is rolled back,
workflow operations are only reported).

TRANSACTION (explicit, as required):
    BEGIN (session)
    -> get-or-create catalog / universities / links / contracts / licenses
    -> get-or-create demo template + stages
    -> flush as needed (no commit yet)
    -> COMMIT (single commit for the whole ORM part)
    -> workflow instances: create_instance() each commits internally
    -> workflow transitions: transition_instance() each commits internally
    On ANY exception before/during: ROLLBACK + clear error message.
    Workflow service commits cannot be rolled back together with the ORM
    part (architectural: the services own their transaction); they run last
    precisely for this reason, and every one of them is idempotent, so a
    rerun after a failure converges to the same final state.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone

# Allow ``python -m app.scripts.seed_demo`` from ``backend/`` as well as
# ``python backend/app/scripts/seed_demo.py`` from the repo root.
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: F401  (register canonical metadata)  # pylint: disable=unused-import
import app.models.audit_outbox  # noqa: F401  (register outbox table)  # pylint: disable=unused-import
import app.modules.audit.models  # noqa: F401  (register audit events)  # pylint: disable=unused-import
from app.config import settings  # noqa: E402
from app.models.catalog import (  # noqa: E402
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
from app.models.interactions import Meeting, UniversityProduct, UniversityProgram  # noqa: E402
from app.models.workflow_instances import WorkflowInstance  # noqa: E402
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate  # noqa: E402

log = logging.getLogger("rtk.seed_demo")

SYSTEM_SUB = "system-seed-demo"

DEMO_TEMPLATE_NAME = "Демонстрационный маршрут взаимодействия с вузом"
DEMO_TEMPLATE_DESCRIPTION = "Демонстрационный маршрут для первичного знакомства с CRM"
DEMO_STAGES = [
    "Первичный контакт",
    "Согласование программы",
    "Подготовка документов",
    "Согласование договора",
    "Запуск программы",
]

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

UNIVERSITIES = [
    ("Московский технологический университет «Вектор»", "Москва"),
    ("Университет цифровых технологий «Прогресс»", "Санкт-Петербург"),
    ("Поволжский технический университет", "Казань"),
    ("Северо-Западный университет информационных технологий", "Санкт-Петербург"),
    ("Сибирский инженерный университет", "Новосибирск"),
]

UNI_VECTOR, UNI_PROGRESS, UNI_POVOLZHSKY, UNI_NORTHWEST, UNI_SIBERIAN = (
    name for name, _ in UNIVERSITIES
)

DIRECTIONS = [
    ("IB-DEMO", "Информационная безопасность"),
    ("DEV-DEMO", "Разработка программного обеспечения"),
    ("AI-DEMO", "Искусственный интеллект и анализ данных"),
    ("CLOUD-DEMO", "Облачные технологии"),
    ("DEVOPS-DEMO", "DevOps и инфраструктура"),
    ("NET-DEMO", "Сетевые технологии"),
]

# (program name, direction code)
PROGRAMS = [
    ("Основы информационной безопасности", "IB-DEMO"),
    ("Защита корпоративной инфраструктуры", "IB-DEMO"),
    ("Современная backend-разработка", "DEV-DEMO"),
    ("Разработка корпоративных приложений", "DEV-DEMO"),
    ("Анализ данных", "AI-DEMO"),
    ("Основы машинного обучения", "AI-DEMO"),
    ("Облачная инфраструктура", "CLOUD-DEMO"),
    ("Контейнеризация и CI/CD", "DEVOPS-DEMO"),
    ("DevOps-инженерия", "DEVOPS-DEMO"),
]

RESPONSIBLES = [
    # (full_name, email, role, university name)
    ("Иванов Алексей Сергеевич", "alexey.ivanov@example.ru", "Куратор", UNI_VECTOR),
    ("Петрова Мария Андреевна", "maria.petrova@example.ru", "Менеджер", UNI_PROGRESS),
    ("Смирнов Дмитрий Олегович", "dmitry.smirnov@example.ru", "Ответственный", UNI_POVOLZHSKY),
    ("Кузнецова Анна Викторовна", "anna.kuznetsova@example.ru", "Куратор", UNI_NORTHWEST),
    ("Соколов Михаил Игоревич", "mikhail.sokolov@example.ru", "Менеджер", UNI_SIBERIAN),
]

VENDORS = ["TechNova", "SecureSoft", "DataCore", "CloudSystems", "InfraLab"]

# (product name, vendor name, program name, version)
PRODUCTS = [
    ("SecureGate", "SecureSoft", "Защита корпоративной инфраструктуры", "5.4"),
    ("SecureMail", "SecureSoft", "Основы информационной безопасности", "2.1"),
    ("NovaERP", "TechNova", "Разработка корпоративных приложений", "7.0"),
    ("NovaBackend", "TechNova", "Современная backend-разработка", "3.3"),
    ("Data Analytics Studio", "DataCore", "Анализ данных", "4.8"),
    ("ML Platform", "DataCore", "Основы машинного обучения", "1.9"),
    ("CloudPlatform", "CloudSystems", "Облачная инфраструктура", "3.2"),
    ("CloudBackup", "CloudSystems", "Облачная инфраструктура", "1.4"),
    ("DevOps Suite", "InfraLab", "DevOps-инженерия", "2026.1"),
    ("Pipeline Runner", "InfraLab", "Контейнеризация и CI/CD", "6.0"),
]

# (university name, program name, status)
UNIVERSITY_PROGRAMS = [
    (UNI_VECTOR, "Защита корпоративной инфраструктуры", "active"),
    (UNI_VECTOR, "Основы информационной безопасности", "planned"),
    (UNI_PROGRESS, "Анализ данных", "active"),
    (UNI_PROGRESS, "Основы машинного обучения", "planned"),
    (UNI_POVOLZHSKY, "Облачная инфраструктура", "active"),
    (UNI_NORTHWEST, "DevOps-инженерия", "active"),
    (UNI_NORTHWEST, "Контейнеризация и CI/CD", "planned"),
    (UNI_SIBERIAN, "Современная backend-разработка", "active"),
    (UNI_SIBERIAN, "Разработка корпоративных приложений", "planned"),
]

# (university name, product name)
UNIVERSITY_PRODUCTS = [
    (UNI_VECTOR, "SecureGate"),
    (UNI_VECTOR, "SecureMail"),
    (UNI_PROGRESS, "Data Analytics Studio"),
    (UNI_PROGRESS, "ML Platform"),
    (UNI_POVOLZHSKY, "CloudPlatform"),
    (UNI_POVOLZHSKY, "CloudBackup"),
    (UNI_NORTHWEST, "DevOps Suite"),
    (UNI_NORTHWEST, "Pipeline Runner"),
    (UNI_SIBERIAN, "NovaBackend"),
    (UNI_SIBERIAN, "NovaERP"),
]

# (contract number, university name, product name)
CONTRACTS = [
    ("ДОГ-ДЕМО-01", UNI_VECTOR, "SecureGate"),
    ("ДОГ-ДЕМО-02", UNI_PROGRESS, "Data Analytics Studio"),
    ("ДОГ-ДЕМО-03", UNI_POVOLZHSKY, "CloudPlatform"),
    ("ДОГ-ДЕМО-04", UNI_SIBERIAN, "NovaBackend"),
]

# (license number, university name, product name, contract number, days to expiry)
LICENSES = [
    ("ЛИЦ-ДЕМО-01", UNI_VECTOR, "SecureGate", "ДОГ-ДЕМО-01", 335),
    ("ЛИЦ-ДЕМО-02", UNI_PROGRESS, "Data Analytics Studio", "ДОГ-ДЕМО-02", 20),
    ("ЛИЦ-ДЕМО-03", UNI_POVOLZHSKY, "CloudPlatform", "ДОГ-ДЕМО-03", 200),
    ("ЛИЦ-ДЕМО-04", UNI_SIBERIAN, "NovaBackend", "ДОГ-ДЕМО-04", 120),
]

# university name -> demo instance program + target stage
INSTANCE_PLAN = {
    UNI_POVOLZHSKY: ("Облачная инфраструктура", "Первичный контакт"),
    UNI_VECTOR: ("Защита корпоративной инфраструктуры", "Согласование программы"),
    UNI_PROGRESS: ("Анализ данных", "Подготовка документов"),
    UNI_NORTHWEST: ("DevOps-инженерия", "Согласование договора"),
    UNI_SIBERIAN: ("Современная backend-разработка", "Согласование программы"),
}

# (university name, meeting subject, days offset from today)
MEETINGS = [
    (UNI_VECTOR, "Установочная встреча", 0),
    (UNI_PROGRESS, "Обсуждение образовательной программы", -1),
    (UNI_SIBERIAN, "Обсуждение договора", -2),
    (UNI_POVOLZHSKY, "Обсуждение облачной инфраструктуры", -3),
    (UNI_NORTHWEST, "Согласование состава продуктов", -5),
]


# ---------------------------------------------------------------------------
# Stats / output helpers
# ---------------------------------------------------------------------------


class SeedStats:
    """Per-entity created/existing counters for the final summary."""

    def __init__(self) -> None:
        self.created: Counter[str] = Counter()
        self.existing: Counter[str] = Counter()
        self.transitions = 0

    @property
    def total_created(self) -> int:
        return sum(self.created.values())

    def summary_lines(self, order: list[str]) -> list[str]:
        lines = []
        for key in order:
            lines.append(
                f"{key}: {self.created.get(key, 0)} created, "
                f"{self.existing.get(key, 0)} existing"
            )
        return lines


SUMMARY_ORDER = [
    "universities",
    "directions",
    "programs",
    "vendors",
    "products",
    "responsibles",
    "responsible_links",
    "university_programs",
    "university_products",
    "contracts",
    "licenses",
    "workflow_templates",
    "workflow_stages",
    "workflow_instances",
    "meetings",
]


def _say(dry_run: bool, verbose: bool, message: str, *, always: bool = False) -> None:
    """Console output. ``[DRY-RUN]``-prefixed when nothing is written."""
    if always or verbose or message.startswith(("[CREATE]", "[LINK]", "[STAGE]", "[FOUND]", "[WARN]", "[SKIP]")):
        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}{message}")


def _get_or_create(session: Session, stats: SeedStats, label: str, model, defaults: dict, **key):
    """Idempotent lookup by natural key; creates + flushes only when missing."""
    obj = session.execute(select(model).filter_by(**key)).scalar_one_or_none()
    if obj is not None:
        stats.existing[label] += 1
        return obj, False
    obj = model(**{**key, **defaults})
    session.add(obj)
    session.flush()  # assign PK for downstream FKs; still inside the transaction
    stats.created[label] += 1
    return obj, True


# ---------------------------------------------------------------------------
# Seed steps (pure ORM — single transaction, no service commits)
# ---------------------------------------------------------------------------


def _seed_catalog(session: Session, stats: SeedStats, dry_run: bool, verbose: bool) -> dict:
    directions: dict[str, ITDirection] = {}
    for code, name in DIRECTIONS:
        direction, created = _get_or_create(
            session, stats, "directions", ITDirection, {"name": name}, code=code
        )
        directions[code] = direction
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} Direction: {name} ({code})")

    programs: dict[str, ITProgram] = {}
    for prog_name, dir_code in PROGRAMS:
        if prog_name == "DevOps-инженерия":
            # Reuse a pre-existing program with this name (any direction) —
            # never create "DevOps-инженерия (2)".
            existing = session.execute(
                select(ITProgram).where(ITProgram.name == prog_name)
            ).scalar_one_or_none()
            if existing is not None:
                programs[prog_name] = existing
                stats.existing["programs"] += 1
                _say(dry_run, verbose, f"[FOUND] Program: {prog_name} (reused)")
                continue
        program, created = _get_or_create(
            session,
            stats,
            "programs",
            ITProgram,
            {"direction_id": directions[dir_code].id, "description": ""},
            name=prog_name,
            direction_id=directions[dir_code].id,
        )
        programs[prog_name] = program
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} Program: {prog_name}")

    vendors: dict[str, Vendor] = {}
    for vendor_name in VENDORS:
        vendor, created = _get_or_create(
            session, stats, "vendors", Vendor, {}, name=vendor_name
        )
        vendors[vendor_name] = vendor
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} Vendor: {vendor_name}")

    products: dict[str, ITProduct] = {}
    for prod_name, vendor_name, prog_name, version in PRODUCTS:
        vendor = vendors[vendor_name]
        program = programs[prog_name]
        product, created = _get_or_create(
            session,
            stats,
            "products",
            ITProduct,
            {"vendor_id": vendor.id, "program_id": program.id},
            vendor_id=vendor.id,
            name=prod_name,
            version=version,
        )
        products[prod_name] = product
        _say(
            dry_run,
            verbose,
            f"{'[CREATE]' if created else '[FOUND]'} Product: {prod_name} {version} "
            f"({vendor_name} / {prog_name})",
        )
    return {"directions": directions, "programs": programs, "vendors": vendors, "products": products}


def _seed_universities(session: Session, stats: SeedStats, dry_run: bool, verbose: bool) -> dict:
    universities: dict[str, University] = {}
    for uni_name, city in UNIVERSITIES:
        uni, created = _get_or_create(
            session, stats, "universities", University, {"city": city}, name=uni_name
        )
        universities[uni_name] = uni
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} University: {uni_name}")

    responsibles: dict[str, Responsible] = {}
    for full_name, email, role, uni_name in RESPONSIBLES:
        resp, created = _get_or_create(
            session,
            stats,
            "responsibles",
            Responsible,
            {"full_name": full_name, "role": role},
            email=email,
        )
        responsibles[email] = resp
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} Responsible: {full_name}")
        uni = universities[uni_name]
        _get_or_create(
            session,
            stats,
            "responsible_links",
            UniversityResponsible,
            {"role_in_university": "primary", "is_primary": True},
            university_id=uni.id,
            responsible_id=resp.id,
        )
        _say(dry_run, verbose, f"[LINK] {full_name} -> {uni_name}")
    return {"universities": universities, "responsibles": responsibles}


def _seed_links(
    session: Session,
    stats: SeedStats,
    dry_run: bool,
    verbose: bool,
    universities: dict[str, University],
    programs: dict[str, ITProgram],
    products: dict[str, ITProduct],
) -> None:
    for uni_name, prog_name, status in UNIVERSITY_PROGRAMS:
        uni, prog = universities[uni_name], programs[prog_name]
        _, created = _get_or_create(
            session,
            stats,
            "university_programs",
            UniversityProgram,
            {"status": status},
            university_id=uni.id,
            program_id=prog.id,
        )
        _say(
            dry_run,
            verbose,
            f"{'[CREATE]' if created else '[FOUND]'} UniversityProgram: "
            f"{uni_name} x {prog_name} [{status}]",
        )

    for uni_name, prod_name in UNIVERSITY_PRODUCTS:
        uni, prod = universities[uni_name], products[prod_name]
        _, created = _get_or_create(
            session,
            stats,
            "university_products",
            UniversityProduct,
            {"status": "active"},
            university_id=uni.id,
            product_id=prod.id,
        )
        _say(
            dry_run,
            verbose,
            f"{'[CREATE]' if created else '[FOUND]'} UniversityProduct: {uni_name} x {prod_name}",
        )


def _seed_contracts_licenses(
    session: Session,
    stats: SeedStats,
    dry_run: bool,
    verbose: bool,
    universities: dict[str, University],
    products: dict[str, ITProduct],
) -> None:
    today = date.today()
    contracts: dict[str, Contract] = {}
    for number, uni_name, prod_name in CONTRACTS:
        uni, prod = universities[uni_name], products[prod_name]
        contract, created = _get_or_create(
            session,
            stats,
            "contracts",
            Contract,
            {
                "university_id": uni.id,
                "product_id": prod.id,
                "signed_at": today - timedelta(days=60),
                "expires_at": today + timedelta(days=305),
                "status_raw": "signed",
                "transfer_status_raw": "accepted",
                "comment": "Демонстрационный договор",
            },
            contract_number=number,
        )
        contracts[number] = contract
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} Contract: {number}")

    for number, uni_name, prod_name, contract_number, days_to_expiry in LICENSES:
        uni, prod = universities[uni_name], products[prod_name]
        lic, created = _get_or_create(
            session,
            stats,
            "licenses",
            License,
            {
                "university_id": uni.id,
                "product_id": prod.id,
                "contract_id": contracts[contract_number].id,
                "signed_at": today - timedelta(days=60),
                # Relative dates are computed ONLY at first creation: an
                # existing license is never re-dated (expires_soon stays
                # meaningful, reruns never shift it).
                "expires_at": today + timedelta(days=days_to_expiry),
                "transfer_status_raw": "accepted",
                "comment": "Демонстрационная лицензия",
            },
            license_number=number,
        )
        _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} License: {number}")


def _seed_template(session: Session, stats: SeedStats, dry_run: bool, verbose: bool):
    template, created = _get_or_create(
        session,
        stats,
        "workflow_templates",
        WorkflowTemplate,
        {"description": DEMO_TEMPLATE_DESCRIPTION, "is_active": True},
        name=DEMO_TEMPLATE_NAME,
    )
    _say(dry_run, verbose, f"{'[CREATE]' if created else '[FOUND]'} WorkflowTemplate: {DEMO_TEMPLATE_NAME}")
    for position, stage_name in enumerate(DEMO_STAGES, start=1):
        _, stage_created = _get_or_create(
            session,
            stats,
            "workflow_stages",
            WorkflowStage,
            {"name": stage_name, "is_required": True, "is_active": True},
            template_id=template.id,
            order_index=position,
        )
        _say(
            dry_run,
            verbose,
            f"{'[CREATE]' if stage_created else '[FOUND]'} WorkflowStage: {position}. {stage_name}",
        )
    return template


def _seed_meetings(
    session: Session,
    stats: SeedStats,
    dry_run: bool,
    verbose: bool,
    universities: dict[str, University],
    responsibles_by_uni: dict[str, Responsible],
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for uni_name, subject, days_offset in MEETINGS:
        uni = universities[uni_name]
        resp = responsibles_by_uni.get(uni_name)
        participants = (
            [{"name": resp.full_name, "role": resp.role, "side": "our"}] if resp else []
        )
        _, created = _get_or_create(
            session,
            stats,
            "meetings",
            Meeting,
            {
                "university_id": uni.id,
                "meeting_type": "online",
                "participants": participants,
                "outcome": "Демонстрационная встреча",
                "meeting_at": now + timedelta(days=days_offset),
                "created_by_keycloak_sub": SYSTEM_SUB,
            },
            university_id=uni.id,
            subject=subject,
        )
        _say(
            dry_run,
            verbose,
            f"{'[CREATE]' if created else '[FOUND]'} Meeting: {subject} ({uni_name})",
        )


# ---------------------------------------------------------------------------
# Workflow instances + transitions (service layer — own transactions)
# ---------------------------------------------------------------------------


def _seed_workflow_instances(
    session: Session,
    stats: SeedStats,
    dry_run: bool,
    verbose: bool,
    template: WorkflowTemplate,
    universities: dict[str, University],
    programs: dict[str, ITProgram],
    responsibles_by_uni: dict[str, Responsible],
) -> None:
    from app.modules.workflow_instances.service import create_instance
    from app.modules.workflow_transitions.service import ordered_stages, transition_instance

    for uni_name, (prog_name, target_stage) in INSTANCE_PLAN.items():
        uni = universities[uni_name]
        existing = session.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.university_id == uni.id,
                WorkflowInstance.template_id == template.id,
            )
        ).scalar_one_or_none()

        if existing is None and dry_run:
            stats.created["workflow_instances"] += 1
            _say(dry_run, verbose, f"[CREATE] WorkflowInstance: {uni_name} (would create)")
            _say(dry_run, verbose, f"[STAGE] {uni_name} -> {target_stage} (would transition)")
            continue

        if existing is None:
            create_instance(
                session,
                university_id=uni.id,
                template_id=template.id,
                program_id=programs[prog_name].id,
                product_id=None,
                responsible_id=(
                    responsibles_by_uni[uni_name].id if uni_name in responsibles_by_uni else None
                ),
                actor_sub=SYSTEM_SUB,
            )
            instance = session.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.university_id == uni.id,
                    WorkflowInstance.template_id == template.id,
                )
            ).scalar_one()
            stats.created["workflow_instances"] += 1
            _say(dry_run, verbose, f"[CREATE] WorkflowInstance: {uni_name}")
        else:
            instance = existing
            stats.existing["workflow_instances"] += 1
            _say(dry_run, verbose, f"[FOUND] WorkflowInstance: {uni_name}")

        # Advance to the target stage step by step (all demo stages are
        # required, so only adjacent moves are legal). Never move backwards
        # and never move an instance that already reached (or passed) target.
        stages = ordered_stages(instance.id, session)
        by_index = {s.order_index: s for s in stages}
        target = next((s for s in stages if s.name == target_stage), None)
        if target is None:
            _say(dry_run, verbose, f"[WARN] target stage missing: {target_stage}", always=True)
            continue
        current = next((s for s in stages if s.id == instance.current_instance_stage_id), None)
        if current is None:
            _say(dry_run, verbose, f"[WARN] instance has no current stage: {uni_name}", always=True)
            continue
        while current.order_index < target.order_index:
            nxt = by_index[current.order_index + 1]
            if dry_run:
                _say(dry_run, verbose, f"[STAGE] {uni_name} -> {nxt.name} (would transition)")
                current = nxt
                continue
            transition_instance(
                session,
                instance.id,
                nxt.id,
                f"Demo seed: переход на этап «{nxt.name}»",
                SYSTEM_SUB,
            )
            stats.transitions += 1
            _say(dry_run, verbose, f"[STAGE] {uni_name} -> {nxt.name}")
            instance = session.get(WorkflowInstance, instance.id)
            stages = ordered_stages(instance.id, session)
            by_index = {s.order_index: s for s in stages}
            current = next((s for s in stages if s.id == instance.current_instance_stage_id), None)
        if current.order_index == target.order_index:
            _say(dry_run, verbose, f"[FOUND] Stage: {uni_name} on «{target_stage}»")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def run_seed(session: Session, *, dry_run: bool = False, verbose: bool = False) -> SeedStats:
    """Execute the full idempotent demo seed on an open session.

    ORM rows are added + flushed but NOT committed here — the caller owns the
    transaction (``main()`` commits once, ``--dry-run`` rolls back).
    Workflow instance creation / transitions commit internally (service
    pattern) and are skipped entirely under ``dry_run``.
    """
    stats = SeedStats()
    catalog = _seed_catalog(session, stats, dry_run, verbose)
    unis = _seed_universities(session, stats, dry_run, verbose)
    _seed_links(
        session, stats, dry_run, verbose,
        unis["universities"], catalog["programs"], catalog["products"],
    )
    _seed_contracts_licenses(
        session, stats, dry_run, verbose, unis["universities"], catalog["products"]
    )
    template = _seed_template(session, stats, dry_run, verbose)

    responsibles_by_uni = {
        uni_name: unis["responsibles"][email]
        for _, email, _, uni_name in RESPONSIBLES
        if email in unis["responsibles"]
    }
    _seed_meetings(session, stats, dry_run, verbose, unis["universities"], responsibles_by_uni)

    # Vendor contacts: the codebase currently exposes only read models for
    # vendor_contacts (no create service/repository) — non-blocking, warn.
    try:
        from app.modules.catalog import service as _catalog_service  # noqa: F401

        _has_contact_write = any(
            hasattr(_catalog_service, name)
            for name in ("create_vendor_contact", "create_contact", "add_vendor_contact")
        )
    except Exception:  # pragma: no cover - defensive
        _has_contact_write = False
    if not _has_contact_write:
        _say(
            dry_run,
            verbose,
            "[WARN] vendor_contacts: no create service/repository in codebase, "
            "skipping contacts (non-blocking)",
            always=True,
        )

    # Overdue/attention demo via the public business API is not safely
    # expressible — skip without failing the seed.
    _say(
        dry_run,
        verbose,
        "[SKIP] Attention=true demo: current business API/domain model "
        "does not support safe creation",
        always=True,
    )

    _seed_workflow_instances(
        session, stats, dry_run, verbose, template,
        unis["universities"], catalog["programs"], responsibles_by_uni,
    )
    return stats


def seeding_enabled(args: argparse.Namespace) -> bool:
    """Explicit opt-in: env flag or CLI flag (never interactive input)."""
    if args.confirm_production:
        return True
    return os.getenv("SEED_DEMO_DATA", "").strip().lower() in ("1", "true", "yes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the demo dataset (idempotent).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be created/linked without writing anything.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-entity FOUND lines."
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Explicit production confirmation (alternative to SEED_DEMO_DATA=true).",
    )
    return parser


def print_summary(stats: SeedStats) -> None:
    print("=== CRM Demo Seed ===")
    print("")
    print("Summary:")
    for line in stats.summary_lines(SUMMARY_ORDER):
        print(f"  {line}")
    if stats.transitions:
        print(f"  workflow transitions performed: {stats.transitions}")
    if stats.total_created == 0 and stats.transitions == 0:
        print("No changes required.")
    print("Seed completed successfully.")


def main(argv: list[str] | None = None) -> int:
    # Windows consoles (cp1251) cannot print Cyrillic demo names otherwise.
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - best effort only
        pass
    args = build_parser().parse_args(argv)

    if not args.dry_run and not seeding_enabled(args):
        print("Demo seeding is disabled.")
        print("Set SEED_DEMO_DATA=true to continue.")
        return 0

    url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            # No audit_context on purpose: seed writes must not emit audit
            # events; transitions enqueue outbox rows only on real moves.
            assert "audit_context" not in session.info
            try:
                stats = run_seed(session, dry_run=args.dry_run, verbose=args.verbose)
                if args.dry_run:
                    session.rollback()
                    print("(dry-run: all changes rolled back)")
                else:
                    session.commit()
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                print(f"Seed failed, transaction rolled back: {exc}", file=sys.stderr)
                return 1
            print_summary(stats)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

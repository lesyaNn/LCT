"""P2-07-05: компонент E — unit + DB тесты (только P1 teachers/programs)."""

from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import UniversityProgram
from app.models.teachers import Teacher, TeacherCertificate, TeacherProgram
from app.modules.health_score.educators_score import calc_E, score_educators

TODAY = date(2026, 9, 20)


def _mem_session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return Session(eng)


def _seed_minimal(db: Session):
    """Вуз + направление + 2 программы (active + archived) + привязки."""
    uni = University(id=uuid4(), name="Вуз E-1")
    direction = ITDirection(id=uuid4(), code="E09", name="Направление E")
    prog_active = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа активная")
    prog_arch = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа архивная")
    db.add_all([uni, direction, prog_active, prog_arch])
    db.flush()
    db.add_all(
        [
            UniversityProgram(
                id=uuid4(), university_id=uni.id, program_id=prog_active.id,
                status="active",
            ),
            UniversityProgram(
                id=uuid4(), university_id=uni.id, program_id=prog_arch.id,
                status="archived",
            ),
        ]
    )
    db.flush()
    return uni, prog_active, prog_arch


def _add_teacher(db: Session, uni_id, program_id, *, mandatory_valid: bool,
                 expired: bool = False, mandatory: bool = True) -> Teacher:
    teacher = Teacher(
        id=uuid4(), university_id=uni_id, full_name="Преподаватель",
        email=f"t-{uuid4()}@example.com",
    )
    db.add(teacher)
    db.flush()
    db.add(
        TeacherProgram(
            id=uuid4(), teacher_id=teacher.id, program_id=program_id,
            assigned_at=TODAY,
        )
    )
    if expired:
        expires = TODAY - timedelta(days=1)
    elif mandatory_valid:
        expires = TODAY + timedelta(days=90)
    else:
        expires = TODAY + timedelta(days=10)  # soon → ATTENTION
    db.add(
        TeacherCertificate(
            id=uuid4(), teacher_id=teacher.id, certificate_name="Обязательный",
            issued_at=TODAY - timedelta(days=100), expires_at=expires,
            is_mandatory=mandatory,
        )
    )
    db.flush()
    return teacher


def test_score_educators_empty_is_100():
    assert score_educators([]) == (100, 0, 0)
    assert score_educators([True, True, False]) == (67, 2, 3)


def test_calc_E_no_active_programs_is_100():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз E-0")
    db.add(uni)
    db.commit()
    assert calc_E(db, uni.id, TODAY) == (100, 0, 0)
    db.close()


def test_calc_E_counts_only_active_programs_and_mandatory():
    db = _mem_session()
    uni, prog_active, prog_arch = _seed_minimal(db)
    # READY на активной программе
    _add_teacher(db, uni.id, prog_active.id, mandatory_valid=True)
    # ATTENTION (скоро истекает) на активной программе
    _add_teacher(db, uni.id, prog_active.id, mandatory_valid=False)
    # READY, но на архивной программе → не требуемый
    _add_teacher(db, uni.id, prog_arch.id, mandatory_valid=True)
    # READY-сертификат, но не mandatory → не требуемый
    _add_teacher(db, uni.id, prog_active.id, mandatory_valid=True, mandatory=False)
    db.commit()

    score, ready, total = calc_E(db, uni.id, TODAY)
    assert (ready, total) == (1, 2)
    assert score == 50
    db.close()


def test_calc_E_expired_is_not_ready():
    db = _mem_session()
    uni, prog_active, _ = _seed_minimal(db)
    _add_teacher(db, uni.id, prog_active.id, mandatory_valid=True, expired=True)
    db.commit()
    assert calc_E(db, uni.id, TODAY) == (0, 0, 1)
    db.close()

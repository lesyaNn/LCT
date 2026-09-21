"""P2-07-06: компонент L — unit + DB тесты (только P1 university_programs)."""

from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import UniversityProgram
from app.modules.health_score.launch_score import calc_L, score_single_program

TODAY = date(2026, 9, 20)


def _mem_session() -> Session:
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return Session(eng)


def test_score_single_program_matrix():
    assert score_single_program("launched", TODAY, TODAY) == 100
    assert score_single_program("launched", TODAY + timedelta(days=5), TODAY) == 70
    assert score_single_program("active", None, TODAY) == 70
    assert score_single_program("active", TODAY - timedelta(days=1), TODAY) == 0
    assert score_single_program("active", TODAY + timedelta(days=10), TODAY) == 40
    assert score_single_program("active", TODAY + timedelta(days=31), TODAY) == 70
    assert score_single_program("planned", None, TODAY) == 70
    assert score_single_program("planned", TODAY - timedelta(days=100), TODAY) == 70
    assert score_single_program("archived", TODAY, TODAY) == 0


def test_calc_L_empty_is_100():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз L-0")
    db.add(uni)
    db.commit()
    assert calc_L(db, uni.id, TODAY) == (100, 0, 0)
    db.close()


def test_calc_L_average_and_archived_ignored():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз L-1")
    direction = ITDirection(id=uuid4(), code="L09", name="Направление L")
    db.add_all([uni, direction])
    db.flush()
    programs = [
        ITProgram(id=uuid4(), direction_id=direction.id, name=f"Программа {i}")
        for i in range(4)
    ]
    db.add_all(programs)
    db.flush()
    links = [
        # launched вовремя → 100
        UniversityProgram(
            id=uuid4(), university_id=uni.id, program_id=programs[0].id,
            status="launched", launch_date=TODAY,
        ),
        # active под риском → 40
        UniversityProgram(
            id=uuid4(), university_id=uni.id, program_id=programs[1].id,
            status="active", launch_date=TODAY + timedelta(days=10),
        ),
        # planned → 70
        UniversityProgram(
            id=uuid4(), university_id=uni.id, program_id=programs[2].id,
            status="planned", launch_date=None,
        ),
        # archived → вне скоупа
        UniversityProgram(
            id=uuid4(), university_id=uni.id, program_id=programs[3].id,
            status="archived", launch_date=TODAY - timedelta(days=5),
        ),
    ]
    db.add_all(links)
    db.commit()

    avg, total, ready = calc_L(db, uni.id, TODAY)
    assert total == 3
    assert ready == 2  # 100 и 70
    assert avg == round((100 + 40 + 70) / 3) == 70
    db.close()


def test_calc_L_overdue_is_zero():
    db = _mem_session()
    uni = University(id=uuid4(), name="Вуз L-2")
    direction = ITDirection(id=uuid4(), code="L10", name="Направление L2")
    prog = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа")
    db.add_all([uni, direction, prog])
    db.flush()
    db.add(
        UniversityProgram(
            id=uuid4(), university_id=uni.id, program_id=prog.id,
            status="active", launch_date=TODAY - timedelta(days=1),
        )
    )
    db.commit()
    assert calc_L(db, uni.id, TODAY) == (0, 1, 0)
    db.close()

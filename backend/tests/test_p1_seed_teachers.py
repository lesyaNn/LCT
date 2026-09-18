"""P1-09-03: seed creates teachers with the exact readiness distribution.

Locks the per-university plan from the spec: 34 teachers total, readiness
computed with the same deterministic service the passport endpoint and
Health Score component E use (``compute_teacher_readiness``).

NOTE: the task's AC line ("30 teachers, 12/6/12") contradicts its own
per-university table (which sums to 34). This test locks the
per-university table as the detailed source of truth:
16 ready + 2 no-mandatory-cert (ready by logic) + 5 attention + 11 expired.
"""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import University
from app.models.teachers import Teacher
from app.services.teacher_readiness import compute_teacher_readiness

# university -> (teachers, {readiness: count})
EXPECTED_PLAN = {
    "МГУ им. М.В. Ломоносова": (5, {"ready": 5}),
    "СПбГУ": (4, {"ready": 3, "attention": 1}),
    "НИУ ВШЭ": (4, {"ready": 2, "attention": 2}),
    "МФТИ": (3, {"ready": 2, "expired": 1}),
    "ИТМО": (4, {"ready": 2, "expired": 2}),
    "УрФУ": (3, {"attention": 1, "expired": 2}),
    "Тюменский государственный университет": (2, {"expired": 2}),
    "Дальневосточный федеральный университет": (2, {"ready": 2}),
    "СибГУТИ": (4, {"ready": 2, "attention": 1, "expired": 1}),
    "КФУ": (3, {"expired": 3}),
}

MANDATORY_NAMES = {
    "Информационная безопасность",
    "Методика преподавания ИТ",
    "Стандарты ФГОС",
}


def _readiness(teacher: Teacher) -> str:
    result = compute_teacher_readiness(
        certificates=teacher.certificates,
        qualifications=teacher.qualifications,
    )
    return result.readiness.value


def test_teacher_count_per_university(seeded_db: Session):
    for uni_name, (expected_count, _) in EXPECTED_PLAN.items():
        uni = seeded_db.execute(
            select(University).filter_by(name=uni_name)
        ).scalar_one()
        actual = seeded_db.execute(
            select(func.count()).select_from(Teacher).filter_by(university_id=uni.id)
        ).scalar()
        assert actual == expected_count, (uni_name, actual)


def test_total_teachers(seeded_db: Session):
    total = seeded_db.execute(select(func.count()).select_from(Teacher)).scalar()
    assert total == 34


def test_readiness_distribution_per_university(seeded_db: Session):
    for uni_name, (_, expected) in EXPECTED_PLAN.items():
        uni = seeded_db.execute(
            select(University).filter_by(name=uni_name)
        ).scalar_one()
        teachers = seeded_db.execute(
            select(Teacher).filter_by(university_id=uni.id)
        ).scalars().all()
        actual = Counter(_readiness(t) for t in teachers)
        assert dict(actual) == expected, (uni_name, dict(actual))


def test_global_readiness_totals(seeded_db: Session):
    teachers = seeded_db.execute(select(Teacher)).scalars().all()
    total = Counter(_readiness(t) for t in teachers)
    assert total["ready"] == 18, total
    assert total["attention"] == 5, total
    assert total["expired"] == 11, total


def test_mandatory_certificate_names(seeded_db: Session):
    from app.models.teachers import TeacherCertificate

    names = set(
        seeded_db.execute(
            select(TeacherCertificate.certificate_name).filter_by(is_mandatory=True)
        ).scalars().all()
    )
    assert names <= MANDATORY_NAMES, names
    assert len(names) >= 2, names


def test_expired_teachers_have_reasons(seeded_db: Session):
    teachers = seeded_db.execute(select(Teacher)).scalars().all()
    expired = [
        t
        for t in teachers
        if _readiness(t) == "expired"
    ]
    assert len(expired) == 11
    for teacher in expired:
        result = compute_teacher_readiness(
            certificates=teacher.certificates,
            qualifications=teacher.qualifications,
        )
        assert result.reasons, teacher.email
        assert any("Истёк" in r for r in result.reasons), result.reasons


def test_dvfu_teachers_ready_without_mandatory(seeded_db: Session):
    from app.models.teachers import TeacherCertificate

    uni = seeded_db.execute(
        select(University).filter_by(
            name="Дальневосточный федеральный университет"
        )
    ).scalar_one()
    teachers = seeded_db.execute(
        select(Teacher).filter_by(university_id=uni.id)
    ).scalars().all()
    assert len(teachers) == 2
    for teacher in teachers:
        mandatory = [c for c in teacher.certificates if c.is_mandatory]
        assert mandatory == []
        assert _readiness(teacher) == "ready"
    _ = TeacherCertificate  # re-export guard

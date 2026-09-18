"""P1-09-01: demo seed creates 10 universities with full per-uni data.

Locks the acceptance criteria: 10 universities, each with programs,
teachers, licensed products, contracts, documents, meetings, responsibles
and students. Health Score distribution itself is P2-owned; P1 guarantees
the raw signals (green/yellow/red profiles) exist.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Contract, License, Responsible, University
from app.models.interactions import (
    Document,
    Meeting,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import Teacher

EXPECTED_UNIVERSITIES = {
    "МГУ им. М.В. Ломоносова",
    "СПбГУ",
    "НИУ ВШЭ",
    "МФТИ",
    "ИТМО",
    "УрФУ",
    "Тюменский государственный университет",
    "Дальневосточный федеральный университет",
    "СибГУТИ",
    "КФУ",
}


def test_ten_universities(seeded_db: Session):
    names = set(seeded_db.execute(select(University.name)).scalars().all())
    assert names == EXPECTED_UNIVERSITIES


def test_each_university_has_full_profile(seeded_db: Session):
    for uni in seeded_db.execute(select(University)).scalars().all():
        n_progs = seeded_db.execute(
            select(func.count())
            .select_from(UniversityProgram)
            .filter_by(university_id=uni.id)
        ).scalar()
        assert 2 <= n_progs <= 3, (uni.name, n_progs)

        n_teachers = seeded_db.execute(
            select(func.count()).select_from(Teacher).filter_by(university_id=uni.id)
        ).scalar()
        assert 2 <= n_teachers <= 5, (uni.name, n_teachers)

        n_licenses = seeded_db.execute(
            select(func.count()).select_from(License).filter_by(university_id=uni.id)
        ).scalar()
        assert n_licenses >= 1, (uni.name, n_licenses)

        n_contracts = seeded_db.execute(
            select(func.count()).select_from(Contract).filter_by(university_id=uni.id)
        ).scalar()
        assert n_contracts >= 2, (uni.name, n_contracts)

        n_docs = seeded_db.execute(
            select(func.count()).select_from(Document).filter_by(university_id=uni.id)
        ).scalar()
        assert n_docs >= 3, (uni.name, n_docs)

        n_meetings = seeded_db.execute(
            select(func.count()).select_from(Meeting).filter_by(university_id=uni.id)
        ).scalar()
        assert n_meetings >= 3, (uni.name, n_meetings)

        n_students = seeded_db.execute(
            select(func.count()).select_from(Student).filter_by(university_id=uni.id)
        ).scalar()
        assert n_students >= 50, (uni.name, n_students)

        assert len(uni.university_responsibles) >= 2, uni.name

        n_products = seeded_db.execute(
            select(func.count())
            .select_from(UniversityProduct)
            .filter_by(university_id=uni.id)
        ).scalar()
        assert n_products >= 1, (uni.name, n_products)


def test_responsibles_are_real_people(seeded_db: Session):
    total = seeded_db.execute(select(func.count()).select_from(Responsible)).scalar()
    assert total >= 20
    безымянных = seeded_db.execute(
        select(func.count()).select_from(Responsible).filter_by(full_name="")
    ).scalar()
    assert безымянных == 0

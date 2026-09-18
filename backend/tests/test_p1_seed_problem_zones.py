"""P1-09-02: seed covers expiring licenses, overdue documents/contracts.

Locks the exact spec cases so Health Score components D (documents) and
T/L (overdue items) always have demo signals:
* МГУ: 1 license expiring in 5 days; СПбГУ: 15/25; ИТМО: 3/10/28.
* УрФУ: all licenses active (> 60 days).
* МФТИ: 2 expired documents; ВШЭ: 1 expired contract;
  Тюменский: all documents expired; ДВФУ: no valid documents.

Workflow progress seeding is P2-owned (workflow instances live in P2
tables) and intentionally out of scope here.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Contract, License, University
from app.models.interactions import Document


def _uni(seeded_db: Session, name: str) -> University:
    return seeded_db.execute(
        select(University).filter_by(name=name)
    ).scalar_one()


def _expiry_deltas(seeded_db: Session, uni_name: str) -> sorted:
    uni = _uni(seeded_db, uni_name)
    licenses = seeded_db.execute(
        select(License).filter_by(university_id=uni.id)
    ).scalars().all()
    assert licenses, uni_name
    return sorted((lic.expires_at - date.today()).days for lic in licenses)


def test_expiring_licenses_per_spec(seeded_db: Session):
    assert _expiry_deltas(seeded_db, "МГУ им. М.В. Ломоносова")[0] == 5
    assert _expiry_deltas(seeded_db, "СПбГУ") == [15, 25]
    assert _expiry_deltas(seeded_db, "ИТМО") == [3, 10, 28]


def test_urfu_licenses_all_active(seeded_db: Session):
    deltas = _expiry_deltas(seeded_db, "УрФУ")
    assert deltas and min(deltas) > 60, deltas


def test_derived_statuses_cover_all_branches(seeded_db: Session):
    statuses = {
        lic.derived_status
        for lic in seeded_db.execute(select(License)).scalars().all()
    }
    assert {"active", "expires_soon", "expired"} <= statuses, statuses


def test_mfti_two_expired_documents(seeded_db: Session):
    uni = _uni(seeded_db, "МФТИ")
    docs = seeded_db.execute(
        select(Document).filter_by(university_id=uni.id)
    ).scalars().all()
    expired = [d for d in docs if d.expires_at and d.expires_at < date.today()]
    assert len(expired) == 2, [(d.title, d.expires_at) for d in docs]


def test_hse_one_expired_contract(seeded_db: Session):
    uni = _uni(seeded_db, "НИУ ВШЭ")
    contracts = seeded_db.execute(
        select(Contract).filter_by(university_id=uni.id)
    ).scalars().all()
    expired = [c for c in contracts if c.derived_status == "expired"]
    assert len(expired) == 1, [(c.contract_number, c.expires_at) for c in contracts]


def test_tyumen_all_documents_expired(seeded_db: Session):
    uni = _uni(seeded_db, "Тюменский государственный университет")
    docs = seeded_db.execute(
        select(Document).filter_by(university_id=uni.id)
    ).scalars().all()
    assert docs
    assert all(d.expires_at and d.expires_at < date.today() for d in docs)


def test_dvfu_no_valid_documents(seeded_db: Session):
    uni = _uni(seeded_db, "Дальневосточный федеральный университет")
    docs = seeded_db.execute(
        select(Document).filter_by(university_id=uni.id)
    ).scalars().all()
    assert docs
    valid = [d for d in docs if d.expires_at and d.expires_at >= date.today()]
    assert valid == []

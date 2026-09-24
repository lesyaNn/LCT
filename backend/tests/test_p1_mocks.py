"""P1-12-01: committed mocks validate against the Pydantic schemas.

Regenerate with ``python scripts/generate_mocks.py`` (from ``backend/``);
this test locks the AC: files exist, parse as ``UniversityPassport`` /
``TeacherPassport``, and contain the headline demo signals (expiring
license, attention teacher with reasons).
"""

import json
import os
from datetime import date

import app.schemas.licenses as license_schemas
from app.schemas import TeacherPassport, UniversityPassport
from app.services.license_status import derive_license_status, days_to_expiry

MOCKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "mocks",
)


def _load(name: str) -> dict:
    path = os.path.join(MOCKS_DIR, name)
    assert os.path.exists(path), f"missing mock file: {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_university_passport_valid():
    payload = _load("university-passport.json")
    passport = UniversityPassport.model_validate(payload)
    assert passport.university.name == "МГУ им. М.В. Ломоносова"
    assert len(passport.programs) >= 2
    assert len(passport.teachers) >= 2
    assert passport.students_summary.total > 0
    assert len(passport.licenses) >= 1
    assert len(passport.documents) >= 1
    assert len(passport.meetings) >= 1
    assert len(passport.responsibles) >= 1


def test_university_passport_shows_expiring_license(monkeypatch):
    """The public mock keeps its 2026-09-23 expiry semantics.

    Computed schema fields do not expose ``today``, so patch the aliases at
    their point of use instead of changing production logic or the fixture.
    """
    frozen_today = date(2026, 9, 18)
    monkeypatch.setattr(
        license_schemas,
        "_derive_license_status",
        lambda expires_at, today=frozen_today: derive_license_status(expires_at, today),
    )
    monkeypatch.setattr(
        license_schemas,
        "_days_to_expiry",
        lambda expires_at, today=frozen_today: days_to_expiry(expires_at, today),
    )
    payload = _load("university-passport.json")
    passport = UniversityPassport.model_validate(payload)
    statuses = {lic.status.value for lic in passport.licenses}
    assert "expires_soon" in statuses, statuses
    soon = [lic for lic in passport.licenses if lic.status.value == "expires_soon"]
    assert all(0 <= lic.days_to_expiry <= 30 for lic in soon)


def test_license_status_expired_with_controlled_today():
    frozen_today = date(2026, 9, 18)
    expires_at = date(2026, 9, 17)
    assert derive_license_status(expires_at, frozen_today) == "expired"
    assert days_to_expiry(expires_at, frozen_today) == -1


def test_teacher_passport_valid_with_reasons():
    payload = _load("teacher-passport.json")
    passport = TeacherPassport.model_validate(payload)
    assert passport.readiness.value == "attention"
    assert passport.readiness_reasons, "attention passport must explain why"
    assert passport.next_qualification_date is not None
    assert len(passport.certificates) >= 1
    assert any(c.is_mandatory for c in passport.certificates)

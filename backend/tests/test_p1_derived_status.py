"""P1-06-02: derived license/contract status — schema-level tests.

Model ``@property``s are covered in ``test_p1_schema.py``; here we verify
the shared service helpers and the Pydantic ``computed_field``s
(``LicenseShort``/``ContractShort``) including OpenAPI exposure.
"""

import uuid
from datetime import date, timedelta

from app.models.catalog import Contract, License
from app.schemas import ContractShort, LicenseShort
from app.services.license_status import (
    days_to_expiry,
    derive_contract_status,
    derive_license_status,
)


def _lic(expires_delta: int | None) -> LicenseShort:
    lic = License(
        id=uuid.uuid4(),
        university_id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        license_number="L-1",
        signed_at=date.today() - timedelta(days=300),
        expires_at=None
        if expires_delta is None
        else date.today() + timedelta(days=expires_delta),
    )
    return LicenseShort.model_validate(lic)


def test_license_status_matrix():
    assert _lic(-5).status.value == "expired"
    assert _lic(5).status.value == "expires_soon"
    assert _lic(30).status.value == "expires_soon"
    assert _lic(31).status.value == "active"
    assert _lic(400).status.value == "active"
    assert _lic(None).status.value == "active"


def test_license_days_to_expiry():
    assert _lic(5).days_to_expiry == 5
    assert _lic(-3).days_to_expiry == -3
    assert _lic(None).days_to_expiry is None


def test_contract_terminal_raw_wins():
    for raw, expected in [
        ("terminated", "terminated"),
        ("draft", "draft"),
        ("signed", "active"),
    ]:
        c = Contract(
            id=uuid.uuid4(),
            university_id=uuid.uuid4(),
            contract_number=f"D-{raw}",
            signed_at=date.today(),
            expires_at=None,
            status_raw=raw,
        )
        short = ContractShort.model_validate(c)
        assert short.status.value == expected, (raw, short.status)
        assert short.days_to_expiry is None


def test_contract_expiry_matrix():
    # NOTE: ContractStatus has no expires_soon (P1-02-04) — the warning
    # window maps to active, days_to_expiry still exposes the detail.
    for delta, expected in [(-1, "expired"), (10, "active"), (90, "active")]:
        c = Contract(
            id=uuid.uuid4(),
            university_id=uuid.uuid4(),
            contract_number=f"D-{delta}",
            signed_at=date.today() - timedelta(days=100),
            expires_at=date.today() + timedelta(days=delta),
            status_raw="signed",
        )
        short = ContractShort.model_validate(c)
        assert short.status.value == expected, (delta, short.status)
        assert short.days_to_expiry == delta


def test_service_helpers_match_models():
    today = date.today()
    assert derive_license_status(None) == "active"
    assert derive_license_status(today + timedelta(days=400)) == "active"
    assert derive_license_status(today - timedelta(days=1)) == "expired"
    assert derive_contract_status("terminated", None) == "terminated"
    assert derive_contract_status("draft", today - timedelta(days=99)) == "draft"
    assert derive_contract_status("signed", None) == "active"
    assert days_to_expiry(None) is None
    assert days_to_expiry(today + timedelta(days=7), today) == 7


def test_status_in_openapi():
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/l", response_model=LicenseShort)
    @app.get("/c", response_model=ContractShort)
    def _(): ...

    schemas = app.openapi()["components"]["schemas"]
    # computed fields are serialized read-only properties
    for name in ("LicenseShort", "ContractShort"):
        props = schemas[name]["properties"]
        assert "status" in props and "days_to_expiry" in props, (name, props)
        assert "status" in schemas[name].get("required", []), name

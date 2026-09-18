"""Derived license/contract status computation (P1-06-02).

Pure functions, no side effects — single source of truth shared by:
* ORM ``@property``s (``License.derived_status``, ``Contract.derived_status``),
* Pydantic ``computed_field``s (``app.schemas.licenses``),
* Health Score component D (P2-07-03 imports from here).

Rules:
* ``status`` is NEVER stored for the derived part — computed on the fly.
* ``expires_at is None`` → ``active`` (open-ended license/contract).
* ``days_left < 0`` → ``expired``.
* ``days_left <= EXPIRY_WARNING_DAYS`` (30) → ``expires_soon``.
* Contracts keep their explicit terminal/raw states: ``terminated`` and
  ``draft`` are returned as-is without looking at dates.
"""

from __future__ import annotations

from datetime import date

from app.models.enums import EXPIRY_WARNING_DAYS


def days_to_expiry(expires_at: date | None, today: date | None = None) -> int | None:
    """``(expires_at - today).days``; ``None`` when there is no expiry date."""
    if expires_at is None:
        return None
    return (expires_at - (today or date.today())).days


def derive_license_status(expires_at: date | None, today: date | None = None) -> str:
    """License derived status: ``active`` / ``expires_soon`` / ``expired``."""
    days_left = days_to_expiry(expires_at, today)
    if days_left is None:
        return "active"
    if days_left < 0:
        return "expired"
    if days_left <= EXPIRY_WARNING_DAYS:
        return "expires_soon"
    return "active"


def derive_contract_status(
    status_raw: str, expires_at: date | None, today: date | None = None
) -> str:
    """Contract status: explicit ``terminated``/``draft`` win; otherwise the
    same date logic as licenses, mapped onto the contract value set.

    NOTE: the frozen API enum (P1-02-04 ``ContractStatus``) has no
    ``expires_soon`` member, so the warning window maps to ``active``
    (P1-06-02: "если есть такой статус, иначе ACTIVE"). The detailed
    ``days_to_expiry`` field still lets the UI highlight expiring contracts.
    """
    if status_raw == "terminated":
        return "terminated"
    if status_raw == "draft":
        return "draft"
    days_left = days_to_expiry(expires_at, today)
    if days_left is None:
        return "active"
    if days_left < 0:
        return "expired"
    return "active"


__all__ = [
    "days_to_expiry",
    "derive_contract_status",
    "derive_license_status",
]

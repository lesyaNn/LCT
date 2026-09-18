"""Deterministic teacher readiness computation (P1-05-03).

Pure function, no side effects — shared by the teacher passport endpoint
(P1-05-01) and the Health Score E component (P2-07-05 imports from here).

Rules:
* collect mandatory certificates + qualifications with ``expires_at``;
* ``expires_at < today`` → EXPIRED;
* ``expires_at <= today + 30 days`` → ATTENTION;
* any EXPIRED → overall EXPIRED; else any ATTENTION → ATTENTION; else READY.
* non-mandatory certificates and entries without ``expires_at`` never affect
  the status; a teacher with no mandatory items is READY.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models.enums import EXPIRY_WARNING_DAYS, TeacherReadiness


class _Expirable(Protocol):
    expires_at: date | None
    is_mandatory: bool


@dataclass
class TeacherReadinessResult:
    readiness: TeacherReadiness
    reasons: list[str] = field(default_factory=list)
    next_qualification_date: date | None = None


def _display_name(item: object, fallback: str = "без названия") -> str:
    for attr in ("certificate_name", "qualification_name", "name"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return fallback


def compute_teacher_readiness(
    certificates: list[object] | None = None,
    qualifications: list[object] | None = None,
    today: date | None = None,
) -> TeacherReadinessResult:
    """Compute readiness from certificate/qualification ORM objects or dicts."""
    today = today or date.today()
    reasons: list[str] = []
    expired = False
    expiring_soon = False
    next_qual: date | None = None

    def _norm(items: list[object] | None, kind: str) -> list[tuple[str, bool, date | None]]:
        normed: list[tuple[str, bool, date | None]] = []
        for item in items or []:
            if isinstance(item, dict):
                name = str(
                    item.get("certificate_name")
                    or item.get("qualification_name")
                    or item.get("name")
                    or "без названия"
                )
                mandatory = bool(item.get("is_mandatory", kind == "qual"))
                expires = item.get("expires_at")
            else:
                name = _display_name(item)
                mandatory = bool(getattr(item, "is_mandatory", kind == "qual"))
                expires = getattr(item, "expires_at", None)
            normed.append((name, mandatory, expires))
        return normed

    entries = _norm(certificates, "cert") + _norm(qualifications, "qual")

    for name, mandatory, expires in entries:
        if not mandatory or expires is None:
            continue
        if next_qual is None or expires < next_qual:
            next_qual = expires
        delta = (expires - today).days
        if delta < 0:
            expired = True
            reasons.append(f"Истёк обязательный сертификат/квалификация: {name} ({expires})")
        elif delta <= EXPIRY_WARNING_DAYS:
            expiring_soon = True
            reasons.append(f"Скоро истекает сертификат/квалификация: {name} ({expires})")

    if expired:
        return TeacherReadinessResult(
            readiness=TeacherReadiness.EXPIRED, reasons=reasons,
            next_qualification_date=next_qual,
        )
    if expiring_soon:
        return TeacherReadinessResult(
            readiness=TeacherReadiness.ATTENTION, reasons=reasons,
            next_qualification_date=next_qual,
        )
    return TeacherReadinessResult(
        readiness=TeacherReadiness.READY,
        reasons=["Все обязательные сертификаты и квалификации актуальны"],
        next_qualification_date=next_qual,
    )

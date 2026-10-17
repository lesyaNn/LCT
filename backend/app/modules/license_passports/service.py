"""Current DB values only; no workflow dependency and no persisted PDF snapshot."""

from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BusinessException
from app.core.policies import ensure_university_visible
from app.core.security import CurrentUser
from app.models.catalog import Contract, ITProduct, License, University, Vendor
from app.modules.license_passports.schemas import LicensePassport, LicenseVerification
from app.schemas.errors import ErrorCode
from app.services.license_status import derive_contract_status, derive_license_status


def _license_row(db: Session, license_id: UUID):
    # Column projection avoids loading contacts, comments or selectin collections.
    return db.execute(
        select(
            License.id, License.university_id, License.product_id,
            License.license_number, License.signed_at, License.expires_at,
            University.name.label("university_name"), ITProduct.name.label("product_name"),
            Vendor.name.label("vendor_name"), Contract.id.label("contract_id"),
            Contract.contract_number, Contract.signed_at.label("contract_signed_at"),
            Contract.expires_at.label("contract_expires_at"), Contract.status_raw,
            Contract.university_id.label("contract_university_id"),
            Contract.product_id.label("contract_product_id"),
        )
        .outerjoin(University, University.id == License.university_id)
        .outerjoin(ITProduct, ITProduct.id == License.product_id)
        .outerjoin(Vendor, Vendor.id == ITProduct.vendor_id)
        .outerjoin(Contract, Contract.id == License.contract_id)
        .where(License.id == license_id)
    ).mappings().one_or_none()


def missing_fields(row) -> list[str]:
    labels = {
        "university_name": "Полное наименование вуза",
        "product_name": "Наименование программного обеспечения",
        "license_number": "Номер лицензии",
        "contract_number": "Связанный договор и его номер",
        "contract_signed_at": "Дата заключения договора",
        "signed_at": "Дата начала действия лицензии",
        "expires_at": "Дата окончания действия лицензии",
    }
    missing = [label for key, label in labels.items()
               if row[key] is None or (isinstance(row[key], str) and not row[key].strip())]
    if row["id"].version != 4:
        missing.append("Случайный UUID v4 лицензии для публичной проверки")
    if row["signed_at"] and row["expires_at"] and row["signed_at"] > row["expires_at"]:
        missing.append("Срок действия лицензии: дата окончания раньше даты начала")
    if row["contract_id"]:
        if row["contract_university_id"] != row["university_id"]:
            missing.append("Договор должен принадлежать тому же вузу")
        if row["contract_product_id"] not in (None, row["product_id"]):
            missing.append("Договор должен относиться к выбранному ПО")
    return missing


def verification_status(row, today: date) -> tuple[str, str, str]:
    # There is no independent revocation field in the current domain model.
    # A terminated parent contract is the existing authoritative terminal state.
    if row["status_raw"] == "terminated":
        return "revoked", "Лицензия недействительна", "Договор прекращён."
    if missing_fields(row):
        return "invalid", "Лицензия не подтверждена", "Данные лицензии неполны или противоречивы."
    contract_status = derive_contract_status(row["status_raw"], row["contract_expires_at"], today)
    if contract_status == "draft":
        return "invalid", "Лицензия недействительна", "Договор находится в статусе черновика."
    if row["status_raw"] != "signed":
        return "invalid", "Лицензия не подтверждена", "Договор не имеет подтверждённого статуса."
    license_status = derive_license_status(row["expires_at"], today)
    if license_status == "expired" or contract_status == "expired":
        return "expired", "Срок действия истёк", "Истёк срок действия лицензии или её договора."
    if row["signed_at"] > today or row["contract_signed_at"] > today:
        return "invalid", "Лицензия ещё не действует", "Дата начала действия ещё не наступила."
    reason = "Сведения подтверждены текущими данными CRM."
    if license_status == "expires_soon":
        reason += " Срок действия лицензии скоро истекает."
    return "confirmed", "Лицензия подтверждена", reason


def build_passport(db: Session, university_id: UUID, license_id: UUID,
                   user: CurrentUser) -> LicensePassport:
    ensure_university_visible(university_id, user)
    row = _license_row(db, license_id)
    if row is None or row["university_id"] != university_id:
        raise BusinessException(ErrorCode.NOT_FOUND)
    missing = missing_fields(row)
    if missing:
        raise BusinessException(ErrorCode.VALIDATION_ERROR, details={"missing_fields": missing})
    origin = settings.frontend_origin.rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.netloc
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path):
        raise BusinessException(ErrorCode.REPORT_FAILED)
    now = datetime.now(UTC)
    _, label, reason = verification_status(row, now.date())
    return LicensePassport(
        license_id=license_id, university_id=university_id,
        passport_number=f"LP-{license_id}",
        university_name=row["university_name"], product_name=row["product_name"],
        vendor_name=row["vendor_name"], license_number=row["license_number"],
        contract_number=row["contract_number"], contract_signed_at=row["contract_signed_at"],
        signed_at=row["signed_at"], expires_at=row["expires_at"],
        status_label=label, status_reason=reason, generated_at=now,
        verification_url=f"{origin}/verify/license/{license_id}",
    )


def verify_license(db: Session, license_id: UUID) -> LicenseVerification:
    now = datetime.now(UTC)
    # UUIDPKMixin creates UUID v4: 122 random bits, no sequential identifiers.
    row = _license_row(db, license_id) if license_id.version == 4 else None
    if row is None:
        return LicenseVerification(status="invalid", status_label="Лицензия не найдена",
                                   reason="Проверьте ссылку или обратитесь к выдавшей документ организации.",
                                   checked_at=now)
    status, label, reason = verification_status(row, now.date())
    return LicenseVerification(
        status=status, status_label=label, reason=reason, checked_at=now,
        university_name=row["university_name"], product_name=row["product_name"],
        license_number=row["license_number"], contract_number=row["contract_number"],
        signed_at=row["signed_at"], expires_at=row["expires_at"],
    )

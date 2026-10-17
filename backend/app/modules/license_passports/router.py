import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.license_passports import service
from app.modules.license_passports.pdf import generate_passport_pdf
from app.modules.license_passports.schemas import LicenseVerification
from app.schemas.errors import ErrorCode

router = APIRouter(tags=["Licenses"])
READ = require_permission("university.read")
logger = logging.getLogger(__name__)


@router.get(
    "/universities/{university_id}/licenses/{license_id}/passport.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Паспорт лицензии A4"}},
    summary="Сформировать паспорт лицензии",
    description="Актуальные серверные данные, право university.read и доступ к вузу. Этап Workflow не ограничивает генерацию.",
)
def download_passport(university_id: UUID, license_id: UUID,
                      db: Session = Depends(get_db), user: CurrentUser = Depends(READ)):
    passport = service.build_passport(db, university_id, license_id, user)
    try:
        content = generate_passport_pdf(passport)
    except Exception as exc:
        logger.error("license_passport_pdf_failed error_type=%s", type(exc).__name__)
        raise BusinessException(ErrorCode.REPORT_FAILED) from exc
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="license-passport-{license_id}.pdf"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.get(
    "/public/licenses/{license_id}/verification", response_model=LicenseVerification,
    summary="Публичная проверка лицензии по случайному UUID",
    description="Только вуз, ПО, номера, срок и текущий статус. Без контактов, файлов и пользовательских идентификаторов.",
)
def verify_license(license_id: UUID, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return service.verify_license(db, license_id)

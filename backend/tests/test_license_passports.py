"""Real SQL projection + HTTP/RBAC + embedded text/A4 checks; no workflow needed."""

import io
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.catalog import Contract, ITProduct, License, University, Vendor
from app.modules.license_passports import router as routes
from app.modules.license_passports import service
from app.modules.license_passports.pdf import generate_passport_pdf
from app.modules.license_passports.schemas import LicensePassport


@pytest.fixture()
def context():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    # Only catalog columns, no unrelated PostgreSQL-only tables. Deliberately
    # allow NULL for legacy/incomplete-row validation tests.
    metadata = MetaData()
    tables = {model.__tablename__: Table(model.__tablename__, metadata, *[
        Column(c.name, c.type, primary_key=c.primary_key) for c in model.__table__.columns
    ]) for model in (University, Vendor, ITProduct, Contract, License)}
    metadata.create_all(engine)
    university_id, product_id, vendor_id, contract_id, license_id = [uuid4() for _ in range(5)]
    today = datetime.now(UTC).date()
    db = Session(engine)
    db.execute(tables["universities"].insert().values(id=university_id, name="Технический университет"))
    db.execute(tables["vendors"].insert().values(id=vendor_id, name="Разработчик ПО"))
    db.execute(tables["it_products"].insert().values(id=product_id, vendor_id=vendor_id, name="Образовательная платформа"))
    db.execute(tables["contracts"].insert().values(
        id=contract_id, university_id=university_id, product_id=product_id,
        contract_number="Д-2026/107", signed_at=today - timedelta(days=40), status_raw="signed"))
    db.execute(tables["licenses"].insert().values(
        id=license_id, university_id=university_id, product_id=product_id, contract_id=contract_id,
        license_number="Л-2026/205", signed_at=today - timedelta(days=30),
        expires_at=today + timedelta(days=60), comment="PRIVATE COMMENT"))
    db.commit()
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(routes.router, prefix="/api/v1")
    actor = CurrentUser(id="private-user-id", roles={"user"}, university_ids=(str(university_id),))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    with TestClient(app) as client:
        yield db, client, actor, tables, university_id, license_id, contract_id, app
    db.close()
    engine.dispose()


def pdf_url(university_id, license_id):
    return f"/api/v1/universities/{university_id}/licenses/{license_id}/passport.pdf"


def public_url(license_id):
    return f"/api/v1/public/licenses/{license_id}/verification"


def test_generation_works_without_any_workflow_and_is_current(context):
    db, client, _, tables, uid, lid, _, _ = context
    first = client.get(pdf_url(uid, lid))
    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert first.headers["cache-control"] == "no-store"
    assert "Технический университет" in PdfReader(io.BytesIO(first.content)).pages[0].extract_text()
    db.execute(tables["universities"].update().values(name="Новое название университета"))
    db.commit()
    second = client.get(pdf_url(uid, lid))
    text = PdfReader(io.BytesIO(second.content)).pages[0].extract_text()
    assert "Новое название университета" in text
    assert "Технический университет" not in text
    assert "PRIVATE COMMENT" not in text
    assert "private-user-id" not in text
    assert f"LP-{lid}" in text


def test_auth_scope_and_mismatched_university(context):
    _, client, actor, _, uid, lid, _, app = context
    assert client.get(pdf_url(uid, uuid4())).status_code == 404
    assert client.get(pdf_url(uuid4(), lid)).status_code == 404
    actor.university_ids = ()
    assert client.get(pdf_url(uid, lid)).status_code == 404
    actor.roles = {"unknown"}
    assert client.get(pdf_url(uid, lid)).status_code == 403
    del app.dependency_overrides[get_current_user]
    assert client.get(pdf_url(uid, lid)).status_code == 401
    assert client.get(public_url(lid)).status_code == 200


def test_missing_and_inconsistent_fields_are_named(context):
    db, client, _, tables, uid, lid, _, _ = context
    db.execute(tables["licenses"].update().values(contract_id=None, signed_at=None, license_number=" "))
    db.commit()
    response = client.get(pdf_url(uid, lid))
    assert response.status_code == 422
    fields = response.json()["error"]["details"]["missing_fields"]
    assert {"Номер лицензии", "Связанный договор и его номер", "Дата начала действия лицензии"} <= set(fields)
    assert client.get(public_url(lid)).json()["status"] == "invalid"


@pytest.mark.parametrize("values,expected", [
    ({"status_raw": "terminated"}, "revoked"),
    ({"status_raw": "draft"}, "invalid"),
    ({"status_raw": "unexpected"}, "invalid"),
    ({"expires_at": date(2000, 1, 1)}, "expired"),
    ({"signed_at": date(2100, 1, 1)}, "invalid"),
])
def test_public_status_reads_contract_changes(context, values, expected):
    db, client, _, tables, _, lid, _, _ = context
    first = client.get(public_url(lid))
    assert first.json()["status"] == "confirmed"
    db.execute(tables["contracts"].update().values(**values))
    db.commit()
    result = client.get(public_url(lid))
    assert result.json()["status"] == expected
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert set(result.json()) == {
        "status", "status_label", "reason", "checked_at", "university_name", "product_name",
        "license_number", "contract_number", "signed_at", "expires_at",
    }


def test_license_dates_unknown_and_deleted(context):
    db, client, _, tables, _, lid, _, _ = context
    today = datetime.now(UTC).date()
    db.execute(tables["licenses"].update().values(expires_at=today))
    db.commit()
    assert client.get(public_url(lid)).json()["status"] == "confirmed"
    db.execute(tables["licenses"].update().values(expires_at=today - timedelta(days=1)))
    db.commit()
    assert client.get(public_url(lid)).json()["status"] == "expired"
    db.execute(tables["licenses"].delete())
    db.commit()
    for unknown in (lid, uuid4(), UUID(int=1)):
        data = client.get(public_url(unknown)).json()
        assert data["status"] == "invalid"
        assert data["university_name"] is None


def test_wrong_contract_or_reversed_dates_rejected(context):
    db, client, _, tables, uid, lid, _, _ = context
    db.execute(tables["contracts"].update().values(university_id=uuid4(), product_id=uuid4()))
    db.execute(tables["licenses"].update().values(expires_at=date(2000, 1, 1)))
    db.commit()
    response = client.get(pdf_url(uid, lid))
    assert response.status_code == 422
    assert len(response.json()["error"]["details"]["missing_fields"]) == 3


def test_render_failure_has_safe_error(context, monkeypatch):
    _, client, _, _, uid, lid, _, _ = context
    def fail(_):
        raise RuntimeError("sensitive path and text")
    monkeypatch.setattr(routes, "generate_passport_pdf", fail)
    response = client.get(pdf_url(uid, lid))
    assert response.status_code >= 400
    assert response.json()["error"]["code"] == "REPORT_FAILED"
    assert "sensitive" not in response.text


def sample_passport(long=False):
    """Synthetic input for visual/layout QA only, never a production fallback."""
    lid = UUID("149b29fb-c710-446a-9b3c-e8dbdc6c3a2a")
    return LicensePassport(
        license_id=lid, university_id=uuid4(), passport_number=f"LP-{lid}",
        university_name=(("Федеральный государственный технический университет " * 11)[:512]
                         if long else "Санкт-Петербургский государственный университет телекоммуникаций им. проф. М. А. Бонч-Бруевича"),
        product_name=(("Программный комплекс для образовательных организаций " * 11)[:512]
                      if long else "Платформа виртуальных лабораторий"),
        vendor_name="Ростелеком", license_number="ЛЦ-2026-0017" if not long else "Л" * 256,
        contract_number="РТК-2026/107" if not long else "Д" * 256,
        contract_signed_at=date(2026, 9, 1), signed_at=date(2026, 9, 15), expires_at=date(2027, 9, 14),
        status_label="Лицензия подтверждена", status_reason="Сведения подтверждены текущими данными CRM.",
        generated_at=datetime(2026, 10, 17, 12, 30, tzinfo=UTC),
        verification_url=f"https://crm.example.org/verify/license/{lid}",
    )


@pytest.mark.parametrize("long", [False, True])
def test_pdf_a4_embedded_cyrillic_full_text_and_verification_link(long):
    data = sample_passport(long)
    pdf = PdfReader(io.BytesIO(generate_passport_pdf(data)))
    assert len(pdf.pages) == (2 if long else 1)
    page = pdf.pages[0]
    assert float(page.mediabox.width) == pytest.approx(595.28, abs=.1)
    assert float(page.mediabox.height) == pytest.approx(841.89, abs=.1)
    text = "".join("".join(p.extract_text().split()) for p in pdf.pages)
    for expected in (data.university_name, data.product_name, data.license_number, data.contract_number):
        assert "".join(expected.split()) in text
    assert "ПАСПОРТЛИЦЕНЗИИ" in text
    assert "Проверка:" in text
    assert data.verification_url in text
    for certificate_page in pdf.pages:
        links = [a.get_object()["/A"]["/URI"] for a in certificate_page["/Annots"]]
        assert links.count(data.verification_url) >= 2  # QR and visible clickable URL
    assert page["/Annots"][0].get_object()["/A"]["/URI"] == data.verification_url
    assert any("/FontFile2" in font.get_object().get("/FontDescriptor", {})
               for font in page["/Resources"]["/Font"].values())


def test_generation_uses_configured_origin_not_request_host(context, monkeypatch):
    db, _, actor, _, uid, lid, _, _ = context
    monkeypatch.setattr(service.settings, "frontend_origin", "https://crm.example.org")
    assert service.build_passport(db, uid, lid, actor).verification_url == f"https://crm.example.org/verify/license/{lid}"

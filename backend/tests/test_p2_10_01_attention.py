"""P2-10-01: attention rules — тесты всех 5 правил (SQLite)."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.db.base import Base
from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    University,
    Vendor,
)
from app.models.interactions import Document, UniversityProgram
from app.models.teachers import Teacher, TeacherCertificate
from app.models.workflow import (
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTemplate,
    WorkflowTemplateStage,
)
from app.modules.health_score.attention import get_attention_items

TODAY = date(2026, 9, 20)
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _mem_session() -> Session:
    eng = create_engine("sqlite:///:memory:")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return Session(eng)


def _uni(db: Session, name="Вуз A-1") -> University:
    uni = University(id=uuid4(), name=name)
    db.add(uni)
    db.flush()
    return uni


def test_empty_university_no_items():
    db = _mem_session()
    uni = _uni(db)
    db.commit()
    assert get_attention_items(db, uni.id, TODAY) == []
    db.close()


def test_overdue_stage_and_expired_document():
    db = _mem_session()
    uni = _uni(db)
    template = WorkflowTemplate(id=uuid4(), code="A-1", name="Ш", created_by_keycloak_sub="t")
    db.add(template)
    db.flush()
    tpl_stage = WorkflowTemplateStage(
        id=uuid4(), template_id=template.id, code="s1", name="Подписание", order_index=0)
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni.id,
        status="active", started_at=NOW - timedelta(days=30),
        created_by_keycloak_sub="t", updated_by_keycloak_sub="t")
    db.add(instance)
    db.flush()
    db.add(WorkflowInstanceStage(
        id=uuid4(), instance_id=instance.id, template_stage_id=tpl_stage.id,
        order_index=0, status="current", due_date=NOW - timedelta(days=5)))
    db.add(Document(
        id=uuid4(), university_id=uni.id, document_type="contract",
        title="Договор", file_path="/f", file_name="d.pdf",
        status_raw="signed", expires_at=TODAY - timedelta(days=2),
        uploaded_by_keycloak_sub="t"))
    db.commit()
    items = get_attention_items(db, uni.id, TODAY)
    codes = [i.code for i in items]
    assert codes == ["OVERDUE_STAGE", "EXPIRED_DOCUMENT"]  # high first
    assert "просрочен на 5 дн" in items[0].description
    db.close()


def test_expiring_license_and_certificate_and_launch():
    db = _mem_session()
    uni = _uni(db)
    direction = ITDirection(id=uuid4(), code="A-1", name="Направление")
    vendor = Vendor(id=uuid4(), name="Вендор")
    product = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Продукт")
    program = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа")
    db.add_all([direction, vendor, product, program])
    db.flush()
    db.add(License(
        id=uuid4(), university_id=uni.id, product_id=product.id,
        license_number="L-1", signed_at=TODAY - timedelta(days=300),
        expires_at=TODAY + timedelta(days=15)))
    teacher = Teacher(id=uuid4(), university_id=uni.id, full_name="Петров",
                      email=f"p-{uuid4()}@x.local")
    db.add(teacher)
    db.flush()
    db.add(TeacherCertificate(
        id=uuid4(), teacher_id=teacher.id, certificate_name="Обязательный",
        issued_at=TODAY - timedelta(days=100),
        expires_at=TODAY + timedelta(days=10), is_mandatory=True))
    db.add(UniversityProgram(
        id=uuid4(), university_id=uni.id, program_id=program.id,
        status="active", launch_date=TODAY + timedelta(days=7)))
    db.commit()
    items = get_attention_items(db, uni.id, TODAY)
    codes = sorted(i.code for i in items)
    assert codes == ["EXPIRING_CERTIFICATE", "EXPIRING_LICENSE", "LAUNCH_AT_RISK"]
    assert all(i.severity == "medium" for i in items)
    db.close()


def test_far_future_license_ignored_and_limit():
    db = _mem_session()
    uni = _uni(db)
    vendor = Vendor(id=uuid4(), name="Вендор-2")
    product = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Продукт-2")
    db.add_all([vendor, product])
    db.flush()
    db.add(License(
        id=uuid4(), university_id=uni.id, product_id=product.id,
        license_number="L-9", signed_at=TODAY - timedelta(days=10),
        expires_at=TODAY + timedelta(days=200)))
    db.commit()
    assert get_attention_items(db, uni.id, TODAY) == []
    db.close()

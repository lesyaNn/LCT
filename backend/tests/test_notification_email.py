"""Email is a delivery channel of the existing notification service."""

import os
import smtplib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import Settings, settings
from app.models.catalog import Responsible, University
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.modules.notifications import email, service
from app.modules.notifications.address import outbound_email


@pytest.fixture()
def database():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def _publish(db, sub="user-a", kind="assignment", target="university", university_id=None):
    return service.publish(
        db, recipient_user_id=sub, event_key=f"{kind}:{uuid.uuid4()}",
        type=kind, priority="INFO", title="Назначена работа",
        message="Уведомление о работе с университетом", entity_type=target,
        entity_id=uuid.uuid4(), university_id=university_id,
    )


def test_email_content_and_targets(monkeypatch):
    monkeypatch.setattr(settings, "frontend_origin", "https://crm.example.test")
    uni = uuid.uuid4()
    for target, suffix in (
        ("contract", f"/universities/{uni}?tab=documents"),
        ("license", f"/universities/{uni}?tab=licenses"),
        ("workflow", "/workflows/"),
        ("import_job", "/admin/import?job="),
        ("university", "/universities/"),
    ):
        row = Notification(
            recipient_user_id="user-a", event_key="test", type="assignment", priority="INFO",
            title="Назначение", message="Русский текст", entity_type=target,
            entity_id=str(uuid.uuid4()), university_id=uni,
        )
        subject, body = email.render_message(row)
        assert subject == "Назначение"
        assert "Русский текст" in body
        assert f"https://crm.example.test{suffix}" in body
        assert "JWT" not in body


def test_smtp_error_is_categorized_without_raw_response():
    secret = b"password=secret-token"
    category, permanent = email._error_category(smtplib.SMTPResponseException(550, secret))
    assert (category, permanent) == ("smtp_permanent", True)
    assert "secret" not in category
    assert email._error_category(TimeoutError(secret.decode())) == ("timeout", False)
    assert email._error_category(smtplib.SMTPResponseException(451, secret)) == ("smtp_temporary", False)


@pytest.mark.parametrize("address", ["user@example.test", "first.last+tag@example.test"])
def test_outbound_accepts_one_mailbox(address):
    assert outbound_email(address) == address


@pytest.mark.parametrize("address", [
    "first,second@example.test", "bad-address", "", "user@example.test\r\nBcc:other@example.test",
])
def test_outbound_rejects_invalid_mailbox(address):
    with pytest.raises(ValueError):
        outbound_email(address)


def test_sender_settings_validation():
    assert Settings(_env_file=None, email_notifications_enabled=True,
                    smtp_host="smtp.example.test", smtp_from_email="sender@example.test").smtp_from_email == "sender@example.test"
    for address in ("bad-address", "first,second@example.test"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, email_notifications_enabled=True,
                     smtp_host="smtp.example.test", smtp_from_email=address)
    assert not Settings(_env_file=None, email_notifications_enabled=False,
                        smtp_host="", smtp_from_email="").smtp_from_email


def test_heartbeat_retries_db_error_then_stops_on_lost_owner(monkeypatch):
    attempts = []
    monkeypatch.setattr(email, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    def renew(*_):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("temporary database outage")
        return False

    monkeypatch.setattr(email, "_renew_lease", renew)
    stop = threading.Event()
    worker = threading.Thread(target=email._heartbeat,
                              args=(None, uuid.uuid4(), uuid.uuid4(), stop))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert len(attempts) == 2


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_smtp_uses_verified_tls_without_network(monkeypatch, security):
    events = []
    context = object()
    monkeypatch.setattr(settings, "smtp_security", security)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "crm@example.test")
    monkeypatch.setattr(email.ssl, "create_default_context", lambda: context)

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            events.append((host, port, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def starttls(self, *, context):
            events.append(("starttls", context))

        def send_message(self, message):
            events.append(("send", message["To"], message.get_content()))

    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", FakeSMTP)
    email.send_email("user@example.test", "Назначение", "Русский текст")
    assert events[-1] == ("send", "user@example.test", "Русский текст\n")
    if security == "starttls":
        assert ("starttls", context) in events
    else:
        assert events[0][2]["context"] is context


def test_publish_enqueues_once_and_skips_missing_email(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    uni = University(name="Тестовый вуз", city="Москва")
    db.add(uni)
    db.flush()
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert service.publish(db, recipient_user_id="user-a", event_key="assignment:one",
                           type="assignment", priority="INFO", title="Назначение",
                           message="Работа назначена", entity_type="university",
                           entity_id=uni.id, university_id=uni.id)
    assert not service.publish(db, recipient_user_id="user-a", event_key="assignment:one",
                               type="assignment", priority="INFO", title="Назначение",
                               message="Работа назначена", entity_type="university",
                               entity_id=uni.id, university_id=uni.id)
    assert _publish(db, sub="unlinked", university_id=uni.id)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 2
    deliveries = db.scalars(select(NotificationDelivery)).all()
    assert len(deliveries) == 1
    assert deliveries[0].recipient == "user@example.test"


@pytest.mark.parametrize("outcome,expected", [
    (None, "sent"), (TimeoutError("raw secret"), "pending"),
    (smtplib.SMTPResponseException(550, b"raw secret"), "failed"),
])
def test_worker_delivery_outcomes(database, monkeypatch, outcome, expected):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert _publish(db)
    db.commit()
    captured = []

    def sender(recipient, subject, body):
        captured.append((recipient, subject, body))
        if outcome:
            raise outcome

    assert email.run_email_delivery_once(db, sender=sender)
    row = db.scalar(select(NotificationDelivery))
    assert row.status == expected
    assert row.attempts == 1
    assert captured[0][0] == "user@example.test"
    if expected == "sent":
        assert row.sent_at is not None
    else:
        assert "secret" not in (row.last_error or "")
    assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_assignment_and_import_use_same_channel(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    university = University(name="Тестовый вуз", city="Москва")
    responsible = Responsible(full_name="Ответственный", email="user@example.test",
                              role="manager", keycloak_sub="user-a")
    db.add_all([university, responsible])
    db.flush()
    assert service.notify_assignment(db, responsible.id, university.id,
                                     event_key="assignment:email-test")
    job = SimpleNamespace(id=uuid.uuid4(), actor_sub="user-a",
                          result={"errors_total": 2, "total_rows": 3, "inserted": 1})
    assert service.notify_import_result(db, job)
    db.commit()
    rows = db.scalars(select(NotificationDelivery)).all()
    assert len(rows) == 2
    assert {db.get(Notification, row.notification_id).type for row in rows} == {
        "assignment", "import_error",
    }


def test_invalid_local_address_keeps_in_app(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    db.add(Responsible(full_name="Ответственный", email="invalid-address",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert _publish(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 1
    assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 0


@pytest.mark.parametrize("mode,expected", [
    ("repair", 1), ("existing", 1), ("disabled", 0), ("missing_recipient", 0),
    ("invalid_recipient", 0),
])
def test_duplicate_event_repairs_only_missing_eligible_delivery(database, monkeypatch, mode, expected):
    db = database
    monkeypatch.setattr(settings, "email_notifications_enabled", mode == "existing")
    if mode != "missing_recipient":
        address = "first,second@example.test" if mode == "invalid_recipient" else "user@example.test"
        db.add(Responsible(full_name="Ответственный", email=address,
                           role="manager", keycloak_sub="user-a"))
        db.flush()
    event = dict(recipient_user_id="user-a", event_key="assignment:repair",
                 type="assignment", priority="INFO", title="Original", message="Original",
                 entity_type="university", entity_id=uuid.uuid4())
    assert service.publish(db, **event)
    db.commit()
    monkeypatch.setattr(settings, "email_notifications_enabled", mode != "disabled")
    assert not service.publish(db, **{**event, "title": "Changed", "message": "Changed"})
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 1
    assert db.scalar(select(Notification.title)) == "Original"
    assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == expected
    if expected:
        assert not service.publish(db, **event)
        db.commit()
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 1


def test_disabled_and_max_attempts(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert _publish(db)
    db.commit()
    monkeypatch.setattr(settings, "email_notifications_enabled", False)
    assert not email.run_email_delivery_once(db, sender=lambda *_: pytest.fail("SMTP called"))
    assert db.scalar(select(NotificationDelivery.status)) == "pending"
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    monkeypatch.setattr(settings, "email_max_attempts", 5)
    row = db.scalar(select(NotificationDelivery))
    row.attempts = 4
    row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert email.run_email_delivery_once(db, sender=lambda *_: (_ for _ in ()).throw(TimeoutError()))
    db.refresh(row)
    assert (row.status, row.attempts) == ("failed", 5)
    assert not email.run_email_delivery_once(db, sender=lambda *_: pytest.fail("sixth SMTP attempt"))


@pytest.mark.parametrize("prior_attempts,delay_seconds", [
    (0, 60), (1, 300), (2, 900), (3, 3600),
])
def test_temporary_failure_retry_schedule(database, monkeypatch, prior_attempts, delay_seconds):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    delivery_id = _pending_delivery(db)
    row = db.get(NotificationDelivery, delivery_id)
    row.attempts = prior_attempts
    db.commit()
    before = datetime.now(timezone.utc)
    assert email.run_email_delivery_once(db, sender=lambda *_: (_ for _ in ()).throw(TimeoutError()))
    db.refresh(row)
    assert row.status == "pending"
    assert row.attempts == prior_attempts + 1
    assert delay_seconds <= (row.next_attempt_at - before).total_seconds() < delay_seconds + 10


def test_pg_constraints_cascade_and_claim_lease(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert _publish(db)
    db.commit()
    delivery = db.scalar(select(NotificationDelivery))
    notification_id = delivery.notification_id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(NotificationDelivery(notification_id=notification_id, channel="email",
                                    recipient="other@example.test", status="pending"))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(NotificationDelivery(notification_id=uuid.uuid4(), channel="email",
                                    recipient="other@example.test", status="pending"))
        db.flush()
    db.rollback()
    claim = email._claim(db, datetime.now(timezone.utc))
    assert claim and claim[0] == delivery.id
    with Session(db.bind) as other:
        assert email._claim(other, datetime.now(timezone.utc)) is None
    db.execute(Notification.__table__.delete().where(Notification.id == notification_id))
    db.commit()
    assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 0


def _pending_delivery(db):
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    assert _publish(db)
    db.commit()
    return db.scalar(select(NotificationDelivery.id))


def test_parallel_claim_uses_independent_sessions(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    delivery_id = _pending_delivery(db)
    barrier = threading.Barrier(2)
    now = datetime.now(timezone.utc)

    def worker():
        with Session(db.bind) as session:
            barrier.wait(timeout=5)
            return email._claim(session, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        claims = [future.result(timeout=10) for future in futures]
    assert sum(claim is not None for claim in claims) == 1
    assert next(claim for claim in claims if claim is not None)[0] == delivery_id


def test_parallel_duplicate_event_repairs_once(database, monkeypatch):
    db = database
    db.add(Responsible(full_name="Ответственный", email="user@example.test",
                       role="manager", keycloak_sub="user-a"))
    db.flush()
    monkeypatch.setattr(settings, "email_notifications_enabled", False)
    event = dict(recipient_user_id="user-a", event_key="assignment:concurrent-repair",
                 type="assignment", priority="INFO", title="Original", message="Original",
                 entity_type="university", entity_id=uuid.uuid4())
    assert service.publish(db, **event)
    db.commit()
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    barrier = threading.Barrier(2)

    def worker():
        with Session(db.bind) as session:
            barrier.wait(timeout=5)
            created = service.publish(session, **event)
            session.commit()
            return created

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert [future.result(timeout=10) for future in futures] == [False, False]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Notification)) == 1
    assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 1


def test_active_expired_and_renewed_lease(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    db = database
    delivery_id = _pending_delivery(db)
    start = datetime.now(timezone.utc)
    first = email._claim(db, start)
    assert first and first[0] == delivery_id
    with Session(db.bind) as other:
        assert email._claim(other, start + timedelta(seconds=149)) is None
    old_lease = db.scalar(select(NotificationDelivery.next_attempt_at))
    assert email._renew_lease(db.bind, delivery_id, first[1], start + timedelta(seconds=100))
    db.expire_all()
    new_lease = db.scalar(select(NotificationDelivery.next_attempt_at))
    assert new_lease > old_lease
    with Session(db.bind) as other:
        assert email._claim(other, start + timedelta(seconds=151)) is None
        second = email._claim(other, start + timedelta(seconds=251))
    assert second and second[0] == delivery_id and second[1] != first[1]
    assert not email._renew_lease(db.bind, delivery_id, first[1], start + timedelta(seconds=251))


def test_live_heartbeat_prevents_reclaim_after_initial_boundary(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    monkeypatch.setattr(email, "_lease_duration", lambda: timedelta(seconds=0.6))
    monkeypatch.setattr(email, "HEARTBEAT_INTERVAL_SECONDS", 0.1)
    db = database
    _pending_delivery(db)
    entered, release = threading.Event(), threading.Event()

    def sender(*_):
        entered.set()
        assert release.wait(5)

    def worker():
        with Session(db.bind) as session:
            return email.run_email_delivery_once(session, sender=sender)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        assert entered.wait(5)
        time.sleep(0.8)
        with Session(db.bind) as other:
            assert email._claim(other, datetime.now(timezone.utc)) is None
        release.set()
        assert future.result(timeout=5)
    db.expire_all()
    assert db.scalar(select(NotificationDelivery.status)) == "sent"


def test_lost_owner_cannot_finalize_reclaimed_delivery(database, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    monkeypatch.setattr(email, "_lease_duration", lambda: timedelta(seconds=0.5))
    monkeypatch.setattr(email, "HEARTBEAT_INTERVAL_SECONDS", 2)
    db = database
    delivery_id = _pending_delivery(db)
    entered, release = threading.Event(), threading.Event()

    def sender(*_):
        entered.set()
        assert release.wait(5)

    def worker():
        with Session(db.bind) as session:
            return email.run_email_delivery_once(session, sender=sender)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        assert entered.wait(5)
        old_token = db.scalar(select(NotificationDelivery.claim_token))
        time.sleep(0.65)
        with Session(db.bind) as other:
            second = email._claim(other, datetime.now(timezone.utc))
        assert second and second[1] != old_token
        release.set()
        assert future.result(timeout=5)
    db.expire_all()
    row = db.get(NotificationDelivery, delivery_id)
    assert row.status == "processing" and row.claim_token == second[1]

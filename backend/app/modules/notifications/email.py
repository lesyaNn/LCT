"""SMTP adapter and durable outbox worker for existing notifications."""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote, urlsplit

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.modules.notifications.address import outbound_email

logger = logging.getLogger("rtk")
HEARTBEAT_INTERVAL_SECONDS = 30


class PermanentEmailError(Exception):
    """An address or SMTP 5xx rejection that must not be retried."""


def target_path(notification: Notification) -> str:
    """Mirror the inbox target routes, using only escaped path components."""
    entity_id = quote(notification.entity_id, safe="")
    university_id = quote(str(notification.university_id), safe="") if notification.university_id else ""
    match notification.entity_type:
        case "workflow":
            return f"/workflows/{entity_id}"
        case "university":
            return f"/universities/{entity_id}"
        case "universities":
            return "/universities"
        case "contract":
            return f"/universities/{university_id}?tab=documents" if university_id else "/universities"
        case "license":
            return f"/universities/{university_id}?tab=licenses" if university_id else "/universities"
        case "import_job":
            return f"/admin/import?job={entity_id}"
        case _:
            return "/notifications"


def render_message(notification: Notification) -> tuple[str, str]:
    """Plain text only; no user supplied HTML or technical identifiers in prose."""
    subject = notification.title.strip() or "Уведомление CRM"
    body = f"{subject}\n\n{notification.message.strip()}"
    origin = settings.frontend_origin.rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme in {"http", "https"} and parsed.netloc
            and not parsed.username and not parsed.password
            and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment):
        body += f"\n\nОткрыть в CRM: {origin}{target_path(notification)}"
    return subject, body


def send_email(recipient: str, subject: str, body: str) -> None:
    """Single mockable SMTP boundary; TLS certificate validation stays enabled."""
    recipient = outbound_email(recipient)
    sender = outbound_email(settings.smtp_from_email)
    if any("\n" in value or "\r" in value for value in (subject, settings.smtp_from_name)):
        raise PermanentEmailError("invalid_header")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = recipient
    message.set_content(body)
    context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                    **({"context": context} if settings.smtp_security == "ssl" else {})) as smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def _lease_duration() -> timedelta:
    return timedelta(seconds=max(150, settings.smtp_timeout_seconds * 2 + 30))


def _claim(db: Session, now: datetime) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Commit a lease before SMTP; SKIP LOCKED prevents simultaneous claims."""
    db.execute(update(NotificationDelivery).where(
        NotificationDelivery.status == "processing",
        NotificationDelivery.next_attempt_at <= now,
        NotificationDelivery.attempts >= settings.email_max_attempts,
    ).values(status="failed", last_error="lease_expired", claim_token=None))
    row = db.scalar(select(NotificationDelivery).where(
        NotificationDelivery.channel == "email",
        NotificationDelivery.next_attempt_at <= now,
        NotificationDelivery.attempts < settings.email_max_attempts,
        or_(NotificationDelivery.status == "pending", NotificationDelivery.status == "processing"),
    ).order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.created_at)
     .with_for_update(skip_locked=True).limit(1))
    if row is None:
        db.commit()
        return None
    token = uuid.uuid4()
    row.status = "processing"
    row.claim_token = token
    row.attempts += 1
    row.last_attempt_at = now
    row.next_attempt_at = now + _lease_duration()
    db.commit()
    return row.id, token


def _renew_lease(bind, delivery_id: uuid.UUID, token: uuid.UUID, now: datetime) -> bool:
    """Renew only a live claim, in a short session independent of SMTP."""
    with Session(bind=bind) as heartbeat_db:
        result = heartbeat_db.execute(update(NotificationDelivery).where(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.status == "processing",
            NotificationDelivery.claim_token == token,
            NotificationDelivery.next_attempt_at > now,
        ).values(next_attempt_at=now + _lease_duration()))
        heartbeat_db.commit()
        return result.rowcount == 1


def _heartbeat(bind, delivery_id: uuid.UUID, token: uuid.UUID,
               stop: threading.Event) -> None:
    """Keep renewing while SMTP runs; retry transient DB errors promptly."""
    interval = HEARTBEAT_INTERVAL_SECONDS
    while not stop.wait(interval):
        try:
            if not _renew_lease(bind, delivery_id, token, datetime.now(timezone.utc)):
                logger.warning("email delivery id=%s lease ownership lost", delivery_id)
                return
            interval = HEARTBEAT_INTERVAL_SECONDS
        except Exception:
            logger.exception("email delivery id=%s lease heartbeat failed", delivery_id)
            interval = min(1, HEARTBEAT_INTERVAL_SECONDS)


def _error_category(exc: Exception) -> tuple[str, bool]:
    """Store a fixed safe category, never an SMTP server response."""
    if isinstance(exc, (PermanentEmailError, ValueError)):
        return "invalid_address_or_header", True
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _ in exc.recipients.values()]
        permanent = bool(codes) and all(500 <= code < 600 for code in codes)
        return ("recipient_refused" if permanent else "smtp_temporary", permanent)
    if isinstance(exc, smtplib.SMTPResponseException):
        code = exc.smtp_code
        return ("smtp_permanent" if 500 <= code < 600 else "smtp_temporary", 500 <= code < 600)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout", False
    if isinstance(exc, (ConnectionError, OSError, smtplib.SMTPException)):
        return "smtp_connection", False
    return "delivery_error", False


def run_email_delivery_once(db: Session, *, sender=send_email) -> bool:
    """Process at most one due row; caller owns the session, not the SMTP call."""
    if not settings.email_notifications_enabled:
        return False
    claim = _claim(db, datetime.now(timezone.utc))
    if claim is None:
        return False
    delivery_id, token = claim
    row = db.get(NotificationDelivery, delivery_id)
    notification = db.get(Notification, row.notification_id) if row else None
    if row is None or notification is None:
        db.rollback()
        return False
    subject, body = render_message(notification)
    recipient = row.recipient
    attempts = row.attempts
    notification_id = notification.id
    db.rollback()  # Never hold an open transaction across the network call.
    category = None
    permanent = False
    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat, args=(db.get_bind(), delivery_id, token, stop), daemon=True,
        name=f"email-lease-{delivery_id}",
    )
    heartbeat.start()
    try:
        try:
            sender(recipient, subject, body)
        except Exception as exc:
            category, permanent = _error_category(exc)
    finally:
        stop.set()
        heartbeat.join()
    now = datetime.now(timezone.utc)
    if category is None:
        changes = dict(status="sent", sent_at=now, last_error=None, claim_token=None)
    elif permanent or attempts >= settings.email_max_attempts:
        changes = dict(status="failed", last_error=category, claim_token=None)
    else:
        # 1, 5, 15, 60 minutes; final (fifth) attempt has no retry.
        delays = (60, 300, 900, 3600)
        changes = dict(status="pending", last_error=category, claim_token=None,
                       next_attempt_at=now + timedelta(seconds=delays[min(attempts - 1, 3)]))
    result = db.execute(update(NotificationDelivery).where(
        NotificationDelivery.id == delivery_id,
        NotificationDelivery.claim_token == token,
        NotificationDelivery.status == "processing",
    ).values(**changes))
    db.commit()
    logger.info("email delivery id=%s notification=%s attempt=%s result=%s error=%s",
                delivery_id, notification_id, attempts,
                changes["status"] if result.rowcount else "lease_lost", category)
    return True

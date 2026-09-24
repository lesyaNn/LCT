"""P2-05 upload policy: single place for limits, chunking and filename safety.

Allowed-types contract (P2-05-01): configured via the
``UPLOAD_ALLOWED_EXTENSIONS`` env var (comma-separated extensions,
e.g. ``"pdf,docx,xlsx"``), parsed by :func:`get_allowed_extensions`.
Empty/unset = open (no contract from the customer yet — accept and record
the declared type). Wiring the real customer list later = setting one env
var, no service/router rewrite.
"""

from __future__ import annotations

import re
from urllib.parse import quote

# Hard limit: 50 MiB exact accepted, 50 MiB + 1 byte -> 413.
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Streaming chunk size (single place): 256 KiB per read iteration.
UPLOAD_CHUNK_SIZE_BYTES = 256 * 1024

# --- Allowed file types (see module docstring) ---------------------------
# Contract wiring (P2-05-01): the allowlist is configured via the
# ``UPLOAD_ALLOWED_EXTENSIONS`` env var (comma-separated, e.g. "pdf,docx").
# Empty/unset = open (no contract from the customer yet — accept and record
# the declared type). The legacy constants below stay None (open) unless a
# future contract fills them in code; env config takes precedence when set.
FILE_TYPE_CONTRACT_STATUS = "ENV_CONFIGURED_OR_OPEN_BY_DEFAULT"


def get_allowed_extensions() -> frozenset[str] | None:
    """Parse ``upload_allowed_extensions``; None = open (no contract)."""
    from app.config import settings

    raw = (settings.upload_allowed_extensions or "")
    parsed = frozenset(
        part.strip().lower().lstrip(".")
        for part in raw.split(",")
        if part.strip().strip(".")
    )
    return parsed or None

MIME_FALLBACK = "application/octet-stream"
MAX_MIME_LENGTH = 128  # mirrors workflow_attachments.mime_type VARCHAR(128)
MAX_FILENAME_LENGTH = 255


def normalize_mime_type(declared: str | None) -> str:
    """Trim and bound the declared content type; never invent one."""
    value = (declared or "").strip()
    if not value:
        return MIME_FALLBACK
    return value[:MAX_MIME_LENGTH]


def check_file_type(filename: str, declared_mime: str | None) -> str:
    """Validate the extension against the env allowlist (P2-05-01).

    Open by default (no contract): records the declared type verbatim.
    With ``UPLOAD_ALLOWED_EXTENSIONS`` set: unknown/missing extensions
    are rejected with 415. MIME types are never allowlisted (no MIME
    contract) — only recorded.
    """
    from app.core.errors import BusinessException
    from app.schemas.errors import ErrorCode

    mime = normalize_mime_type(declared_mime)
    allowed = get_allowed_extensions()
    if allowed is None:
        return mime
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed:
        raise BusinessException(ErrorCode.FILE_TYPE_NOT_ALLOWED)
    return mime


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(name: str | None) -> str:
    """Keep the original name as metadata only, safe for headers/logging.

    Strips: NUL, CR/LF (header injection), control chars, directory parts
    (``/``, ``\\``), drive letters (``C:``), and bare ``.``/``..``.
    Never returns an empty or path-like value.
    """
    if not name:
        return "file"
    cleaned = name.replace("\x00", "")
    cleaned = cleaned.replace("\\", "/")
    # Drive letter (``C:...``) and anything before the last slash is a path.
    if len(cleaned) >= 2 and cleaned[1] == ":":
        cleaned = cleaned[2:]
    cleaned = cleaned.split("/")[-1]
    cleaned = cleaned.replace("\r", "").replace("\n", "")
    cleaned = _CONTROL_CHARS.sub("", cleaned).strip(" .")
    if cleaned in ("", ".", ".."):
        return "file"
    if len(cleaned) > MAX_FILENAME_LENGTH:
        cleaned = cleaned[:MAX_FILENAME_LENGTH]
    return cleaned


def content_disposition(safe_name: str) -> str:
    """RFC 6266/5987 attachment header from an already-sanitized name."""
    ascii_name = re.sub(r"[^\x20-\x7e]", "_", safe_name).replace('"', "_").replace("\\", "_")
    ascii_name = ascii_name or "file"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe_name)}"

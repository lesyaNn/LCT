"""P2-05 upload policy: single place for limits, chunking and filename safety.

Allowed-types contract status: the "10 types" source of truth was NOT found
(README, docs/, API contracts, frontend, tests, mocks searched — only the
legacy deferred 7-MIME set in ``modules/documents/router.py`` exists, which
must NOT be reused). The allowlist therefore lives here as one explicit
extension point (``ALLOWED_EXTENSIONS`` / ``ALLOWED_MIME_TYPES`` /
``EXTENSION_TO_MIME``), currently disabled (``None`` = no contract, accept
and record the declared type). Wiring a real contract later = filling these
three constants, no service/router rewrite.
"""

from __future__ import annotations

import re
from urllib.parse import quote

# Hard limit: 50 MiB exact accepted, 50 MiB + 1 byte -> 413.
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

# Streaming chunk size (single place): 256 KiB per read iteration.
UPLOAD_CHUNK_SIZE_BYTES = 256 * 1024

# --- Allowed file types (see module docstring) ---------------------------
# Status marker for the missing contract ( surfaced in the final report ).
FILE_TYPE_CONTRACT_STATUS = "PARTIAL_BLOCKED_BY_MISSING_FILE_TYPE_CONTRACT"

ALLOWED_EXTENSIONS: frozenset[str] | None = None
ALLOWED_MIME_TYPES: frozenset[str] | None = None
EXTENSION_TO_MIME: dict[str, frozenset[str]] = {}

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
    """Validate extension + declared content-type against the allowlist.

    Without a contract (current state) this records the declared type
    verbatim instead of rejecting with an invented list.
    """
    mime = normalize_mime_type(declared_mime)
    if ALLOWED_EXTENSIONS is None and ALLOWED_MIME_TYPES is None:
        return mime
    from fastapi import HTTPException

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ALLOWED_EXTENSIONS is not None and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"File extension not allowed: .{ext}")
    if ALLOWED_MIME_TYPES is not None and mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail=f"MIME not allowed: {mime}")
    expected = EXTENSION_TO_MIME.get(ext)
    if expected is not None and mime not in expected:
        raise HTTPException(status_code=415, detail="Extension/MIME mismatch")
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

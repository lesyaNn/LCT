"""Shared normalization for file-import identities and contact values."""

from __future__ import annotations

import re
from typing import Any


def normalized_name(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    return text.strip('«»“”"').strip()


def normalize_phone(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not 10 <= len(digits) <= 15:
        raise ValueError("Некорректный номер телефона")
    return "+" + digits


def split_products(value: Any) -> list[str]:
    """Split the provided comma/semicolon-separated product cell, not companies."""
    return [name for part in re.split(r"[,;]", str(value or "")) if (name := normalized_name(part))]

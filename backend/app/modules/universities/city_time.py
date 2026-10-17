"""Offline city lookup. Ambiguous and unknown names never default to Moscow."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CITY_INDEX = Path(__file__).resolve().parents[2] / "assets" / "city-time-zones.json"


def normalize_city(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    value = re.sub(r"[‐‑‒–—−]", "-", value.strip())
    value = re.sub(r"^(?:город\s+|г\.\s*|г\s+)", "", value)
    return re.sub(r"\s*-\s*", "-", " ".join(value.split())).strip(" .,;")


@lru_cache(maxsize=1)
def city_index() -> dict[str, str | None]:
    return json.loads(CITY_INDEX.read_text(encoding="utf-8"))["cities"]


def city_time_zone(city: str | None) -> str | None:
    return city_index().get(normalize_city(city)) if city else None

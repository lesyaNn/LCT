"""Exact offline GeoNames city-to-admin1 lookup for the universities map."""

import json
from functools import lru_cache
from pathlib import Path

from app.modules.universities.city_time import normalize_city

INDEX = Path(__file__).resolve().parents[2] / "assets" / "city-regions.json"


@lru_cache(maxsize=1)
def city_regions() -> dict[str, str | None]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["cities"]


def city_region_code(city: str | None) -> str | None:
    return city_regions().get(normalize_city(city)) if city else None

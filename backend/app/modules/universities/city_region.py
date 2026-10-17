"""Exact offline GeoNames city-to-admin1 lookup for the universities map."""

import json
from functools import lru_cache
from pathlib import Path

from app.modules.universities.city_time import normalize_city

INDEX = Path(__file__).resolve().parents[2] / "assets" / "city-regions.json"

# The CRM contains this institution with only "Донецк" as its city. GeoNames
# also has a Donetsk in Rostov Oblast, so the city alone is ambiguous. The
# institution's published address identifies the intended region exactly.
UNIVERSITY_REGION_CODES = {
    "донецкий национальный технический университет": "UA.05",
}


@lru_cache(maxsize=1)
def city_regions() -> dict[str, str | None]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["cities"]


def city_region_code(city: str | None, university_name: str | None = None) -> str | None:
    if not city:
        return None
    code = city_regions().get(normalize_city(city))
    if code is None and university_name and normalize_city(city) == "донецк":
        return UNIVERSITY_REGION_CODES.get(university_name.casefold().strip())
    return code

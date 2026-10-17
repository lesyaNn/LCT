"""Timezone selection and the actual read DTO/OpenAPI contract, without a DB."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.catalog.schemas import UniversityDetail
from app.modules.universities.city_time import city_index, city_time_zone
from app.modules.universities.passport_schemas import UniversityBrief


@pytest.mark.parametrize(
    "city,zone",
    [
        ("Москва", "Europe/Moscow"),
        ("  г.МОСКВА  ", "Europe/Moscow"),
        ("город Санкт-Петербург", "Europe/Moscow"),
        ("Санкт – Петербург", "Europe/Moscow"),
        ("Казань", "Europe/Moscow"),
        ("Калининград", "Europe/Kaliningrad"),
        ("Королёв", "Europe/Moscow"),
        ("Самара", "Europe/Samara"),
        ("Саратов", "Europe/Saratov"),
        ("Екатеринбург", "Asia/Yekaterinburg"),
        ("Омск", "Asia/Omsk"),
        ("Новосибирск", "Asia/Novosibirsk"),
        ("Томск", "Asia/Tomsk"),
        ("Красноярск", "Asia/Krasnoyarsk"),
        ("Иркутск", "Asia/Irkutsk"),
        ("Якутск", "Asia/Yakutsk"),
        ("Владивосток", "Asia/Vladivostok"),
        ("Магадан", "Asia/Magadan"),
        ("Петропавловск-Камчатский", "Asia/Kamchatka"),
        ("Анадырь", "Asia/Anadyr"),
        ("Moscow", "Europe/Moscow"),
        (None, None),
        ("", None),
        ("—", None),
        ("Несуществующий город", None),
        ("Киров", None),  # Same current name in more than one timezone.
        ("Москва, неизвестный регион", None),
    ],
)
def test_city_time_zone_is_exact_and_conservative(city, zone):
    assert city_time_zone(city) == zone


def test_every_published_zone_is_valid_and_dataset_is_offline():
    index = city_index()
    assert len(index) > 5000
    for zone in set(index.values()) - {None}:
        assert ZoneInfo(zone).key == zone


def test_pasport_and_catalog_compute_zone_from_city_not_a_stale_input():
    data = {"id": uuid.uuid4(), "name": "Тестовый вуз", "city": "Владивосток"}
    passport = UniversityBrief.model_validate({**data, "time_zone": "Europe/Moscow"})
    assert passport.model_dump()["time_zone"] == "Asia/Vladivostok"
    detail = UniversityDetail(**data, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    assert detail.model_dump()["time_zone"] == "Asia/Vladivostok"
    detail.city = "Самара"
    assert detail.model_dump()["time_zone"] == "Europe/Samara"


def test_schema_marks_zone_as_nullable_and_read_only():
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]
    for name in ("UniversityBrief", "UniversityListItem", "UniversityDetail"):
        field = schemas[name]["properties"]["time_zone"]
        assert field["readOnly"] is True
        assert {entry["type"] for entry in field["anyOf"]} == {"string", "null"}

"""P4-05-01 unit tests: JSON exporter over a stubbed dataset (no database).

Covers the frozen shape (``metadata/filters/columns/rows/totals``),
default-14 vs subset vs order, typed serialization (UUID/date/datetime/
numbers/null/unicode), hidden-key exclusion, UTF-8 readability,
temp-file atomicity, failure cleanup and the streaming (no ``.all()`` on
the dataset cursor) export path.
"""

from __future__ import annotations

import inspect
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.modules.analytics.columns import DEFAULT_COLUMNS
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.json_export import (
    JSON_FROZEN_KEYS,
    generate_json_report,
    serialize_json_value,
)

SUBSET_3 = ["university", "city", "comment"]


def _rows() -> list[dict]:
    uid = uuid.uuid4()
    return [
        {
            "university": "МГУ им. Ломоносова",
            "city": "Москва",
            "comment": "Комментарий №1",
            "_university_id": uid,
            "_license_id": uuid.uuid4(),
        },
        {
            "university": "ВУЗ Бета",
            "city": None,
            "comment": None,
            "_university_id": uid,
            "_license_id": None,
        },
    ]


class _Mappings:
    """Mappings result that explodes if the exporter materializes via .all()."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def all(self):  # pragma: no cover
        raise AssertionError("JSON export path must stream, never call .all()")

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, values: list):
        self._values = values

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, mappings_rows=None, scalars_values=None, pairs=None):
        self._mappings_rows = mappings_rows or []
        self._scalars_values = scalars_values or []
        self._pairs = pairs if pairs is not None else []

    def mappings(self):
        return _Mappings(self._mappings_rows)

    def scalars(self):
        return _Scalars(self._scalars_values)

    def all(self):
        return list(self._pairs)


class FakeSession:
    """Same routing shapes as production (see XLSX/PDF unit stubs)."""

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def _owner_uids(self) -> list:
        uids = []
        for row in self._rows:
            uid = row.get("_university_id")
            if uid is not None and uid not in uids:
                uids.append(uid)
        return uids

    def execute(self, stmt, execution_options=None):
        try:
            compiled = str(stmt).lower()
        except Exception:
            compiled = ""
        if "university_responsibles" in compiled:
            pairs = []
            for row in self._rows:
                uid = row.get("_university_id")
                name = row.get("responsible")
                if uid is not None and name and (uid, name) not in pairs:
                    pairs.append((uid, name))
            return _Result(pairs=pairs)
        if "licenses" in compiled or "_university_id" in compiled:
            return _Result(mappings_rows=self._rows)
        return _Result(scalars_values=self._owner_uids())


def _gen(tmp_path: Path, columns, rows: list[dict], **kw):
    out = tmp_path / "report.json"
    result = generate_json_report(FakeSession(rows), UnifiedFilter(), columns, out, **kw)
    assert result.path == out
    return result, json.loads(out.read_text(encoding="utf-8"))


def test_selected_grouping_is_exported_with_the_rows(tmp_path, monkeypatch):
    from app.modules.analytics.stats import ReportStatsService, StatBucket, StatSlice

    summary = StatSlice("by_university", "Распределение строк по вузам", "rows", 2, (StatBucket("МГУ", 2),))
    monkeypatch.setattr(ReportStatsService, "group_slice", staticmethod(lambda *args, **kwargs: summary))
    _, doc = _gen(tmp_path, ["university"], [{"university": "МГУ"}], group_by="university")
    assert list(doc) == ["metadata", "filters", "columns", "rows", "groups", "totals"]
    assert doc["groups"]["buckets"] == [{"label": "МГУ", "count": 2}]


def test_selected_columns_export_multiple_groups(tmp_path, monkeypatch):
    from app.modules.analytics.stats import ReportStatsService, StatBucket, StatSlice

    def summary(_db, _filters, dimension, **_kwargs):
        return StatSlice(f"by_{dimension}", dimension, "rows", 1, (StatBucket(dimension, 1),))

    monkeypatch.setattr(ReportStatsService, "group_slice", staticmethod(summary))
    _, doc = _gen(tmp_path, ["university", "direction"], [{"university": "МГУ", "direction": "ИТ"}], group_bys=["university", "direction"])
    assert [group["dimension"] for group in doc["groups"]] == ["by_university", "by_direction"]


# ------------------------------------------------------------- serialization


def test_serialize_json_value_types():
    uid = uuid.uuid4()
    assert serialize_json_value(uid) == str(uid)
    assert serialize_json_value(date(2026, 2, 3)) == "2026-02-03"
    aware = datetime(2026, 2, 3, 10, 30, tzinfo=timezone.utc)
    assert serialize_json_value(aware) == "2026-02-03T10:30:00+00:00"
    naive = datetime(2026, 2, 3, 10, 30)
    assert serialize_json_value(naive) == "2026-02-03T10:30:00+00:00"
    assert serialize_json_value(85) == 85 and isinstance(serialize_json_value(85), int)
    assert serialize_json_value(None) is None
    assert serialize_json_value("МГУ") == "МГУ"


def test_serialize_json_value_enum_and_fallback():
    from app.schemas.common import WorkflowStageStatus

    assert serialize_json_value(WorkflowStageStatus.CURRENT) == "current"
    assert serialize_json_value(1.5) == 1.5


# ------------------------------------------------------------- shape / columns


def test_frozen_top_level_keys_and_order(tmp_path):
    _, doc = _gen(tmp_path, SUBSET_3, _rows())
    assert list(doc.keys()) == list(JSON_FROZEN_KEYS)
    assert JSON_FROZEN_KEYS == ("metadata", "filters", "columns", "rows", "totals")


def test_metadata_block(tmp_path):
    _, doc = _gen(tmp_path, SUBSET_3, _rows())
    assert doc["metadata"]["report_name"] == "Аналитический отчёт по взаимодействию с ВУЗами"
    assert doc["metadata"]["version"] == "1.0"
    assert doc["metadata"]["generator"] == "CRM ИТ-Школа Ростелеком"
    assert datetime.fromisoformat(doc["metadata"]["generated_at"]).tzinfo is not None


def test_columns_carry_key_and_title(tmp_path):
    _, doc = _gen(tmp_path, SUBSET_3, _rows())
    assert doc["columns"] == [
        {"key": "university", "title": "Наименование ВУЗа"},
        {"key": "city", "title": "Город"},
        {"key": "comment", "title": "Комментарий"},
    ]


def test_totals_computed(tmp_path):
    _, doc = _gen(tmp_path, SUBSET_3, _rows())
    assert doc["totals"]["row_count"] == 2
    # Фикстура несёт два разных имени (в проде имена уникальны).
    assert doc["totals"]["universities"] == 2


def test_totals_empty_when_no_scores(tmp_path):
    _, doc = _gen(tmp_path, ["university"], [])
    assert doc["totals"] == {
        "row_count": 0, "universities": None,
    }


def test_totals_fallback_to_names_without_ids(tmp_path):
    # Курсор несёт только публичные ключи: distinct university names.
    rows = [
        {"university": "ВУЗ А", "city": "Москва"},
        {"university": "ВУЗ А", "city": "Москва"},
        {"university": "ВУЗ Б", "city": None},
    ]
    _, doc = _gen(tmp_path, ["university", "city"], rows)
    assert doc["totals"]["universities"] == 2


def test_default_columns_are_14_mandatory(tmp_path):
    result, doc = _gen(tmp_path, None, [])
    assert result.columns == list(DEFAULT_COLUMNS)
    assert [c["key"] for c in doc["columns"]] == list(DEFAULT_COLUMNS)
    assert all(c["title"] for c in doc["columns"])
    assert doc["totals"]["row_count"] == 0
    assert doc["rows"] == []


def test_subset_and_selected_column_order(tmp_path):
    cols = ["city", "university", "comment"]
    result, doc = _gen(tmp_path, cols, _rows())
    assert result.columns == cols
    assert [c["key"] for c in doc["columns"]] == cols
    assert doc["totals"]["row_count"] == 2
    assert list(doc["rows"][0].keys()) == cols
    assert doc["rows"][0] == {
        "city": "Москва",
        "university": "МГУ им. Ломоносова",
        "comment": "Комментарий №1",
    }


def test_hidden_keys_never_emitted(tmp_path):
    _, doc = _gen(tmp_path, None, _rows())
    for item in doc["rows"]:
        assert "_university_id" not in item
        assert "_license_id" not in item


def test_null_stays_null_numeric_stays_numeric(tmp_path):
    _, doc = _gen(tmp_path, SUBSET_3, _rows())
    second = doc["rows"][1]
    assert second["city"] is None
    assert second["comment"] is None
    assert doc["rows"][0]["city"] == "Москва"


def test_unicode_readable_utf8_not_escaped_dump(tmp_path):
    result, _ = _gen(tmp_path, SUBSET_3, _rows())
    raw = result.path.read_bytes().decode("utf-8")
    assert "МГУ им. Ломоносова" in raw
    assert "Комментарий №1" in raw
    assert "\\u041c" not in raw  # ensure_ascii=False on file


def test_unicode_round_trip_through_escaped_json():
    # json.dumps default (ensure_ascii=True, as in JSONResponse) round-trips.
    payload = json.dumps({"university": "МГУ им. Ломоносова"})
    assert json.loads(payload)["university"] == "МГУ им. Ломоносова"


def test_dates_iso_and_datetimes_with_timezone(tmp_path):
    rows = [
        {
            "university": "ВУЗ",
            "license_signed": date(2026, 2, 1),
            "license_expires": None,
            "_university_id": uuid.uuid4(),
        }
    ]
    _, doc = _gen(tmp_path, ["university", "license_signed", "license_expires"], rows)
    assert doc["rows"][0]["license_signed"] == "2026-02-01"
    assert doc["rows"][0]["license_expires"] is None


def test_generated_at_iso_with_timezone(tmp_path):
    naive = datetime(2026, 9, 20, 10, 30, 0)
    result, doc = _gen(tmp_path, ["university"], _rows()[:1], generated_at=naive)
    assert result.generated_at.tzinfo is not None
    parsed = datetime.fromisoformat(doc["metadata"]["generated_at"])
    assert parsed.tzinfo is not None


def test_filters_serialized_all_8_fields(tmp_path):
    from datetime import date as _date

    uid = uuid.uuid4()
    filters = UnifiedFilter(
        date_from=_date(2026, 1, 1),
        date_to=_date(2026, 9, 30),
        university_ids=[uid],
        workflow_statuses=["pending"],
    )
    out = tmp_path / "f.json"
    generate_json_report(FakeSession([]), filters, ["university"], out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert set(doc["filters"]) == {
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
    }
    assert doc["filters"]["date_from"] == "2026-01-01"
    assert doc["filters"]["university_ids"] == [str(uid)]
    assert doc["filters"]["workflow_statuses"] == ["pending"]


# ------------------------------------------------------------- result / streaming


def test_result_metadata(tmp_path):
    result, _ = _gen(tmp_path, SUBSET_3, _rows())
    assert result.path.exists()
    assert result.size_bytes == result.path.stat().st_size > 0
    assert result.row_count == 2
    assert result.generated_at.tzinfo is not None


def test_no_part_files_left_behind(tmp_path):
    _gen(tmp_path, SUBSET_3, _rows())
    assert list(tmp_path.glob("*.part")) == []


def test_iterate_rows_is_streaming_generator():
    assert inspect.isgeneratorfunction(ReportDatasetService.iterate_rows)


def test_export_path_never_calls_mappings_all(tmp_path):
    # FakeSession._Mappings.all() raises; a green run proves streaming.
    _gen(tmp_path, SUBSET_3, _rows())


def test_large_export_bounded_single_pass(tmp_path):
    rows = [
        {
            "university": f"ВУЗ {i:05d}",
            "workflow_progress": i % 101,
            "comment": None,
            "_university_id": uuid.uuid4(),
        }
        for i in range(3000)
    ]
    result, doc = _gen(tmp_path, SUBSET_3, rows)
    assert result.row_count == 3000
    assert doc["totals"]["row_count"] == 3000
    assert len(doc["rows"]) == 3000
    assert doc["rows"][0]["university"] == "ВУЗ 00000"
    assert doc["rows"][2999]["university"] == "ВУЗ 02999"


def test_failure_removes_temp_and_raises(tmp_path):
    out = tmp_path / "fail.json"
    real_dumps = json.dumps

    def _boom(*args, **kwargs):
        raise RuntimeError("disk gone")

    json.dumps = _boom
    try:
        with pytest.raises(RuntimeError, match="disk gone"):
            generate_json_report(FakeSession(_rows()), UnifiedFilter(), SUBSET_3, out)
    finally:
        json.dumps = real_dumps
    assert not out.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_unknown_and_empty_columns_raise(tmp_path):
    from app.modules.analytics.columns import (
        EmptyReportColumnsError,
        UnknownReportColumnError,
    )

    with pytest.raises(UnknownReportColumnError):
        generate_json_report(
            FakeSession([]),
            UnifiedFilter(),
            ["university", "bogus"],
            tmp_path / "a.json",
        )
    with pytest.raises(EmptyReportColumnsError):
        generate_json_report(FakeSession([]), UnifiedFilter(), [], tmp_path / "b.json")
    with pytest.raises(ValueError, match="batch_size"):
        generate_json_report(
            FakeSession([]),
            UnifiedFilter(),
            ["university"],
            tmp_path / "c.json",
            batch_size=0,
        )
    assert list(tmp_path.glob("*.part")) == []
    assert list(tmp_path.glob("*.json")) == []

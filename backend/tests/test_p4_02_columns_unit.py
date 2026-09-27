"""P4-02 unit tests: column registry, ReportRequest, presets (no database)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.analytics.columns import (
    ADDITIONAL_COLUMNS,
    COLUMN_REGISTRY,
    DEFAULT_COLUMNS,
    EXTENDED_COLUMNS,
    FULL_COLUMNS,
    MANDATORY_COLUMNS,
    OPTIONAL_COLUMNS,
    PRESETS,
    STANDARD_COLUMNS,
    TZ_COLUMNS,
    EmptyReportColumnsError,
    UnknownReportColumnError,
    is_known_column,
    resolve_columns,
)
from app.modules.analytics.report_request import ReportRequest
from app.schemas.common import ReportFormat

EXPECTED_TITLES = {
    "university": "Наименование ВУЗа",
    "direction": "ИТ-направление",
    "program": "ИТ-программа",
    "product": "ИТ-продукт",
    "workflow_status": "Статус работы",
    "responsible": "Ответственный",
    "vendor": "Вендор",
    "contract_number": "Номер договора",
    "license_signed": "Подписание лицензии",
    "license_expires": "Срок действия",
    "transfer_status": "Статус передачи",
    "comment": "Комментарий",
}

#: The five output columns the ТЗ names, in ТЗ order.
EXPECTED_TZ_TITLES = {
    "university": "Наименование ВУЗа",
    "direction": "ИТ-направление",
    "product": "ИТ-продукт",
    "workflow_status": "Статус работы",
    "responsible": "Ответственный",
}


def test_mandatory_columns_are_exactly_the_five_tz_columns():
    assert MANDATORY_COLUMNS == tuple(EXPECTED_TZ_TITLES.keys())
    assert TZ_COLUMNS == MANDATORY_COLUMNS
    assert len(MANDATORY_COLUMNS) == len(EXPECTED_TZ_TITLES)
    assert len(set(MANDATORY_COLUMNS)) == len(EXPECTED_TZ_TITLES)


def test_mandatory_titles_match_spec():
    for key, title in EXPECTED_TZ_TITLES.items():
        assert COLUMN_REGISTRY[key].title == title, key
        assert COLUMN_REGISTRY[key].mandatory is True, key


def test_non_tz_columns_are_optional_but_supported():
    """ТЗ columns are the default, not the only selectable ones."""
    for key, title in EXPECTED_TITLES.items():
        assert COLUMN_REGISTRY[key].title == title, key
    for key in EXTENDED_COLUMNS:
        assert COLUMN_REGISTRY[key].mandatory is False, key
        assert is_known_column(key), key


def test_registry_single_source_of_truth():
    assert set(COLUMN_REGISTRY) >= set(MANDATORY_COLUMNS)
    for key in COLUMN_REGISTRY:
        entry = COLUMN_REGISTRY[key]
        assert entry.key == key
        assert entry.source, key  # every column documents its canonical source


def test_default_columns_are_the_immutable_tz_set():
    assert DEFAULT_COLUMNS == TZ_COLUMNS
    resolved = resolve_columns(None)
    assert resolved == list(TZ_COLUMNS)
    resolved.append("university")
    assert resolve_columns(None) == list(TZ_COLUMNS)


def test_resolve_preserves_order_and_dedupes():
    assert resolve_columns(["comment", "university", "comment"]) == [
        "comment",
        "university",
    ]
    assert resolve_columns(["university", "university", "comment"]) == [
        "university",
        "comment",
    ]


def test_resolve_unknown_raises_never_ignored():
    with pytest.raises(UnknownReportColumnError, match="unknown report columns"):
        resolve_columns(["university", "bogus"])
    with pytest.raises(UnknownReportColumnError):
        resolve_columns(["nope"])


def test_resolve_empty_raises():
    with pytest.raises(EmptyReportColumnsError, match="at least one column"):
        resolve_columns([])


def test_is_known_column():
    assert is_known_column("university")
    assert not is_known_column("bogus")


def test_presets():
    assert PRESETS["MINIMAL"] == TZ_COLUMNS
    assert STANDARD_COLUMNS[: len(TZ_COLUMNS)] == TZ_COLUMNS
    assert set(STANDARD_COLUMNS) == set(TZ_COLUMNS) | {"program", "city", "current_stage"}
    assert set(FULL_COLUMNS) == set(TZ_COLUMNS) | set(ADDITIONAL_COLUMNS)
    assert set(FULL_COLUMNS) == set(COLUMN_REGISTRY), "FULL must cover the registry"
    assert ADDITIONAL_COLUMNS == EXTENDED_COLUMNS + OPTIONAL_COLUMNS
    assert set(OPTIONAL_COLUMNS) == {
        "city", "current_stage", "last_interaction", "workflow_progress",
        "overdue_tasks",
    }
    for key in ADDITIONAL_COLUMNS:
        assert COLUMN_REGISTRY[key].mandatory is False, key


def test_full_optionals_frozen():
    for key in ("last_interaction", "workflow_progress", "overdue_tasks"):
        assert key in COLUMN_REGISTRY, key


def test_report_format_reuses_shared_enum():
    import app.modules.analytics.report_request as rr

    assert rr.ReportFormat is ReportFormat
    # ТЗ: the tabular report must export to XLS, XLSX and PDF (+ JSON kept).
    assert {m.value for m in ReportFormat} == {"xls", "xlsx", "pdf", "json"}


def test_report_request_defaults():
    req = ReportRequest(format=ReportFormat.XLSX)
    assert req.filters == col_valid_empty_filter()
    assert req.columns is None
    assert req.resolved_columns == list(MANDATORY_COLUMNS)


def col_valid_empty_filter():
    from app.modules.analytics.filters import UnifiedFilter

    return UnifiedFilter()


def test_report_request_explicit_columns_normalized():
    req = ReportRequest(
        format="pdf", filters={}, columns=["comment", "university", "comment"]
    )
    assert req.format is ReportFormat.PDF
    assert req.columns == ["comment", "university"]
    assert req.resolved_columns == ["comment", "university"]


def test_report_request_unknown_column_is_422_style():
    with pytest.raises(ValidationError) as exc_info:
        ReportRequest(format="json", filters={}, columns=["university", "bogus"])
    assert "unknown report columns" in str(exc_info.value)


def test_report_request_empty_columns_is_422_style():
    with pytest.raises(ValidationError) as exc_info:
        ReportRequest(format="json", filters={}, columns=[])
    assert "at least one column" in str(exc_info.value)


def test_report_request_uses_frozen_unified_filter():
    from app.modules.analytics.filters import UnifiedFilter

    req = ReportRequest.model_validate(
        {
            "format": "json",
            "filters": {
                "date_from": None,
                "date_to": None,
                "university_ids": [],
                "direction_ids": [],
                "program_ids": [],
                "product_ids": [],
                "responsible_ids": [],
                "workflow_statuses": [],
            },
            "columns": None,
        }
    )
    assert isinstance(req.filters, UnifiedFilter)
    assert req.filters == UnifiedFilter()
    schema = ReportRequest.model_json_schema()
    assert set(schema["properties"]) == {"format", "filters", "columns"}


def test_public_column_contract_matches_registry():
    root = Path(__file__).resolve().parents[2]
    contract_path = root / "docs" / "contracts" / "report-columns.json"
    assert contract_path.exists(), "docs/contracts/report-columns.json must exist"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert [c["key"] for c in contract["mandatory_columns"]] == list(MANDATORY_COLUMNS)
    for entry in contract["mandatory_columns"]:
        reg = COLUMN_REGISTRY[entry["key"]]
        assert entry["title"] == reg.title, entry["key"]
        assert entry["type"] == reg.data_type, entry["key"]
        assert entry["source"] == reg.source, entry["key"]
    assert [c["key"] for c in contract["extended_columns"]] == list(EXTENDED_COLUMNS)
    for entry in contract["extended_columns"]:
        reg = COLUMN_REGISTRY[entry["key"]]
        assert entry["title"] == reg.title, entry["key"]
        assert entry["type"] == reg.data_type, entry["key"]
        assert entry["source"] == reg.source, entry["key"]
    supported = {c["key"] for c in contract["optional_columns_supported"]}
    assert supported == set(OPTIONAL_COLUMNS)


def test_column_module_has_no_second_filter_dto():
    import app.modules.analytics.columns as columns_module
    import app.modules.analytics.report_request as request_module

    for module in (columns_module, request_module):
        for name in dir(module):
            assert "Filter" not in name or name == "UnifiedFilter", (
                f"{module.__name__} must not define a second filter DTO: {name}"
            )

"""P4-02 unit tests: column registry, ReportRequest, presets (no database).

Covers §29-§34 at the contract level: the 14 mandatory keys/titles, default
columns, dedupe/unknown/empty behavior, preset constants, ReportFormat reuse
(single shared enum) and the public ``report-columns.json`` artifact.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.analytics.columns import (
    COLUMN_REGISTRY,
    DEFAULT_COLUMNS,
    FULL_COLUMNS,
    MANDATORY_COLUMNS,
    OPTIONAL_COLUMNS,
    PRESETS,
    STANDARD_COLUMNS,
    UNSUPPORTED_OPTIONAL_COLUMNS,
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
    "software": "ПО",
    "contract_number": "Номер договора",
    "license_signed": "Подписание лицензии",
    "license_expires": "Срок действия",
    "transfer_status": "Статус передачи",
    "comment": "Комментарий",
    "health_score": "Health Score",
}


def test_mandatory_columns_exactly_14_in_order():
    assert MANDATORY_COLUMNS == tuple(EXPECTED_TITLES.keys())
    assert len(MANDATORY_COLUMNS) == 14
    assert len(set(MANDATORY_COLUMNS)) == 14


def test_mandatory_titles_match_spec():
    for key, title in EXPECTED_TITLES.items():
        assert COLUMN_REGISTRY[key].title == title, key
        assert COLUMN_REGISTRY[key].mandatory is True, key


def test_registry_single_source_of_truth():
    assert set(COLUMN_REGISTRY) >= set(MANDATORY_COLUMNS)
    for key in MANDATORY_COLUMNS:
        entry = COLUMN_REGISTRY[key]
        assert entry.key == key
        assert entry.source, key  # every column documents its canonical source


def test_default_columns_are_immutable_14():
    assert DEFAULT_COLUMNS == MANDATORY_COLUMNS
    resolved = resolve_columns(None)
    assert resolved == list(MANDATORY_COLUMNS)
    resolved.append("university")
    assert resolve_columns(None) == list(MANDATORY_COLUMNS)


def test_resolve_preserves_order_and_dedupes():
    assert resolve_columns(["health_score", "university", "health_score"]) == [
        "health_score",
        "university",
    ]
    assert resolve_columns(["university", "university", "health_score"]) == [
        "university",
        "health_score",
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
    assert PRESETS["MINIMAL"] == MANDATORY_COLUMNS
    assert STANDARD_COLUMNS[: len(MANDATORY_COLUMNS)] == MANDATORY_COLUMNS
    assert set(STANDARD_COLUMNS) == set(MANDATORY_COLUMNS) | {"city", "current_stage"}
    assert set(FULL_COLUMNS) == set(MANDATORY_COLUMNS) | set(OPTIONAL_COLUMNS)
    assert set(OPTIONAL_COLUMNS) == {
        "city", "current_stage", "last_interaction", "workflow_progress",
        "teacher_readiness", "overdue_tasks",
    }
    for key in OPTIONAL_COLUMNS:
        assert COLUMN_REGISTRY[key].mandatory is False, key


def test_full_optionals_frozen():
    for key in ("last_interaction", "workflow_progress", "teacher_readiness", "overdue_tasks"):
        assert key in COLUMN_REGISTRY, key
        assert key not in UNSUPPORTED_OPTIONAL_COLUMNS, key


def test_report_format_reuses_shared_enum():
    import app.modules.analytics.report_request as rr

    assert rr.ReportFormat is ReportFormat
    assert {m.value for m in ReportFormat} == {"xlsx", "pdf", "json"}
    assert "xls" not in {m.value for m in ReportFormat}


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
        format="pdf", filters={}, columns=["health_score", "university", "health_score"]
    )
    assert req.format is ReportFormat.PDF
    assert req.columns == ["health_score", "university"]
    assert req.resolved_columns == ["health_score", "university"]


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
    supported = {c["key"] for c in contract["optional_columns_supported"]}
    assert supported == set(OPTIONAL_COLUMNS)
    assert set(contract["optional_columns_unsupported"]) == set(
        UNSUPPORTED_OPTIONAL_COLUMNS
    )


def test_column_module_has_no_second_filter_dto():
    import app.modules.analytics.columns as columns_module
    import app.modules.analytics.report_request as request_module

    for module in (columns_module, request_module):
        for name in dir(module):
            assert "Filter" not in name or name == "UnifiedFilter", (
                f"{module.__name__} must not define a second filter DTO: {name}"
            )

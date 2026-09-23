"""P4-01-01 unit tests: frozen UnifiedFilter contract (no database needed).

Covers §26: defaults, all-fields, one-sided dates, valid/invalid ranges,
multi IDs, empty arrays, duplicate IDs, JSON round-trip, query param
parsing (repeated multi-select), workflow statuses, the 422 error contract
and the public contract artifact.
"""

import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.security import CurrentUser
from app.models.catalog import University
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import (
    ID_LIST_FIELDS,
    UnifiedFilter,
    WorkflowFilterStatus,
    get_unified_filter,
)
from app.schemas.common import WorkflowStageStatus

A = uuid.uuid4()
B = uuid.uuid4()
C = uuid.uuid4()


def _probe_app():
    app = FastAPI()

    @app.get("/probe")
    def probe(filters: UnifiedFilter = Depends(get_unified_filter)):
        return filters.model_dump(mode="json")

    return app


@pytest.fixture()
def probe_client():
    return TestClient(_probe_app(), raise_server_exceptions=False)


# ------------------------------------------------------------------ defaults


def test_default_object_is_empty_and_unfiltered():
    f = UnifiedFilter()
    assert f.date_from is None
    assert f.date_to is None
    for field in ID_LIST_FIELDS:
        assert getattr(f, field) == []
    assert f.workflow_statuses == []
    # An empty filter builds zero predicates (never WHERE FALSE).
    assert UnifiedFilterService.build_university_conditions(f) == []


def test_explicit_empty_arrays_mean_not_applied():
    f = UnifiedFilter(
        university_ids=[],
        direction_ids=[],
        program_ids=[],
        product_ids=[],
        responsible_ids=[],
        workflow_statuses=[],
    )
    assert UnifiedFilterService.build_university_conditions(f) == []


def test_null_lists_normalize_to_empty():
    f = UnifiedFilter.model_validate(
        {
            "university_ids": None,
            "direction_ids": None,
            "program_ids": None,
            "product_ids": None,
            "responsible_ids": None,
            "workflow_statuses": None,
        }
    )
    assert f.university_ids == []
    assert f.workflow_statuses == []


# ------------------------------------------------------------------- all fields


def test_valid_all_fields():
    f = UnifiedFilter(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        university_ids=[A, B],
        direction_ids=[A],
        program_ids=[B],
        product_ids=[C],
        responsible_ids=[A],
        workflow_statuses=[WorkflowStageStatus.PENDING, WorkflowStageStatus.COMPLETED],
    )
    assert f.date_from == date(2026, 1, 1)
    assert f.date_to == date(2026, 12, 31)
    assert f.university_ids == [A, B]
    assert f.workflow_statuses == [
        WorkflowStageStatus.PENDING,
        WorkflowStageStatus.COMPLETED,
    ]
    # date_from + date_to + 5 id dims + workflow = 8 AND-combined predicates.
    assert len(UnifiedFilterService.build_university_conditions(f)) == 8


def test_date_from_only_and_date_to_only():
    assert UnifiedFilter(date_from=date(2026, 3, 1)).date_to is None
    assert UnifiedFilter(date_to=date(2026, 3, 1)).date_from is None
    assert len(
        UnifiedFilterService.build_university_conditions(
            UnifiedFilter(date_from=date(2026, 3, 1))
        )
    ) == 1


def test_valid_range_single_day():
    f = UnifiedFilter(date_from=date(2026, 5, 5), date_to=date(2026, 5, 5))
    assert f.date_from == f.date_to


def test_invalid_reversed_range_rejected():
    with pytest.raises(ValidationError) as exc_info:
        UnifiedFilter(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))
    assert "date_from" in str(exc_info.value)


# ------------------------------------------------------------------ id lists


def test_multiple_ids_kept():
    f = UnifiedFilter(university_ids=[A, B, C])
    assert f.university_ids == [A, B, C]


def test_duplicate_ids_deduplicated_preserving_order():
    f = UnifiedFilter(university_ids=[A, A, B, A, B, C])
    assert f.university_ids == [A, B, C]
    g = UnifiedFilter(
        direction_ids=[B, B],
        program_ids=[C, C, C],
        product_ids=[A, A],
        responsible_ids=[B, A, B],
        workflow_statuses=["pending", "pending", "completed"],
    )
    assert g.direction_ids == [B]
    assert g.program_ids == [C]
    assert g.product_ids == [A]
    assert g.responsible_ids == [B, A]
    assert g.workflow_statuses == [
        WorkflowStageStatus.PENDING,
        WorkflowStageStatus.COMPLETED,
    ]


# -------------------------------------------------------------- round-trips


def test_json_round_trip_identical():
    f = UnifiedFilter(
        date_from=date(2026, 1, 10),
        date_to=date(2026, 9, 20),
        university_ids=[A, B],
        direction_ids=[C],
        program_ids=[],
        product_ids=[A],
        responsible_ids=[B],
        workflow_statuses=[WorkflowStageStatus.OVERDUE],
    )
    payload = json.loads(f.model_dump_json())
    assert payload["university_ids"] == [str(A), str(B)]
    assert payload["date_from"] == "2026-01-10"
    assert payload["workflow_statuses"] == ["overdue"]
    back = UnifiedFilter.model_validate(payload)
    assert back == f
    assert UnifiedFilter.model_validate(f.model_dump(mode="json")) == f


def test_query_body_parse_equivalence():
    body = {
        "date_from": "2026-01-01",
        "date_to": "2026-06-30",
        "university_ids": [str(A), str(B)],
        "direction_ids": [],
        "program_ids": [str(C)],
        "product_ids": [],
        "responsible_ids": [],
        "workflow_statuses": ["pending"],
    }
    from_body = UnifiedFilter.model_validate(body)
    from_query = get_unified_filter(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 6, 30),
        university_ids=[A, B],
        direction_ids=None,
        program_ids=[C],
        product_ids=None,
        responsible_ids=None,
        workflow_statuses=[WorkflowStageStatus.PENDING],
    )
    assert from_query == from_body


# ---------------------------------------------------------- query dependency


def test_query_defaults_parse_to_empty_filter(probe_client):
    r = probe_client.get("/probe")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "date_from": None,
        "date_to": None,
        "university_ids": [],
        "direction_ids": [],
        "program_ids": [],
        "product_ids": [],
        "responsible_ids": [],
        "workflow_statuses": [],
    }


def test_query_multi_select_repeated_params(probe_client):
    r = probe_client.get(
        f"/probe?university_ids={A}&university_ids={B}"
        f"&direction_ids={C}&workflow_statuses=pending&workflow_statuses=completed"
        "&date_from=2026-01-01&date_to=2026-12-31"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["university_ids"] == [str(A), str(B)]
    assert body["direction_ids"] == [str(C)]
    assert body["workflow_statuses"] == ["pending", "completed"]
    assert body["date_from"] == "2026-01-01"
    assert body["date_to"] == "2026-12-31"


def test_query_duplicate_ids_deduplicated(probe_client):
    r = probe_client.get(f"/probe?university_ids={A}&university_ids={A}")
    assert r.status_code == 200, r.text
    assert r.json()["university_ids"] == [str(A)]


def test_query_invalid_uuid_is_422(probe_client):
    r = probe_client.get("/probe?university_ids=not-a-uuid")
    assert r.status_code == 422, r.text


def test_query_invalid_workflow_status_is_422(probe_client):
    r = probe_client.get("/probe?workflow_statuses=bogus")
    assert r.status_code == 422, r.text


def test_query_invalid_date_is_422(probe_client):
    r = probe_client.get("/probe?date_from=2026-13-99")
    assert r.status_code == 422, r.text


def test_query_reversed_range_is_422_not_500(probe_client):
    r = probe_client.get("/probe?date_from=2026-05-01&date_to=2026-01-01")
    assert r.status_code == 422, r.text
    assert r.json()["detail"]


def test_dependency_direct_reversed_range_is_422():
    with pytest.raises(HTTPException) as exc_info:
        get_unified_filter(date_from=date(2026, 5, 1), date_to=date(2026, 1, 1))
    assert exc_info.value.status_code == 422


# ------------------------------------------------------------ workflow enum


def test_workflow_status_reuses_frozen_enum():
    assert WorkflowFilterStatus is WorkflowStageStatus
    assert {s.value for s in WorkflowStageStatus} == {
        "pending",
        "current",
        "completed",
        "skipped",
        "overdue",
    }
    f = UnifiedFilter(workflow_statuses=["pending", "overdue"])
    assert f.workflow_statuses == [
        WorkflowStageStatus.PENDING,
        WorkflowStageStatus.OVERDUE,
    ]


def test_workflow_status_invalid_rejected():
    with pytest.raises(ValidationError):
        UnifiedFilter(workflow_statuses=["active"])
    with pytest.raises(ValidationError):
        UnifiedFilter(workflow_statuses=["done"])


# --------------------------------------------------------------- openapi/schema


def test_json_schema_exposes_all_eight_dimensions():
    schema = UnifiedFilter.model_json_schema()
    assert sorted(schema["properties"].keys()) == [
        "date_from",
        "date_to",
        "direction_ids",
        "product_ids",
        "program_ids",
        "responsible_ids",
        "university_ids",
        "workflow_statuses",
    ]
    date_schema = schema["properties"]["date_from"]
    date_variants = date_schema.get("anyOf", [date_schema])
    assert any(v.get("format") == "date" for v in date_variants)
    assert "example" in schema


def test_probe_openapi_lists_filter_params(probe_client):
    spec = probe_client.get("/openapi.json")
    assert spec.status_code == 200
    params = {
        p["name"]
        for p in spec.json()["paths"]["/probe"]["get"].get("parameters", [])
    }
    assert {
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
    } <= params


# ------------------------------------------------------- predicate construction


def test_predicates_use_exists_not_join_fanout():
    f = UnifiedFilter(direction_ids=[A], responsible_ids=[B])
    stmt = UnifiedFilterService.apply_to_universities(select(University), f)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "EXISTS" in compiled.upper()
    # No JOIN in the OUTER query (the direction path joins two link tables
    # only inside its EXISTS subquery, so universities never fan out).
    outer = compiled.upper().split("WHERE", 1)[0]
    assert "JOIN" not in outer
    assert "FROM UNIVERSITIES" in outer


def test_combined_predicates_count_matches_dimensions():
    f = UnifiedFilter(
        university_ids=[A],
        direction_ids=[A],
        program_ids=[A],
        product_ids=[A],
        responsible_ids=[A],
        workflow_statuses=[WorkflowStageStatus.PENDING],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )
    assert len(UnifiedFilterService.build_university_conditions(f)) == 8


# ------------------------------------------------------------- security scope


def test_security_scope_admin_keeps_global():
    stmt = select(University)
    admin = CurrentUser(id="a", roles={"admin"})
    assert UnifiedFilterService.apply_security_scope(stmt, admin) is stmt


def test_security_scope_none_claim_keeps_global():
    stmt = select(University)
    user = CurrentUser(id="u", roles={"user"})
    assert UnifiedFilterService.apply_security_scope(stmt, user) is stmt


def test_security_scope_confines_scoped_user():
    stmt = UnifiedFilterService.apply_security_scope(
        select(University),
        CurrentUser(id="u", roles={"user"}, university_ids=(str(A),)),
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert A.hex in compiled.replace("-", "")


def test_security_scope_empty_after_parsing_fails_closed():
    stmt = UnifiedFilterService.apply_security_scope(
        select(University),
        CurrentUser(id="u", roles={"user"}, university_ids=("not-a-uuid",)),
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FALSE" in compiled.upper()


# ------------------------------------------------------- public contract file


def test_public_contract_artifact_matches_dto():
    root = Path(__file__).resolve().parents[2]
    contract_path = root / "docs" / "contracts" / "unified-filter.json"
    assert contract_path.exists(), "docs/contracts/unified-filter.json must exist"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    example = contract["example"]
    assert UnifiedFilter.model_validate(example) == UnifiedFilter()
    assert set(contract["allowed_workflow_statuses"].keys()) == {
        s.value for s in WorkflowStageStatus
    }
    assert set(contract["query_params"]["names"]) == {
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
    }
    assert contract["combination"] == {
        "between_dimensions": "AND",
        "within_dimension": "OR / IN",
    }

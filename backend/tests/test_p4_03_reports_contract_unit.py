"""P4-03-01 / P4-04 / P4-05 / P4-06-01 contract tests (no DB).

P4-06-01 LANDED: persistent ``ReportJob`` storage (migration 000018) +
``BackgroundTasks`` worker exist, the router is MOUNTED in the production
``v1`` router, and ``create_report_job`` persists a real ``queued`` job
(live 202 paths are pinned by ``test_p4_06_report_jobs_pg.py``).

These tests pin without a database: the frozen ``202`` response shape,
the persistence payload (filters + columns + format + actor scope), the
three-format gate (xlsx/pdf/json share one path), the worker dispatch
table, RBAC (401/403), validation (422), the mounted OpenAPI shape
(3 paths, unique operation ids) and the public contracts/mocks.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import CurrentUser, get_current_user
from app.core.errors import register_error_handlers
from app.schemas.errors import ErrorCode, ErrorResponse
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import (
    FORMAT_GENERATORS,
    ReportQueuedResponse,
    build_job_payload,
    ensure_supported_format,
    ensure_xlsx,
    generate_report_file,
)
from app.modules.analytics.reports_router import (
    ReportJobRead,
    SUPPORTED_FORMATS,
    router,
)
from app.schemas.common import ReportFormat


def _admin() -> CurrentUser:
    return CurrentUser(id="admin-1", roles={"admin"})


def _scoped() -> tuple[CurrentUser, object]:
    uid = uuid4()
    user = CurrentUser(id="scoped-1", roles={"manager"}, university_ids=(str(uid),))
    return user, uid


def _app(user: CurrentUser | None) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------- queued response shape


def test_queued_response_frozen_shape():
    body = ReportQueuedResponse(job_id=str(uuid4()), status="queued")
    assert body.model_dump() == {"job_id": body.job_id, "status": "queued"}


# ------------------------------------------------------- payload builder


def test_build_job_payload_persists_filters_columns_format_and_scope():
    user, uid = _scoped()
    req = ReportRequest(
        format="xlsx",
        filters={"university_ids": [str(uid)]},
        columns=["university", "comment", "university"],
    )
    payload = build_job_payload(req, user)
    assert payload["format"] == "xlsx"
    assert payload["filters"]["university_ids"] == [str(uid)]
    assert payload["columns"] == ["university", "comment"]
    assert payload["actor"]["sub"] == "scoped-1"
    assert payload["actor"]["roles"] == ["manager"]
    assert payload["actor"]["university_ids"] == [str(uid)]


def test_build_job_payload_default_columns_and_global_scope():
    payload = build_job_payload(ReportRequest(format="xlsx"), _admin())
    from app.modules.analytics.columns import DEFAULT_COLUMNS

    assert payload["columns"] == list(DEFAULT_COLUMNS)
    assert payload["actor"]["university_ids"] is None


def test_grouping_is_validated_and_frozen_with_the_job():
    request = ReportRequest(format="xlsx", group_by="program", columns=["university", "program"])
    payload = build_job_payload(request, _admin())
    assert payload["filters"]["_group_by"] == "program"
    assert ReportRequest(format="xlsx", filters=payload["filters"], group_by=payload["filters"]["_group_by"]).group_by == "program"
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        ReportRequest(format="xlsx", group_by="unknown")


def test_build_job_payload_identical_shape_for_all_formats():
    for fmt in ("xlsx", "pdf", "json"):
        payload = build_job_payload(ReportRequest(format=fmt), _admin())
        assert payload["format"] == fmt
        assert set(payload) == {"format", "filters", "columns", "actor"}
        assert set(payload["filters"]) == {
            "date_from",
            "date_to",
            "university_ids",
            "direction_ids",
            "program_ids",
            "product_ids",
            "responsible_ids",
            "workflow_statuses",
        }


# ------------------------------------------------------- format gate + dispatch


def test_ensure_supported_format_accepts_all_three():
    for fmt in ("xlsx", "pdf", "json"):
        ensure_supported_format(ReportRequest(format=fmt))


def test_format_generators_cover_all_formats_with_shared_signature():
    import inspect

    assert set(FORMAT_GENERATORS) == {
        ReportFormat.XLS,
        ReportFormat.XLSX,
        ReportFormat.PDF,
        ReportFormat.JSON,
    }
    for generate in FORMAT_GENERATORS.values():
        params = list(inspect.signature(generate).parameters)
        assert params[:4] == ["db", "filters", "columns", "output_path"]


def test_generate_report_file_dispatches_per_format(tmp_path):
    calls: list[str] = []

    def _fake(kind: str):
        def _gen(db, filters, columns, output_path, **kw):
            from app.modules.analytics.xlsx import GeneratedReport

            calls.append(kind)
            out = tmp_path / f"{kind}.bin"
            out.write_bytes(b"x")
            from datetime import datetime, timezone

            return GeneratedReport(
                path=out,
                size_bytes=1,
                row_count=0,
                generated_at=datetime.now(timezone.utc),
                columns=list(columns),
            )

        return _gen

    import pytest

    monkey = pytest.MonkeyPatch()
    monkey.setitem(FORMAT_GENERATORS, ReportFormat.XLSX, _fake("xlsx"))
    monkey.setitem(FORMAT_GENERATORS, ReportFormat.PDF, _fake("pdf"))
    monkey.setitem(FORMAT_GENERATORS, ReportFormat.JSON, _fake("json"))
    try:
        for fmt in ("xlsx", "pdf", "json"):
            generate_report_file(object(), ReportRequest(format=fmt), tmp_path / f"out.{fmt}")
    finally:
        monkey.undo()
    assert calls == ["xlsx", "pdf", "json"]


def test_generate_report_file_passes_grouping_to_existing_generator(tmp_path, monkeypatch):
    seen = []

    def generate(db, filters, columns, output_path, **kwargs):
        seen.append(kwargs["group_by"])
        return object()

    monkeypatch.setitem(FORMAT_GENERATORS, ReportFormat.XLSX, generate)
    generate_report_file(object(), ReportRequest(format="xlsx", group_by="direction"), tmp_path / "grouped.xlsx")
    assert seen == ["direction"]


def test_supported_formats_router_matches_service():
    assert SUPPORTED_FORMATS == frozenset(FORMAT_GENERATORS), (
        "the router must accept exactly the formats that have a generator"
    )


def test_ensure_xlsx_rejects_other_formats():
    import pytest

    ensure_xlsx(ReportRequest(format="xlsx"))
    with pytest.raises(ValueError, match="unsupported report format"):
        ensure_xlsx(ReportRequest(format="pdf"))
    with pytest.raises(ValueError, match="unsupported report format"):
        ensure_xlsx(ReportRequest(format="json"))


# ------------------------------------------------------- router RBAC / validation


def test_router_401_without_token():
    client = _app(None)
    resp = client.post("/reports", json={"format": "xlsx"})
    assert resp.status_code == 401
    assert ErrorResponse.model_validate(resp.json()).error.code == ErrorCode.AUTH_REQUIRED


def test_router_user_report_permission_reaches_validation():
    user = CurrentUser(id="u-1", roles={"user"})
    resp = _app(user).post("/reports", json={"format": "xlsx", "columns": ["bogus"]})
    assert resp.status_code == 422


def test_router_403_for_curator_without_reports_read():
    user = CurrentUser(id="c-1", roles={"curator"})  # no reports.read in canon
    resp = _app(user).post("/reports", json={"format": "xlsx"})
    assert resp.status_code == 403
    assert ErrorResponse.model_validate(resp.json()).error.code == ErrorCode.FORBIDDEN


def test_router_422_unknown_column():
    resp = _app(_admin()).post(
        "/reports", json={"format": "xlsx", "columns": ["university", "bogus"]}
    )
    assert resp.status_code == 422


def test_router_422_empty_columns():
    resp = _app(_admin()).post("/reports", json={"format": "xlsx", "columns": []})
    assert resp.status_code == 422


def test_router_422_unknown_format():
    resp = _app(_admin()).post("/reports", json={"format": "csv"})
    assert resp.status_code == 422


def test_router_get_401_without_token():
    assert _app(None).get(f"/reports/{uuid4()}").status_code == 401


def test_router_download_401_without_token():
    assert _app(None).get(f"/reports/{uuid4()}/download").status_code == 401


# ------------------------------------------------------- mounted production API


def test_production_v1_mounts_reports_routes():
    # Asserted through the served OpenAPI: recent FastAPI versions keep
    # lazy _IncludedRouter placeholders on router objects, while the
    # served app always materializes them (proven by live /openapi.json).
    from app.main import app

    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/reports"]) >= {"post"}
    assert set(paths["/api/v1/reports/{job_id}"]) >= {"get"}
    assert set(paths["/api/v1/reports/{job_id}/download"]) >= {"get"}


def test_router_openapi_paths_and_unique_operation_ids():
    from app.main import app

    spec = app.openapi()
    paths = spec["paths"]
    assert "/api/v1/reports" in paths
    assert "/api/v1/reports/{job_id}" in paths
    assert "/api/v1/reports/{job_id}/download" in paths
    post = paths["/api/v1/reports"]["post"]
    assert post["responses"]["202"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ReportQueuedResponse"
    )
    assert "501" not in post["responses"]
    seen: dict[str, str] = {}
    for path, item in paths.items():
        for method, op in item.items():
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            op_id = op["operationId"]
            assert op_id not in seen, f"duplicate operationId {op_id}: {seen[op_id]} vs {method} {path}"
            seen[op_id] = f"{method} {path}"
    report_ops = {
        seen[op["operationId"]]
        for path in (
            "/api/v1/reports",
            "/api/v1/reports/{job_id}",
            "/api/v1/reports/{job_id}/download",
        )
        for method, op in paths[path].items()
        if isinstance(op, dict) and "operationId" in op
    }
    assert report_ops == {
        "get /api/v1/reports",
        "post /api/v1/reports",
        "get /api/v1/reports/{job_id}",
        "get /api/v1/reports/{job_id}/download",
    }


def test_report_format_enum_still_single_source():
    assert {m.value for m in ReportFormat} == {"xls", "xlsx", "pdf", "json"}


def test_report_job_read_never_exposes_filesystem_path():
    fields = set(ReportJobRead.model_fields)
    assert fields == {
        "id",
        "format",
        "status",
        "progress",
        "file_size",
        "created_at",
        "started_at",
        "completed_at",
        "expires_at",
        "error_message",
    }
    assert "file_path" not in fields


def test_public_report_request_contract_matches_code():
    from app.modules.analytics.columns import DEFAULT_COLUMNS

    root = Path(__file__).resolve().parents[2]
    contract_path = root / "docs" / "contracts" / "report-request.json"
    assert contract_path.exists(), "docs/contracts/report-request.json must exist"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["example"]["format"] == "xlsx"
    assert contract["example"]["columns"] == list(DEFAULT_COLUMNS)
    assert set(contract["request"]["format"]["values"]) == {"xls", "xlsx", "pdf", "json"}
    assert contract["async_api"]["endpoint"] == "POST /api/v1/reports"
    assert contract["async_api"]["success"] == "202 Accepted"
    assert contract["async_api"]["success_body"] == {
        "job_id": "uuid",
        "status": "queued",
    }
    assert "BLOCKED_BY_P4_06_01" not in json.dumps(contract)
    assert contract["async_api"]["lifecycle"].startswith("queued -> building -> ready")
    assert contract["xlsx_workbook"]["freeze_panes"] == "A7"
    assert contract["xlsx_workbook"]["header_row"] == 6


def test_public_report_output_contract_covers_job_lifecycle():
    root = Path(__file__).resolve().parents[2]
    contract_path = root / "docs" / "contracts" / "report-output.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    lifecycle = contract["job_lifecycle"]
    assert lifecycle["states"] == ["queued", "building", "ready", "failed"]
    assert lifecycle["download"]["expired_or_missing_file"] == "410 Gone"
    assert lifecycle["media_types"]["xlsx"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_report_job_mock_matches_read_schema():
    root = Path(__file__).resolve().parents[1]
    mock_path = root / "docs" / "mocks" / "report-job.json"
    assert mock_path.exists(), "backend/docs/mocks/report-job.json must exist"
    mock = json.loads(mock_path.read_text(encoding="utf-8"))
    assert mock["create_response"]["status"] == "queued"
    ok = ReportJobRead.model_validate(mock["status_response"])
    assert ok.status == "ready" and ok.progress == 100
    failed = ReportJobRead.model_validate(mock["failed_status_response"])
    assert failed.status == "failed" and failed.error_message
    assert mock["lifecycle"] == ["queued", "building", "ready", "failed"]

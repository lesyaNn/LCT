"""L14: mocks exist once, in canonical places, schema-valid.

Canonical map (see ``backend/docs/mocks/README.md``):
* ``docs/mocks/``: university-passport, analytics-overview + report-request
  (static etalons, no generator);
* ``backend/docs/mocks/``: workflow-instance (generated), report-job
  (static etalon, no generator).

Also pins: no ``university-passport.json`` duplicate under
``backend/docs/mocks/`` (drift of doubles removed in Dev-3).

Pure-unit: no database, no Keycloak.
"""

import json
import os

ROOT_MOCKS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "mocks",
)
BACKEND_MOCKS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "mocks"
)


def _load(base: str, name: str) -> dict:
    path = os.path.join(base, name)
    assert os.path.exists(path), f"missing mock file: {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_no_university_passport_duplicate():
    dup = os.path.join(BACKEND_MOCKS, "university-passport.json")
    assert not os.path.exists(dup), (
        f"duplicate mock must not come back: {dup} "
        "(canonical location is docs/mocks/university-passport.json)"
    )


def test_p1_passport_mocks_valid():
    from app.schemas import UniversityPassport

    UniversityPassport.model_validate(_load(ROOT_MOCKS, "university-passport.json"))


def test_analytics_overview_mock_valid():
    from app.modules.analytics.schemas import Overview

    Overview.model_validate(_load(ROOT_MOCKS, "analytics-overview.json"))


def test_report_request_mock_valid():
    from app.modules.analytics.report_request import ReportRequest

    ReportRequest.model_validate(_load(ROOT_MOCKS, "report-request.json"))


def test_p2_mocks_valid():
    from app.modules.workflow_instances.schemas import InstanceDetail

    InstanceDetail.model_validate(_load(BACKEND_MOCKS, "workflow-instance.json"))


def test_report_job_mock_present_and_shaped():
    # Full ReportJobRead validation lives in test_p4_03_reports_contract_unit;
    # here we only pin presence + lifecycle shape (no generator exists).
    mock = _load(BACKEND_MOCKS, "report-job.json")
    assert mock["lifecycle"] == ["queued", "building", "ready", "failed"]
    assert mock["create_response"]["status"] == "queued"

"""P5-06 unified error contract checks (database independent)."""

import json
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.core.errors import BusinessException, register_error_handlers
from app.main import app
from app.schemas.errors import ERROR_MESSAGES, ERROR_STATUS_MAP, ErrorCode, ErrorResponse


def test_registry_has_status_and_message_for_every_code():
    assert set(ERROR_STATUS_MAP) == set(ErrorCode)
    assert set(ERROR_MESSAGES) == set(ErrorCode)
    assert all(isinstance(value, int) for value in ERROR_STATUS_MAP.values())


def test_document_matches_runtime_registry():
    root = Path(__file__).resolve().parents[2]
    document = json.loads((root / "docs/contracts/security-errors.json").read_text(encoding="utf-8"))
    assert set(document["codes"]) == {code.value for code in ErrorCode}
    assert document["http_status"] == {code.value: status for code, status in ERROR_STATUS_MAP.items()}
    assert document["messages"] == {code.value: message for code, message in ERROR_MESSAGES.items()}


def test_unknown_route_and_method_not_allowed_are_enveloped():
    client = TestClient(app)
    missing = client.get("/route-that-does-not-exist")
    assert missing.status_code == 404
    assert set(missing.json()) == {"error"}
    assert missing.json()["error"]["code"] == ErrorCode.NOT_FOUND
    wrong_method = client.post("/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == ErrorCode.METHOD_NOT_ALLOWED


def test_validation_fields_are_stable_and_safe():
    api = FastAPI()
    register_error_handlers(api)

    class Payload(BaseModel):
        email: str = Field(pattern=r"^[^@]+@[^@]+$")
        password: str

    @api.post("/payload")
    def payload(value: Payload):
        return value

    response = TestClient(api).post("/payload", json={"email": "bad", "password": "secret"})
    assert response.status_code == 422
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == ErrorCode.VALIDATION_ERROR
    assert {"field", "message", "type"} <= set(body.error.details["field_errors"][0])
    assert "secret" not in response.text
    UUID(response.headers["X-Request-ID"])


def test_business_exception_uses_registry_status():
    assert BusinessException(ErrorCode.REPORT_NOT_READY).status_code == 400
    assert BusinessException(ErrorCode.GONE).status_code == 410


def test_http_error_code_is_explicit_not_guessed_from_message():
    api = FastAPI()
    register_error_handlers(api)

    @api.get("/typed")
    def typed():
        raise HTTPException(
            status_code=400,
            detail={"code": "WORKFLOW_INVALID_TRANSITION", "details": {}},
        )

    @api.get("/prose")
    def prose():
        raise HTTPException(status_code=400, detail="invalid workflow transition")

    client = TestClient(api)
    assert client.get("/typed").json()["error"]["code"] == "WORKFLOW_INVALID_TRANSITION"
    assert client.get("/prose").json()["error"]["code"] == "HTTP_ERROR"


def test_integrity_conflict_exposes_only_safe_field():
    class Diagnostic:
        constraint_name = "uq_students_external_id"
        column_name = None

    class DriverError(Exception):
        diag = Diagnostic()

    api = FastAPI()
    register_error_handlers(api)

    @api.get("/duplicate")
    def duplicate():
        raise IntegrityError("private sql", {"external_id": "secret"}, DriverError())

    response = TestClient(api, raise_server_exceptions=False).get("/duplicate")
    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"field": "external_id"}
    assert "private sql" not in response.text
    assert "secret" not in response.text

"""No DB/LLM required: contract, SQL boundaries, authorization and PDF layout."""

import io
import time
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy.dialects import postgresql

from app.core.errors import BusinessException, register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.models.workflow_instances import WorkflowComment
from app.modules.audit.service import _comment_snapshot
from app.modules.meeting_agenda import router as routes
from app.modules.meeting_agenda import service
from app.modules.meeting_agenda.pdf import PDF_ROWS, _paragraph, generate_agenda_pdf
from app.modules.meeting_agenda.schemas import MeetingAgenda
from app.modules.workflow_transitions.schemas import WorkflowCommentCreate, WorkflowQuestionUpdate


def sample_agenda(*, count=2, long_text=False):
    """Synthetic data only; also used by the local visual preview."""
    uid, iid, sid = uuid4(), uuid4(), uuid4()
    today = date(2026, 10, 16)
    now = datetime(2026, 10, 16, 10, 30, tzinfo=UTC)
    names = ["Разработка корпоративных приложений", "Информационная безопасность"]
    suffix = (" <скрипт> & очень длинный текст " * 350) if long_text else ""
    return MeetingAgenda(
        university_id=uid,
        university_name="Московский технический университет" + suffix,
        city="Москва",
        instance_id=iid,
        stage_id=sid,
        stage_name="Организация встречи" + suffix,
        stage_order=3,
        generated_at=now,
        as_of=today,
        expires_through=today + timedelta(days=30),
        warning_days=30,
        programs={
            "items": [
                {
                    "program_id": uuid4(),
                    "name": names[i % 2] + suffix,
                    "direction": "ИТ и цифровые технологии",
                    "status": "active",
                    "launch_date": date(2026, 9, 1),
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
        expiring_licenses={
            "items": [
                {
                    "license_id": uuid4(),
                    "license_number": f"ЛЦТ-{i + 1:03}" + suffix,
                    "product": "Платформа учебных лабораторий" + suffix,
                    "expires_at": today + timedelta(days=i % 31),
                    "days_left": i % 31,
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
        open_questions={
            "items": [
                {
                    "comment_id": uuid4(),
                    "instance_id": iid,
                    "stage_id": None,
                    "content": [
                        "Кто согласует продление лицензий на следующий семестр?",
                        "Нужно уточнить сроки запуска новой программы.",
                    ][i % 2]
                    + suffix,
                    "created_at": now,
                }
                for i in range(count)
            ],
            "total": count,
            "omitted": 0,
        },
    )


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class ScriptedDB:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []
        self.info = {}

    def execute(self, statement):
        self.statements.append(statement)
        return Rows(self.results.pop(0))


def admin():
    return CurrentUser(id="admin", roles={"admin"})


def _db(*, order=3, status="active", university_id=None):
    return ScriptedDB(
        [
            {
                "university_id": university_id or uuid4(),
                "status": status,
                "current_instance_stage_id": uuid4(),
            }
        ],
        [{"id": uuid4(), "name": "Встреча", "order_index": order}],
        [{"name": "Вуз", "city": "Москва"}],
        [],
        [],
        [],
    )


def test_service_empty_has_bounded_queries_and_same_date_window():
    db = _db()
    result = service.build_agenda(db, uuid4(), admin())
    assert (
        result.programs.total == result.expiring_licenses.total == result.open_questions.total == 0
    )
    assert (result.expires_through - result.as_of).days == 30
    assert result.generated_at.tzinfo is not None
    assert len(db.statements) == 6
    sql = [s.compile(dialect=postgresql.dialect()) for s in db.statements]
    assert all("LIMIT" in str(s) and "count(*) OVER ()" in str(s) for s in sql[-3:])
    assert all(service.PREVIEW_LIMIT in s.params.values() for s in sql[-3:])
    assert "university_programs.university_id" in str(sql[3])
    assert ["active", "launched"] in sql[3].params.values()
    assert "licenses.university_id" in str(sql[4])
    assert "BETWEEN" in str(sql[4])
    assert (
        result.as_of in sql[4].params.values() and result.expires_through in sql[4].params.values()
    )
    assert "workflow_instances.university_id" in str(sql[5])
    assert "archived" in sql[5].params.values() and "open" in sql[5].params.values()


def test_section_reports_omissions_and_license_days():
    today = datetime.now(UTC).date()
    db = _db()
    row = {
        "license_id": uuid4(),
        "license_number": "1",
        "product": "ИТ-продукт",
        "expires_at": today + timedelta(days=30),
        "_total": 107,
    }
    db.results[-2] = [row] * 100
    result = service.build_agenda(db, uuid4(), admin())
    assert len(result.expiring_licenses.items) == 100
    assert result.expiring_licenses.total == 107
    assert result.expiring_licenses.omitted == 7
    assert result.expiring_licenses.items[0].days_left == 30


@pytest.mark.parametrize(
    "order,status", [(1, "active"), (2, "active"), (4, "active"), (3, "completed"), (3, "archived")]
)
def test_only_active_third_stage(order, status):
    db = _db(order=order, status=status)
    with pytest.raises(BusinessException) as caught:
        service.build_agenda(db, uuid4(), admin())
    assert caught.value.status_code == 409
    assert caught.value.details["reason"] == "meeting_agenda_requires_stage_3"
    assert len(db.statements) == 2


@pytest.mark.parametrize("roles,ids", [({"user"}, None), ({"manager"}, ()), ({"curator"}, None)])
def test_foreign_scope_never_loads_sections(roles, ids):
    db = _db()
    with pytest.raises(BusinessException) as caught:
        service.build_agenda(db, uuid4(), CurrentUser(id="other", roles=roles, university_ids=ids))
    assert caught.value.status_code == 404
    assert len(db.statements) == 1


def test_missing_instance():
    with pytest.raises(BusinessException) as caught:
        service.build_agenda(ScriptedDB([]), uuid4(), admin())
    assert caught.value.status_code == 404


def test_comment_contract_backward_compatible_and_explicit():
    assert not WorkflowCommentCreate(content="Вопрос?").is_question
    assert WorkflowCommentCreate(content="Обсудить сроки", is_question=True).is_question
    for status in ("none", "open", "resolved"):
        assert WorkflowQuestionUpdate(status=status).status == status
    with pytest.raises(ValidationError):
        WorkflowQuestionUpdate(status="anything")
    comment = WorkflowComment(instance_id=uuid4(), content="Private text", question_status="open")
    snapshot = _comment_snapshot(comment)
    assert snapshot["question_status"] == "open"
    assert "Private text" not in str(snapshot)
    comment.question_status = None  # ORM defaults haven't fired before_flush
    assert _comment_snapshot(comment)["question_status"] == "none"


@pytest.mark.parametrize(
    "actor,role", [("author", "user"), ("other", "manager"), ("other", "admin")]
)
def test_status_lifecycle_has_no_content_edit_window(actor, role):
    uid = uuid4()
    db = _db()
    db.results = [
        [{"instance_id": uuid4(), "author_keycloak_sub": "author"}],
        [{"university_id": uid, "status": "active"}],
    ]
    # The content may be old and belong to a previous stage. Neither is edited.
    comment = SimpleNamespace(
        content="старый вопрос", question_status="open", created_at=datetime(2020, 1, 1, tzinfo=UTC)
    )
    db.get, db.commit, db.refresh = Mock(return_value=comment), Mock(), Mock()
    user = CurrentUser(id=actor, roles={role}, university_ids=(str(uid),))
    assert service.set_question_status(db, uuid4(), "resolved", user) is comment
    assert comment.question_status == "resolved" and comment.content == "старый вопрос"
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "foreign,archived,expected", [(False, False, 403), (True, False, 404), (False, True, 409)]
)
def test_status_gates(foreign, archived, expected):
    uid = uuid4()
    db = ScriptedDB(
        [{"instance_id": uuid4(), "author_keycloak_sub": "author"}],
        [{"university_id": uid, "status": "archived" if archived else "active"}],
    )
    user = CurrentUser(
        id="author" if archived else "stranger",
        roles={"user"},
        university_ids=() if foreign else (str(uid),),
    )
    with pytest.raises(BusinessException) as caught:
        service.set_question_status(db, uuid4(), "resolved", user)
    assert caught.value.status_code == expected


@pytest.fixture()
def client(monkeypatch):
    application = FastAPI()
    application.include_router(routes.router, prefix="/api/v1")
    register_error_handlers(application)
    db = Mock(info={})
    application.dependency_overrides[routes.get_audit_db] = lambda: db
    application.dependency_overrides[get_current_user] = admin
    agenda = sample_agenda()
    monkeypatch.setattr(service, "build_agenda", Mock(return_value=agenda))
    return TestClient(application), application, db, agenda


def test_json_response(client):
    client, _, db, agenda = client
    response = client.get(f"/api/v1/workflow/instances/{agenda.instance_id}/meeting-agenda")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["stage_order"] == 3
    assert response.json()["open_questions"]["total"] == 2
    db.commit.assert_not_called()


def test_production_contract_is_mounted():
    from app.main import app

    paths = app.openapi()["paths"]
    base = "/api/v1/workflow/instances/{instance_id}/meeting-agenda"
    assert base in paths
    assert "application/pdf" in paths[base + ".pdf"]["get"]["responses"]["200"]["content"]
    assert "/api/v1/workflow/comments/{comment_id}/question-status" in paths


def test_question_status_route_uses_audit_context():
    def dependency_names(node):
        names = set()
        for child in node.dependencies:
            names.add(getattr(child.call, "__name__", ""))
            names.update(dependency_names(child))
        return names

    route = next(r for r in routes.router.routes if "PATCH" in r.methods)
    assert "get_audit_db" in dependency_names(route.dependant)


def test_pdf_response_and_safe_audit(client, monkeypatch):
    client, _, db, agenda = client
    monkeypatch.setattr(routes, "generate_agenda_pdf", lambda _: b"%PDF-test")
    response = client.get(f"/api/v1/workflow/instances/{agenda.instance_id}/meeting-agenda.pdf")
    assert response.status_code == 200 and response.content == b"%PDF-test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("attachment;")
    db.commit.assert_called_once()
    event = db.add.call_args.args[0]
    assert event.action == "REPORT_GENERATE" and event.university_id == agenda.university_id
    assert event.new_value["open_question_count"] == 2
    assert "согласует" not in str(event.new_value)


def test_failed_pdf_no_audit_or_commit(client, monkeypatch):
    client, _, db, agenda = client
    monkeypatch.setattr(routes, "generate_agenda_pdf", Mock(side_effect=RuntimeError("private")))
    response = client.get(f"/api/v1/workflow/instances/{agenda.instance_id}/meeting-agenda.pdf")
    assert response.status_code == 500 and response.json()["error"]["code"] == "REPORT_FAILED"
    assert "private" not in response.text
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("suffix", ["", ".pdf"])
def test_unknown_role_cannot_read(client, suffix):
    client, application, _, agenda = client
    application.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="unknown", roles={"curator"}
    )
    response = client.get(f"/api/v1/workflow/instances/{agenda.instance_id}/meeting-agenda{suffix}")
    assert response.status_code == 403
    service.build_agenda.assert_not_called()


def test_question_route_and_invalid_status(client, monkeypatch):
    client, _, _, _ = client
    now = datetime.now(UTC)
    comment = WorkflowComment(
        id=uuid4(),
        instance_id=uuid4(),
        author_keycloak_sub="author",
        content="Вопрос",
        is_internal=True,
        question_status="resolved",
        created_at=now,
        updated_at=now,
        attachments=[],
    )
    setter = Mock(return_value=comment)
    monkeypatch.setattr(service, "set_question_status", setter)
    url = f"/api/v1/workflow/comments/{comment.id}/question-status"
    response = client.patch(url, json={"status": "resolved"})
    assert response.status_code == 200, response.text
    assert response.json()["question_status"] == "resolved"
    assert client.patch(url, json={"status": "typo"}).status_code == 422
    assert setter.call_count == 1


@pytest.mark.parametrize("count,long_text", [(0, False), (2, False), (100, True)])
def test_pdf_one_a4_page_cyrillic_and_overflow(count, long_text):
    agenda = sample_agenda(count=count, long_text=long_text)
    content = generate_agenda_pdf(agenda)
    reader = PdfReader(io.BytesIO(content))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(595.276, abs=0.01)
    assert float(page.mediabox.height) == pytest.approx(841.89, abs=0.01)
    text = page.extract_text()
    for heading in (
        "Повестка встречи",
        "Действующие ИТ-программы",
        "Лицензии:",
        "Открытые вопросы",
    ):
        assert heading in text
    assert "1 / 1" in text
    if count > PDF_ROWS:
        assert f"Ещё записей: {count - PDF_ROWS}" in text
        assert "..." in text
    if not count:
        assert "Действующие программы не указаны" in text
    # The body renderer treats HTML tags as literal text, never markup.
    if long_text:
        assert "<скрипт>" in text
        assert "До 16.10.2026 (0 дн.)" in text  # expiry is visible even for a huge product name


def test_pdf_layout_measures_unbroken_and_hostile_input():
    generate_agenda_pdf(sample_agenda(count=0))  # fonts registered
    for text in ("Я" * 10000, "<img src='https://invalid/'/>" * 400, "\x00\n\tA&B" * 1000):
        paragraph, measured = _paragraph(text, 500, 29)
        assert measured <= 29
        assert paragraph.width <= 500


def test_pdf_warm_generation_under_one_second():
    agenda = sample_agenda(count=100, long_text=True)
    generate_agenda_pdf(agenda)
    started = time.perf_counter()
    generate_agenda_pdf(agenda)
    assert time.perf_counter() - started < 1.0

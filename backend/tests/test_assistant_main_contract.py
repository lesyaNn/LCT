"""Keep the JSON contract already integrated into main backwards compatible."""

from app.main import app
from app.modules.assistant.schemas import (
    ChatIn,
    ChatOut,
    ConversationOut,
    ConversationPage,
    Source,
    StatusOut,
    TurnOut,
    TurnPage,
)


def test_main_chat_request_fields_and_pages_are_unchanged():
    schema = ChatIn.model_json_schema()
    assert set(schema["properties"]) == {"message", "conversation_id", "page", "expected_revision"}
    assert schema["required"] == ["message"]
    pages = schema["properties"]["page"]["anyOf"][0]["enum"]
    assert set(pages) == {
        "dashboard",
        "universities",
        "university",
        "workflows",
        "workflow",
        "reports",
        "audit",
        "catalogs",
        "import",
        "users",
        "workflow_templates",
        "docs",
    }
    assert ChatIn.model_validate({"message": "Как скачать отчёт?"}).page is None


def test_main_reply_and_history_fields_are_unchanged():
    reply = {
        "conversation_id",
        "turn_id",
        "revision",
        "answer",
        "basis",
        "sources",
        "knowledge_version",
        "retrieval_mode",
        "model",
        "created_at",
    }
    assert set(ChatOut.model_fields) == reply
    assert set(TurnOut.model_fields) == reply | {"question"}
    assert set(Source.model_fields) == {"id", "title", "url", "excerpt"}
    assert set(ConversationOut.model_fields) == {
        "id",
        "title",
        "revision",
        "created_at",
        "updated_at",
    }
    assert set(ConversationPage.model_fields) == {"items", "total", "page", "page_size"}
    assert set(TurnPage.model_fields) == {"conversation", "items", "total", "page", "page_size"}
    model_types = ChatOut.model_json_schema()["properties"]["model"]["anyOf"]
    assert {item["type"] for item in model_types} == {"string", "null"}


def test_status_preserves_fields_and_only_extends_the_reason_enum():
    schema = StatusOut.model_json_schema()
    assert set(schema["properties"]) == {
        "enabled",
        "ready",
        "reason",
        "model",
        "retrieval_mode",
        "document_count",
        "knowledge_version",
    }
    main_reasons = {"disabled", "knowledge_missing", "model_unavailable", "ready"}
    assert set(schema["properties"]["reason"]["enum"]) == main_reasons | {"storage_unavailable"}


def test_existing_http_paths_and_success_response_shapes_are_unchanged():
    paths = app.openapi()["paths"]
    for path, method, status, model in (
        ("/status", "get", "200", "StatusOut"),
        ("/chat", "post", "200", "ChatOut"),
        ("/conversations", "get", "200", "ConversationPage"),
        ("/conversations/{conversation_id}", "get", "200", "TurnPage"),
    ):
        operation = paths["/api/v1/assistant" + path][method]
        response = operation["responses"][status]["content"]["application/json"]["schema"]
        assert response["$ref"] == "#/components/schemas/" + model
        assert operation["security"]
    deletion = paths["/api/v1/assistant/conversations/{conversation_id}"]["delete"]
    assert "204" in deletion["responses"]
    assert "content" not in deletion["responses"]["204"]

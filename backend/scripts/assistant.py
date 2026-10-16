"""Documentation indexing and private-history retention, run explicitly by an operator.

From backend/: python -m scripts.assistant inspect|index|purge [--execute].
No model download, schema changes or business-data access occur here.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import engine
from app.models.assistant import AssistantConversation
from app.modules.assistant.knowledge import get_knowledge
from app.modules.assistant.provider import Ollama


def bootstrap(config=settings, knowledge=None, provider=None):
    """Idempotent explicit deploy step: weights, index, one warm-up generation."""
    knowledge = knowledge or get_knowledge(config)
    provider = provider or Ollama(config)
    snapshot = knowledge.snapshot()
    if not snapshot.chunks:
        raise SystemExit("Assistant documentation is missing; check the read-only docs mount.")
    available = provider.available_models()
    for model in dict.fromkeys((config.assistant_embedding_model, config.assistant_model)):
        if model not in available:
            print(f"Downloading local model: {model}", flush=True)
            provider.pull(model)
    if not snapshot.embeddings:
        print("Building documentation index", flush=True)
        snapshot = knowledge.build_embeddings(provider)
    print("Warming chat model", flush=True)
    provider.chat(
        [
            {
                "role": "user",
                "content": 'Верни JSON с answer="Готов", basis="insufficient", source_ids=[].',
            }
        ]
    )
    print(
        json.dumps(
            {
                "ready": True,
                "documents": snapshot.document_count,
                "knowledge_version": snapshot.version,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain the documentation assistant")
    parser.add_argument("command", choices=("inspect", "index", "purge", "bootstrap", "check"))
    parser.add_argument("--execute", action="store_true", help="Apply retention deletion")
    arguments = parser.parse_args()
    if arguments.command == "bootstrap":
        bootstrap()
        return
    if arguments.command == "check":
        from app.modules.assistant.repository import Conversations
        from app.modules.assistant.service import Assistant

        with Session(engine) as db:
            status = Assistant(settings, get_knowledge(settings), Ollama(settings)).status(
                "admin", Conversations(db, "health-check", "admin", settings)
            )
        print(status.model_dump_json())
        if not status.ready:
            raise SystemExit(1)
        return
    if arguments.command == "purge":
        cutoff = datetime.now(UTC) - timedelta(days=settings.assistant_retention_days)
        with Session(engine) as db:
            condition = AssistantConversation.updated_at < cutoff
            count = (
                db.scalar(select(func.count()).select_from(AssistantConversation).where(condition))
                or 0
            )
            if arguments.execute:
                db.execute(delete(AssistantConversation).where(condition))
                db.commit()
            print(json.dumps({"expired_conversations": count, "deleted": arguments.execute}))
        return
    knowledge = get_knowledge(settings)
    snapshot = (
        knowledge.build_embeddings(Ollama(settings))
        if arguments.command == "index"
        else knowledge.snapshot()
    )
    print(
        json.dumps(
            {
                "documents": snapshot.document_count,
                "chunks": len(snapshot.chunks),
                "knowledge_version": snapshot.version,
                "retrieval_mode": "hybrid" if snapshot.embeddings else "lexical",
            }
        )
    )


if __name__ == "__main__":
    main()

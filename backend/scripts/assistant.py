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


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain the documentation assistant")
    parser.add_argument("command", choices=("inspect", "index", "purge"))
    parser.add_argument("--execute", action="store_true", help="Apply retention deletion")
    arguments = parser.parse_args()
    if arguments.command == "purge":
        cutoff = datetime.now(UTC) - timedelta(days=settings.assistant_retention_days)
        with Session(engine) as db:
            condition = AssistantConversation.updated_at < cutoff
            count = db.scalar(select(func.count()).select_from(AssistantConversation)
                              .where(condition)) or 0
            if arguments.execute:
                db.execute(delete(AssistantConversation).where(condition))
                db.commit()
            print(json.dumps({"expired_conversations": count, "deleted": arguments.execute}))
        return
    knowledge = get_knowledge(settings)
    snapshot = (knowledge.build_embeddings(Ollama(settings))
                if arguments.command == "index" else knowledge.snapshot())
    print(json.dumps({
        "documents": snapshot.document_count, "chunks": len(snapshot.chunks),
        "knowledge_version": snapshot.version,
        "retrieval_mode": "hybrid" if snapshot.embeddings else "lexical",
    }))


if __name__ == "__main__":
    main()

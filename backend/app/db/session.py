"""SQLAlchemy engine/session (Postgres in prod, SQLite fallback for hackathon demo)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def get_engine(url: str | None = None):
    """Build an engine for ``url`` (default: settings). No globals mutated."""
    target = url or settings.database_url
    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    return create_engine(target, pool_pre_ping=True, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

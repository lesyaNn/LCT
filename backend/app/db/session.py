"""SQLAlchemy engine/session (Postgres in prod, SQLite fallback for hackathon demo)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def get_engine(url: str | None = None):
    """Build an engine for ``url`` (default: settings). No globals mutated.

    M5: PostgreSQL gets an explicit pool (size/overflow/timeout) plus a
    server-side statement timeout so one slow query (import batch, overview)
    cannot pin a connection forever. SQLite keeps driver defaults.
    """
    target = url or settings.database_url
    if target.startswith("sqlite"):
        return create_engine(
            target,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(
        target,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        connect_args={
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
        },
    )


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

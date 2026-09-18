"""Alembic environment (P1-01-04).

* Imports ``app.models`` so ``target_metadata`` sees EVERY P1 model —
  the classic "model exists but Alembic doesn't see it" bug is avoided here.
* DB URL resolution: ``DATABASE_URL`` env var first (Docker / CI / local
  Postgres), then ``app.config.settings.database_url`` (default: local
  ``sqlite:///./dev.db`` for zero-setup runs).
* Sync engine — the project uses sync SQLAlchemy (``app.db.session``).
"""

import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure ``backend/`` is importable as top-level (``import app....``).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  (register ALL P1 tables on Base.metadata)

config = context.config

db_url = os.getenv("DATABASE_URL", settings.database_url)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

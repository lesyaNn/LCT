"""Isolated metadata for deferred (unmounted) domain modules.

P0-1 fix: pre-UUID / forward-stub models (workflow/documents/health_score/
identity) must never pollute the canonical ``Base.metadata`` — otherwise
SQLite ``create_all`` in tests builds phantom tables that do not exist in
production (SQL migrations are the sole schema source), and a future
``Base.metadata``-wide operation would mix UUID canon with int stubs.

Deferred models subclass :class:`DeferredBase` instead of ``Base``.
The audit log stays on ``Base`` (it IS SQL-managed, migration 000006+).
"""
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.db.base import NAMING_CONVENTION


class DeferredBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

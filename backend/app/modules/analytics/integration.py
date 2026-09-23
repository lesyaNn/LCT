"""Explicit boundary to Dev-1. No substitute UnifiedFilter or export engine.

P4_FILTER_PROVIDER=package.module:provider selects an object implementing
FilterProvider. With no provider only an EMPTY filter is supported. A supplied
business filter fails closed with 503, never silently becomes an unfiltered query.
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.catalog import ITProgram, University

FILTER_KEYS = frozenset(
    {
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
    }
)


class Selection(BaseModel):
    """IDs selected by the SHARED filter service, not by analytics.

    None on child ID lists = all children of selected universities/programs;
    [] = no children. A provider must narrow child lists for date/product/stage
    filters as well as university_ids, otherwise aggregates would broaden them.
    program_ids also defines the matrix column universe (including not_used).
    """

    university_ids: list[UUID] = Field(default_factory=list)
    program_ids: list[UUID] = Field(default_factory=list)
    university_program_ids: list[UUID] | None = None
    license_ids: list[UUID] | None = None
    workflow_instance_ids: list[UUID] | None = None


class FilterProvider(Protocol):
    version: str

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate via Dev-1 UnifiedFilter; return its JSON-mode model_dump."""
        ...

    def select(self, db: Session, filters: dict[str, Any]) -> Selection:
        """Use Dev-1 FilterService, with identical semantics to report/list."""
        ...


def load_object(variable: str):
    path = os.getenv(variable)
    if not path:
        return None
    module, name = path.rsplit(":", 1)
    return getattr(importlib.import_module(module), name)


class UnfilteredProvider:
    version = "unfiltered-only-v1"

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        unknown = set(raw) - FILTER_KEYS
        if unknown:
            raise HTTPException(422, "Unknown filter fields: " + ", ".join(sorted(unknown)))
        if any(value not in (None, [], "") for value in raw.values()):
            raise HTTPException(
                503,
                {
                    "code": "FILTER_PROVIDER_NOT_CONFIGURED",
                    "message": "Connect Dev-1 UnifiedFilter via P4_FILTER_PROVIDER",
                },
            )
        return {}

    def select(self, db: Session, filters: dict[str, Any]) -> Selection:
        return Selection(
            university_ids=list(db.scalars(select(University.id))),
            program_ids=list(db.scalars(select(ITProgram.id))),
        )


def get_filter_provider() -> FilterProvider:
    return load_object("P4_FILTER_PROVIDER") or UnfilteredProvider()


def data_scope(user: CurrentUser) -> tuple[UUID, ...] | None:
    """Authorization only, never business filtering. No unscoped user access."""
    if not user.id or not user.roles.intersection({"admin", "manager", "curator", "user"}):
        raise HTTPException(403, "Analytics/report access denied")
    if user.university_ids is None:
        if user.roles.intersection({"admin", "manager"}):
            return None
        raise HTTPException(403, "University scope is required")
    try:
        return tuple(sorted({UUID(value) for value in user.university_ids}))
    except (TypeError, ValueError):
        raise HTTPException(403, "Invalid university scope") from None


def restrict_selection(selection: Selection, allowed: tuple[UUID, ...] | None) -> Selection:
    if allowed is None:
        return selection
    return selection.model_copy(
        update={
            "university_ids": sorted(set(selection.university_ids).intersection(allowed)),
        }
    )

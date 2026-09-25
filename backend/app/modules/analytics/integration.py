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

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.models.catalog import ITProgram, License, University
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import WorkflowInstance

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
            raise BusinessException(ErrorCode.VALIDATION_ERROR)
        if any(value not in (None, [], "") for value in raw.values()):
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        return {}

    def select(self, db: Session, filters: dict[str, Any]) -> Selection:
        return Selection(
            university_ids=list(db.scalars(select(University.id))),
            program_ids=list(db.scalars(select(ITProgram.id))),
        )

    def select_scoped(self, db: Session, filters: dict[str, Any], user: CurrentUser) -> Selection:
        from app.core.policies import apply_university_scope

        stmt = apply_university_scope(select(University.id), University.id, user)
        university_ids = list(db.scalars(stmt))
        selection = Selection(
            university_ids=university_ids,
            program_ids=list(db.scalars(
                select(UniversityProgram.program_id).distinct().where(
                    UniversityProgram.university_id.in_(university_ids)
                )
            )),
        )
        if not university_ids:
            selection = selection.model_copy(update={
                "program_ids": [],
                "university_program_ids": [],
                "license_ids": [],
                "workflow_instance_ids": [],
            })
        return selection


def get_filter_provider() -> FilterProvider:
    return load_object("P4_FILTER_PROVIDER") or UnfilteredProvider()


def data_scope(user: CurrentUser) -> tuple[UUID, ...] | None:
    """Adapter to P5 scope for the existing P4 provider boundary."""
    from app.core.policies import get_data_scope

    scope = get_data_scope(user)
    return None if scope.is_all else tuple(sorted(scope.university_ids))


def restrict_selection(
    selection: Selection, allowed: tuple[UUID, ...] | None, db: Session | None = None
) -> Selection:
    if allowed is None:
        return selection
    visible = sorted(set(selection.university_ids).intersection(allowed))
    child_ids = (
        selection.program_ids or selection.university_program_ids
        or selection.license_ids or selection.workflow_instance_ids
    )
    if db is None:
        if child_ids:
            raise ValueError("database session required to scope Selection child IDs")
        return selection.model_copy(update={"university_ids": visible})
    programs = list(db.scalars(
        select(UniversityProgram.program_id).distinct().where(
            UniversityProgram.university_id.in_(visible),
            UniversityProgram.program_id.in_(selection.program_ids))
    ))
    def owned(model, ids):
        if ids is None:
            return None
        return list(db.scalars(select(model.id).where(
            model.id.in_(ids), model.university_id.in_(visible)
        )))
    return selection.model_copy(update={
        "university_ids": visible,
        "program_ids": sorted(programs),
        "university_program_ids": owned(UniversityProgram, selection.university_program_ids),
        "license_ids": owned(License, selection.license_ids),
        "workflow_instance_ids": owned(WorkflowInstance, selection.workflow_instance_ids),
    })

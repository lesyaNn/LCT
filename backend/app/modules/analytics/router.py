"""Thin Dev-2 endpoints. All business filters come from the Dev-1 provider."""

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.infrastructure import redis as cache
from app.modules.analytics.integration import (
    FILTER_KEYS,
    FilterProvider,
    data_scope,
    get_filter_provider,
    restrict_selection,
)
from app.modules.analytics.repository import load_data
from app.modules.analytics.schemas import Matrix, Overview
from app.modules.analytics.service import build_matrix, build_overview

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)
CACHE_TTL = 60


def filter_input(
    request: Request,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    university_ids: list[UUID] | None = Query(None),
    direction_ids: list[UUID] | None = Query(None),
    program_ids: list[UUID] | None = Query(None),
    product_ids: list[UUID] | None = Query(None),
    responsible_ids: list[UUID] | None = Query(None),
    workflow_statuses: list[str] | None = Query(None),
) -> dict:
    """Query transport only; validation/semantics belong to UnifiedFilter."""
    if set(request.query_params) - FILTER_KEYS:
        raise HTTPException(422, "Unknown filter parameter")
    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "university_ids": [str(x) for x in university_ids or []],
        "direction_ids": [str(x) for x in direction_ids or []],
        "program_ids": [str(x) for x in program_ids or []],
        "product_ids": [str(x) for x in product_ids or []],
        "responsible_ids": [str(x) for x in responsible_ids or []],
        "workflow_statuses": workflow_statuses or [],
    }


def cache_key(kind, filters, user, scope, provider, today):
    payload = {
        "filter": filters,
        "user": user.id,
        "roles": sorted(user.roles),
        "scope": None if scope is None else [str(x) for x in scope],
        "provider": provider.version,
        "day": today.isoformat(),
        "version": 1,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"analytics:{kind}:{digest}"


def get_analytics(kind, db, raw, user, provider):
    scope = data_scope(user)  # Authorization BEFORE reading shared cache/DB.
    try:
        filters = provider.normalize(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid UnifiedFilter") from None
    today = datetime.now(timezone.utc).date()
    key = cache_key(kind, filters, user, scope, provider, today)
    model = Overview if kind == "overview" else Matrix
    try:
        hit = cache.cache_get(key)
        if hit:
            return model.model_validate_json(hit)
    except Exception:
        # Cache outage/corrupt entry must not make the authoritative DB unavailable.
        logger.warning("Analytics cache read failed")
    selection = restrict_selection(provider.select(db, filters), scope)
    if kind == "matrix" and len(selection.university_ids) * len(selection.program_ids) > 50_000:
        raise HTTPException(422, "Matrix is too large; narrow the shared filter")
    data = load_data(db, selection, today=today, filters=filters)
    result = (build_overview if kind == "overview" else build_matrix)(data, today=today)
    try:
        cache.cache_set(key, result.model_dump_json(), CACHE_TTL)
    except Exception:
        logger.warning("Analytics cache write failed")
    return result


@router.get("/overview", response_model=Overview)
def overview(
    filters: dict = Depends(filter_input),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
    provider: FilterProvider = Depends(get_filter_provider),
):
    return get_analytics("overview", db, filters, user, provider)


@router.get("/matrix", response_model=Matrix)
def matrix(
    filters: dict = Depends(filter_input),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
    provider: FilterProvider = Depends(get_filter_provider),
):
    return get_analytics("matrix", db, filters, user, provider)

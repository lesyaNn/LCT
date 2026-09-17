"""DEFERRED to the next stage (PostgreSQL domain schema).

The minimal auth stage mounts only /api/v1/auth + /health, so the
domain CRUD tests below are intentionally skipped. They will be
re-enabled together with the domain routers.
"""
import pytest

pytestmark = pytest.mark.skip(reason="domain stage deferred — minimal auth only")

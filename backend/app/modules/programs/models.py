"""Legacy import shim — canonical P1 models live in ``app.models``.

Old code used ``Program`` with table ``programs``; the P1 schema uses
``ITProgram`` / ``it_programs``. ``Program`` is kept as an alias so legacy
imports do not break (domain routers are not mounted in the P1 stage).
"""

from app.models.catalog import ITDirection, ITProduct, ITProgram, Vendor  # noqa: F401

Program = ITProgram

__all__ = ["Program", "ITProgram", "ITDirection", "ITProduct", "Vendor"]

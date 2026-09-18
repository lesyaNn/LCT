"""Legacy import shim — canonical P1 models live in ``app.models``.

The old integer-based ``University`` definition was replaced by the P1 schema
(UUID PK, ``universities`` without a direct responsible column). Old imports
keep working; the table is defined exactly once (in ``app.models.catalog``).
"""

from app.models.catalog import (  # noqa: F401
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)

__all__ = [
    "University",
    "ITDirection",
    "ITProgram",
    "Vendor",
    "ITProduct",
    "Contract",
    "License",
    "Responsible",
    "UniversityResponsible",
]

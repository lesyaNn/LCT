"""Legacy import shim — canonical P1 models live in ``app.models``."""

from app.models.teachers import (  # noqa: F401
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)

__all__ = [
    "Teacher",
    "TeacherQualification",
    "TeacherCertificate",
    "TeacherProgram",
]

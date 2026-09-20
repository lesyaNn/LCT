"""P1 canonical domain models (single source of truth for Alembic metadata).

Importing this package registers ALL P1 tables on ``Base.metadata``.
Alembic ``env.py`` imports this module — that is how autogenerate and
``upgrade head`` see every model (P1-01-04 requirement).

Table naming follows the task specs exactly:
universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles, teachers,
teacher_qualifications, teacher_certificates, teacher_programs, students,
university_programs, university_products, meetings, documents,
interaction_notes, meeting_documents, health_score_snapshots (P2-09-01).
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
from app.models.health_score import HealthScoreSnapshot  # noqa: F401
from app.models.interactions import (  # noqa: F401
    Document,
    InteractionNote,
    Meeting,
    MeetingDocument,
    Student,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import (  # noqa: F401
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
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
    "Teacher",
    "TeacherQualification",
    "TeacherCertificate",
    "TeacherProgram",
    "Student",
    "UniversityProgram",
    "UniversityProduct",
    "Meeting",
    "MeetingDocument",
    "Document",
    "HealthScoreSnapshot",
    "InteractionNote",
]

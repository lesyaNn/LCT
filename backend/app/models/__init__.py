"""P1 canonical domain models (single source of truth for ORM metadata).

Importing this package registers ALL P1 tables plus the canonical P2
workflow pipeline on ``Base.metadata``. Alembic ``env.py`` imports this
module — that is how autogenerate and ``upgrade head`` see every model
(P1-01-04 requirement).

Table naming follows the task specs exactly:
universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles, teachers,
teacher_qualifications, teacher_certificates, teacher_programs, students,
university_programs, university_products, meetings, documents,
interaction_notes, meeting_documents, workflow_templates, workflow_stages,
workflow_instances, workflow_stage_transitions, workflow_comments,
workflow_attachments, workflow_tasks, instance_stages,
health_score_snapshots (P2-09-01, migration 000015).
report_jobs (P4-06-01, migration 000018).
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
from app.models.report_job import ReportJob  # noqa: F401
from app.models.teachers import (  # noqa: F401
    Teacher,
    TeacherCertificate,
    TeacherProgram,
    TeacherQualification,
)
from app.models.workflow_templates import (  # noqa: F401
    WorkflowStage,
    WorkflowTemplate,
)
from app.models.workflow_instances import (  # noqa: F401
    InstanceStage,
    WorkflowAttachment,
    WorkflowComment,
    WorkflowInstance,
    WorkflowStageTransition,
    WorkflowTask,
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
    "InteractionNote",
    "WorkflowTemplate",
    "WorkflowStage",
    "WorkflowInstance",
    "WorkflowStageTransition",
    "WorkflowComment",
    "WorkflowAttachment",
    "WorkflowTask",
    "InstanceStage",
    "HealthScoreSnapshot",
    "ReportJob",
]

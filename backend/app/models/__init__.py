"""Canonical domain models (single source of truth for ORM metadata).

Importing this package registers all P1 tables plus the canonical B2 workflow
runtime on ``Base.metadata``.  The legacy ``app.modules.workflow`` models are
kept on ``DeferredBase`` and must not be imported here.

Table naming follows the task specs exactly:
universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles, teachers,
teacher_qualifications, teacher_certificates, teacher_programs, students,
university_programs, university_products, meetings, documents,
interaction_notes, meeting_documents.

Workflow runtime tables: workflow_templates, workflow_stages,
workflow_instances, instance_stages, transitions,
comments, tasks, attachments.
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
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.models.workflow import (  # noqa: F401
    WorkflowAttachment,
    WorkflowComment,
    WorkflowInstance,
    WorkflowInstanceStage,
    WorkflowTask,
    WorkflowTemplate,
    WorkflowTemplateStage,
    WorkflowTransition,
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
    "AuditEvent",
    "WorkflowTemplate",
    "WorkflowTemplateStage",
    "WorkflowInstance",
    "WorkflowInstanceStage",
    "WorkflowTransition",
    "WorkflowComment",
    "WorkflowTask",
    "WorkflowAttachment",
]

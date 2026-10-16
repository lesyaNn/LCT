"""P1 canonical domain models (single source of truth for ORM metadata).

Importing this package registers ALL P1 tables plus the canonical P2
workflow pipeline on ``Base.metadata``. Alembic ``env.py`` imports this
module — that is how autogenerate and ``upgrade head`` see every model
(P1-01-04 requirement).

Table naming follows the task specs exactly:
universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles,
university_programs, university_products, meetings, documents,
interaction_notes, meeting_documents, workflow_templates, workflow_stages,
workflow_instances, workflow_stage_transitions, workflow_comments,
workflow_attachments, workflow_tasks, instance_stages,
report_jobs
(P4-06-01, migration 000018, Dev-1 actor_* schema), external_applications
and external_sync_states (Stage 11, migration 000027), product_directions
(import sheet "Продукт_Направление", migration 000028).
"""

from app.models.assistant import AssistantConversation, AssistantTurn
from app.models.catalog import (  # noqa: F401
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    ProductDirection,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
    VendorContact,
)
from app.models.external import ExternalApplication, ExternalSyncState  # noqa: F401
from app.models.report_job import (  # noqa: F401
    REPORT_JOB_STATUSES,
    STATUS_BUILDING,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_READY,
    ReportJob,
)
from app.models.report_template import ReportTemplate  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.education import ProgramEducationStats  # noqa: F401
from app.models.interactions import (  # noqa: F401
    Document,
    InteractionNote,
    Meeting,
    MeetingDocument,
    UniversityProduct,
    UniversityProgram,
)
from app.models.teachers import Teacher, TeacherCertificate, TeacherProgram, TeacherQualification  # noqa: F401
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
    "AssistantConversation",
    "AssistantTurn",
    "University",
    "ITDirection",
    "ITProgram",
    "Vendor",
    "ITProduct",
    "ProductDirection",
    "Contract",
    "License",
    "Responsible",
    "UniversityResponsible",
    "UniversityProgram",
    "ProgramEducationStats",
    "Teacher",
    "TeacherQualification",
    "TeacherCertificate",
    "TeacherProgram",
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
    "AuditOutbox",
    "ExternalApplication",
    "ExternalSyncState",
    "ReportJob",
    "ReportTemplate",
    "Notification",
]

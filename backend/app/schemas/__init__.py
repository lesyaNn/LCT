"""Central Pydantic DTO package (P1-02-0x contract schemas).

Import everything from here::

    from app.schemas import LicenseStatus, UniversityList, TeacherPassport
"""

from app.schemas.common import (  # noqa: F401
    EXPIRY_WARNING_DAYS,
    ContractStatus,
    DocumentStatus,
    DocumentType,
    EntityStatus,
    ErrorDetail,
    ErrorResponse,
    FilterBase,
    HealthScoreStatus,
    LicenseStatus,
    MeetingType,
    PaginatedResponse,
    PaginationParams,
    ReportFormat,
    StudentStatus,
    TeacherReadiness,
    TransferStatus,
    TransitionAction,
    UniversityFilter,
    UniversityProductStatus,
    UniversityProgramStatus,
    UserRole,
    WorkflowStageStatus,
)
from app.schemas.university import (  # noqa: F401
    ContractShort,
    DocumentShort,
    InteractionShort,
    LicenseShort,
    MeetingShort,
    ProductShort,
    ProgramShort,
    ResponsibleDetail,
    ResponsibleShort,
    StageShort,
    StudentsSummary,
    TeacherShort,
    UniversityBase,
    UniversityCreate,
    UniversityDetail,
    UniversityList,
    UniversityPassport,
    UniversityUpdate,
    WorkflowSummary,
)

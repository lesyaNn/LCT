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
    LicenseStatus,
    MeetingType,
    PaginatedResponse,
    PaginationParams,
    ReportFormat,
    TransferStatus,
    TransitionAction,
    UniversityFilter,
    UniversityProductStatus,
    UniversityProgramStatus,
    UserRole,
    WorkflowStageStatus,
)
from app.schemas.catalog import (  # noqa: F401
    DirectionBase,
    DirectionCreate,
    DirectionDetail,
    DirectionList,
    DirectionShort,
    DirectionUpdate,
    ProductBase,
    ProductCreate,
    ProductDetail,
    ProductList,
    ProductShort,
    ProductUpdate,
    ProgramBase,
    ProgramCreate,
    ProgramDetail,
    ProgramList,
    ProgramShort,
    ProgramUpdate,
    VendorBase,
    VendorCreate,
    VendorDetail,
    VendorList,
    VendorShort,
    VendorUpdate,
)
from app.schemas.licenses import (  # noqa: F401
    ContractShort,
    LicenseShort,
)
from app.schemas.university import (  # noqa: F401
    DocumentShort,
    InteractionShort,
    MeetingShort,
    ResponsibleDetail,
    ResponsibleShort,
    StageShort,
    UniversityBase,
    UniversityCreate,
    UniversityDetail,
    UniversityList,
    UniversityPassport,
    UniversityUpdate,
    WorkflowSummary,
)

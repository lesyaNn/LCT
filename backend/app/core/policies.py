"""Single university data-scope policy for P1, P2 and P4 consumers."""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy import false

from app.core.errors import SecurityError
from app.core.security import CurrentUser
from app.schemas.errors import ErrorCode


class ScopeKind(str, Enum):
    OWN = "own"
    GROUP = "group"
    ALL = "all"
    DENY = "deny"


@dataclass(frozen=True)
class DataScope:
    kind: ScopeKind
    university_ids: frozenset[UUID]

    @property
    def is_all(self) -> bool:
        return self.kind is ScopeKind.ALL

    def allows(self, university_id: UUID | str) -> bool:
        try:
            return self.is_all or UUID(str(university_id)) in self.university_ids
        except (ValueError, TypeError, AttributeError):
            return False


def get_data_scope(user: CurrentUser) -> DataScope:
    """JWT university_ids is the explicit assignment; missing/empty fails closed."""
    roles = user.roles or set()
    if "admin" in roles:
        return DataScope(ScopeKind.ALL, frozenset())
    # Legacy curator routes historically had global visibility. Preserve that
    # compatibility without making curator a public admin/manager role.
    if "curator" in roles and "manager" not in roles and user.university_ids is None:
        return DataScope(ScopeKind.ALL, frozenset())
    kind = (ScopeKind.GROUP if "manager" in roles else
            ScopeKind.OWN if roles & {"user", "curator"} else ScopeKind.DENY)
    if kind is ScopeKind.DENY:
        return DataScope(kind, frozenset())
    ids: set[UUID] = set()
    for raw in user.university_ids or ():
        try:
            ids.add(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    return DataScope(kind, frozenset(ids))


def apply_university_scope(stmt, university_column, user: CurrentUser):
    """Add SQL predicate before counting, pagination or loading rows."""
    scope = get_data_scope(user)
    if scope.is_all:
        return stmt
    if not scope.university_ids:
        return stmt.where(false())
    return stmt.where(university_column.in_(scope.university_ids))


def ensure_university_access(university_id: UUID | str, user: CurrentUser) -> None:
    if not get_data_scope(user).allows(university_id):
        raise SecurityError(ErrorCode.FORBIDDEN)

"""P2-06-01 overdue math: single canonical helper (P2 dependency for B1).

Every consumer (instance endpoint, runtime-stage DTOs, health score, tests)
must use :func:`compute_overdue` — no local ``is_overdue``/``days_overdue``
formulas anywhere else.

Date contract
-------------
* ``due_date`` is a calendar DATE (never a timestamp); ``completed_at`` is a
  TIMESTAMPTZ moment (or a plain date in tests/callers that only track days).
* "Today" is UTC calendar day (:func:`today_utc`); callers under test pass an
  explicit ``today`` so boundaries are deterministic.
* A DATE carries no timezone, so there is no tz conversion: only the date
  part of ``completed_at`` participates in the comparison.

Boundary semantics (pinned)
---------------------------
* ``due_date`` None -> never overdue, ``days_overdue == 0`` (no deadline set,
  e.g. ``sla_days`` NULL cascade).
* Open item (``completed_at`` None): overdue iff ``today > due_date``.
  Due today or due tomorrow -> not overdue (``days_overdue == 0``);
  due yesterday -> overdue with ``days_overdue == 1``.
* Completed item: overdue iff ``completed_date > due_date`` (strictly after).
  Completed before due or exactly on the due date -> not overdue.
  Completed after due -> overdue with ``days_overdue`` = calendar days late.
"""

from __future__ import annotations

from datetime import date, datetime


def today_utc() -> date:
    """Current UTC calendar day (single place for the date contract)."""
    from datetime import timezone

    return datetime.now(timezone.utc).date()


def _as_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def compute_overdue(
    due_date: date | None,
    completed_at: date | datetime | None,
    today: date | None = None,
) -> tuple[bool, int]:
    """Return ``(is_overdue, days_overdue)`` for one dated item.

    ``today`` defaults to :func:`today_utc`; pass it explicitly in tests.
    ``days_overdue`` is 0 whenever ``is_overdue`` is False.
    """
    if due_date is None:
        return False, 0
    current = today if today is not None else today_utc()
    done = _as_date(completed_at)
    if done is not None:
        late = (done - due_date).days
        if late <= 0:
            return False, 0
        return True, late
    late = (current - due_date).days
    if late <= 0:
        return False, 0
    return True, late

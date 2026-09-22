"""
SchemeKnit Calendar-Period Usage Quota
=======================================

Server-side enforcement of the Free Tier lesson-plan allowance.

COMMERCIAL MODEL
----------------
    ONE INDICATOR → ONE TEACHING PERIOD → ONE LESSON PLAN → ONE FREE-TIER UNIT
    Free Tier allowance = 5 lesson plans per CALENDAR MONTH.

Rules implemented here:
  * The active period is derived from the SERVER clock only (never the
    browser's month). A new calendar month reads a different ``usage_periods``
    row, so no cron job is required to reset the allowance; January usage never
    affects February.
  * Enforcement is atomic. Reserving N units inserts the per-unit rows and then
    performs a single guarded UPDATE (``units_used + N <= limit``). Concurrent
    requests cannot race past the limit — the second one's guard fails.
  * Failed generations and validation/provider failures release their reserved
    units.
  * Duplicate requests and regeneration of an already-counted indicator in the
    same period consume ZERO additional units (idempotent per-unit keys).

Nothing in this module trusts a client-supplied period. ``period_key`` is always
computed from ``current_period_key()`` unless a test passes one explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from .database import UsagePeriodDB, UsageUnitDB, generate_id

#: The period granularity for the Free Tier lesson-plan allowance.
PERIOD_TYPE_CALENDAR_MONTH = "calendar_month"

#: Unit kind recorded in the ledger. One lesson plan == one unit.
UNIT_KIND_LESSON_PLAN = "lesson_plan"


def current_period_key(at: Optional[datetime] = None) -> str:
    """Return the active calendar-month key (``YYYY-MM``) from the server clock.

    This is the only place the period is computed; callers must not use a
    client-supplied month.
    """
    at = at or datetime.utcnow()
    return at.strftime("%Y-%m")


def _dialect(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _insert_ignore(db: Session, model, values: dict):
    """Dialect-aware ``INSERT ... ON CONFLICT DO NOTHING``.

    Returns the executed result; ``rowcount == 1`` means a row was inserted,
    ``0`` means the unique key already existed.
    """
    if _dialect(db) == "postgresql":
        stmt = _pg_insert(model.__table__).values(**values).on_conflict_do_nothing()
    else:
        stmt = _sqlite_insert(model.__table__).values(**values).on_conflict_do_nothing()
    return db.execute(stmt)


def _unit_key(scheme_id: str, indicator_code: str) -> str:
    return f"{scheme_id}:{indicator_code or ''}"


def _ensure_period_row(db: Session, user_id: str, period_key: str) -> None:
    """Create the aggregate row for (user, period) if it does not exist."""
    _insert_ignore(db, UsagePeriodDB, {
        "id": generate_id(),
        "user_id": user_id,
        "period_type": PERIOD_TYPE_CALENDAR_MONTH,
        "period_key": period_key,
        "units_used": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })


def get_units_used(db: Session, user_id: str, period_key: Optional[str] = None) -> int:
    """Units consumed by a user in a period (defaults to the current month)."""
    period_key = period_key or current_period_key()
    row = db.query(UsagePeriodDB).filter(
        UsagePeriodDB.user_id == user_id,
        UsagePeriodDB.period_type == PERIOD_TYPE_CALENDAR_MONTH,
        UsagePeriodDB.period_key == period_key,
    ).first()
    return int(row.units_used or 0) if row else 0


@dataclass
class Reservation:
    """Outcome of an atomic quota reservation attempt."""
    allowed: bool
    limit: int
    used: int
    remaining: int
    consumed: int = 0                 # NEW units charged by this call
    unlimited: bool = False
    period_type: str = PERIOD_TYPE_CALENDAR_MONTH
    period_key: str = ""
    reserved_keys: List[str] = field(default_factory=list)
    reason: str = ""

    def as_quota(self) -> dict:
        return {
            "enforced": not self.unlimited,
            "limit": self.limit,
            "used": self.used,
            "remaining": None if self.unlimited else self.remaining,
            "unlimited": self.unlimited,
            "period_type": self.period_type,
            "period_key": self.period_key,
        }


def reserve_lesson_units(
    db: Session,
    user_id: str,
    scheme_id: str,
    indicator_codes: Sequence[str],
    limit: int,
    period_key: Optional[str] = None,
) -> Reservation:
    """Atomically reserve one unit per requested indicator.

    ``limit <= 0`` means unlimited: no rows are written and the request always
    succeeds. Otherwise the per-unit rows are inserted (idempotently) and the
    aggregate is incremented by the number of NEWLY inserted units under a
    guarded UPDATE. If the guard fails, the transaction is rolled back and the
    reservation is refused.
    """
    period_key = period_key or current_period_key()

    if limit <= 0:
        return Reservation(
            allowed=True, limit=0, used=0, remaining=-1, consumed=0,
            unlimited=True, period_key=period_key,
        )

    # Deduplicate while preserving order.
    keys: List[str] = []
    for code in indicator_codes:
        k = _unit_key(scheme_id, code)
        if k not in keys:
            keys.append(k)

    try:
        _ensure_period_row(db, user_id, period_key)

        new_keys: List[str] = []
        for k in keys:
            res = _insert_ignore(db, UsageUnitDB, {
                "id": generate_id(),
                "user_id": user_id,
                "period_type": PERIOD_TYPE_CALENDAR_MONTH,
                "period_key": period_key,
                "unit_kind": UNIT_KIND_LESSON_PLAN,
                "unit_key": k,
                "scheme_id": scheme_id,
                "created_at": datetime.utcnow(),
            })
            if (res.rowcount or 0) == 1:
                new_keys.append(k)

        new_count = len(new_keys)

        if new_count == 0:
            used = get_units_used(db, user_id, period_key)
            db.commit()
            return Reservation(
                allowed=True, limit=limit, used=used,
                remaining=max(limit - used, 0), consumed=0,
                period_key=period_key, reason="already_counted",
            )

        # Atomic guard: only succeed when this increment keeps us within limit.
        upd = db.execute(
            text(
                "UPDATE usage_periods "
                "SET units_used = units_used + :n, updated_at = :now "
                "WHERE user_id = :uid AND period_type = :pt "
                "AND period_key = :pk AND units_used + :n <= :limit"
            ),
            {
                "n": new_count, "now": datetime.utcnow(),
                "uid": user_id, "pt": PERIOD_TYPE_CALENDAR_MONTH,
                "pk": period_key, "limit": limit,
            },
        )

        if (upd.rowcount or 0) != 1:
            # Lost the race (or the allowance is exhausted): undo everything.
            db.rollback()
            used = get_units_used(db, user_id, period_key)
            return Reservation(
                allowed=False, limit=limit, used=used,
                remaining=max(limit - used, 0), consumed=0,
                period_key=period_key, reason="quota_exceeded",
            )

        db.commit()
        used = get_units_used(db, user_id, period_key)
        return Reservation(
            allowed=True, limit=limit, used=used,
            remaining=max(limit - used, 0), consumed=new_count,
            period_key=period_key, reserved_keys=new_keys,
        )
    except Exception:
        db.rollback()
        raise


def release_lesson_units(
    db: Session,
    user_id: str,
    unit_keys: Sequence[str],
    period_key: Optional[str] = None,
) -> int:
    """Release previously reserved units (generation failed / produced fewer).

    Deletes the named per-unit rows and decrements the aggregate by exactly the
    number deleted, guarded so it can never go negative. Returns the count
    released.
    """
    period_key = period_key or current_period_key()
    keys = [k for k in unit_keys if k]
    if not keys:
        return 0

    try:
        deleted = db.query(UsageUnitDB).filter(
            UsageUnitDB.user_id == user_id,
            UsageUnitDB.period_type == PERIOD_TYPE_CALENDAR_MONTH,
            UsageUnitDB.period_key == period_key,
            UsageUnitDB.unit_kind == UNIT_KIND_LESSON_PLAN,
            UsageUnitDB.unit_key.in_(keys),
        ).delete(synchronize_session=False)

        if deleted:
            db.execute(
                text(
                    "UPDATE usage_periods SET units_used = units_used - :n, "
                    "updated_at = :now "
                    "WHERE user_id = :uid AND period_type = :pt "
                    "AND period_key = :pk AND units_used >= :n"
                ),
                {
                    "n": deleted, "now": datetime.utcnow(),
                    "uid": user_id, "pt": PERIOD_TYPE_CALENDAR_MONTH,
                    "pk": period_key,
                },
            )
        db.commit()
        return int(deleted or 0)
    except Exception:
        db.rollback()
        raise


def remaining_for_limit(
    db: Session, user_id: str, limit: int, period_key: Optional[str] = None
) -> int:
    """Remaining units for a finite limit (or a large sentinel when unlimited)."""
    if limit <= 0:
        return -1
    used = get_units_used(db, user_id, period_key)
    return max(limit - used, 0)

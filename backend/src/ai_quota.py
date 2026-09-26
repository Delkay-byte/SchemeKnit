"""
SchemeKnit Monthly AI Generation Quota
=======================================

Server-side enforcement of the Free Tier AI allowance.

COMMERCIAL MODEL (real-use remediation PART 16-19)
--------------------------------------------------
    ONE SUCCESSFUL AI-ASSISTED GENERATION REQUEST = ONE AI QUOTA UNIT
    Free Tier allowance = 5 AI generations per CALENDAR MONTH.

Semantics (must stay consistent with the existing lesson-plan entitlement):
  * The active period is derived from the SERVER clock only (``YYYY-MM``).
    A new calendar month reads a different ledger row, so usage resets to
    0/5 automatically — no cron job, no manual reset (PART 18).
  * ONE unit is consumed per successful AI-assisted generation REQUEST —
    the same unit definition the existing lifetime counter used (one batch
    request = one AI generation), NOT per lesson (PART 17).
  * Failures never consume quota (PART 17/19): provider failure, model
    unavailable, 429/503, malformed output, quality-gate failure and a
    deterministic fallback all consume ZERO units. Callers only invoke
    :func:`consume_ai_generation` after a generation actually succeeded
    with AI content.
  * Per-user isolation: every ledger row is keyed by ``user_id`` (PART 29)
    and the AI ledger is independent of the lesson-plan quota ledger
    (different ``period_type``, PART 30).

This module deliberately mirrors the shape of ``usage_quota.py`` so the two
allowances stay conceptually aligned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from .database import AIGenerationPeriodDB, generate_id

#: The period granularity for the AI allowance.
PERIOD_TYPE_AI_CALENDAR_MONTH = "ai_calendar_month"

#: Unit kind recorded in the ledger. One successful AI generation == one unit.
UNIT_KIND_AI_GENERATION = "ai_generation"


def current_ai_period_key(at: Optional[datetime] = None) -> str:
    """Return the active calendar-month key (``YYYY-MM``) from the server clock."""
    at = at or datetime.utcnow()
    return at.strftime("%Y-%m")


def _dialect(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _insert_ignore(db: Session, model, values: dict):
    """Dialect-aware ``INSERT ... ON CONFLICT DO NOTHING``."""
    if _dialect(db) == "postgresql":
        stmt = _pg_insert(model.__table__).values(**values).on_conflict_do_nothing()
    else:
        stmt = _sqlite_insert(model.__table__).values(**values).on_conflict_do_nothing()
    return db.execute(stmt)


def _ensure_period_row(db: Session, user_id: str, period_key: str) -> None:
    _insert_ignore(db, AIGenerationPeriodDB, {
        "id": generate_id(),
        "user_id": user_id,
        "period_type": PERIOD_TYPE_AI_CALENDAR_MONTH,
        "period_key": period_key,
        "units_used": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })


def get_ai_units_used(db: Session, user_id: str, period_key: Optional[str] = None) -> int:
    """AI units consumed by a user this calendar month (server clock)."""
    period_key = period_key or current_ai_period_key()
    row = db.query(AIGenerationPeriodDB).filter(
        AIGenerationPeriodDB.user_id == user_id,
        AIGenerationPeriodDB.period_type == PERIOD_TYPE_AI_CALENDAR_MONTH,
        AIGenerationPeriodDB.period_key == period_key,
    ).first()
    return int(row.units_used or 0) if row else 0


def ai_quota_status(
    db: Session,
    user_id: str,
    ai_credits: int,
    period_key: Optional[str] = None,
) -> dict:
    """Snapshot for UI display: ``X / 5 AI generations this month``.

    ``ai_credits <= 0`` means unlimited (paid plans / school licenses) — the
    UI must never render a monthly cap for those.
    """
    period_key = period_key or current_ai_period_key()
    enforced = ai_credits > 0
    used = get_ai_units_used(db, user_id, period_key) if enforced else 0
    return {
        "enforced": enforced,
        "unlimited": not enforced,
        "limit": ai_credits if enforced else 0,
        "used": used,
        "remaining": (max(ai_credits - used, 0) if enforced else None),
        "period_type": PERIOD_TYPE_AI_CALENDAR_MONTH,
        "period_key": period_key,
        "unit": UNIT_KIND_AI_GENERATION,
    }


def consume_ai_generation(
    db: Session,
    user_id: str,
    credits: int,
    period_key: Optional[str] = None,
) -> int:
    """Record ONE successful AI generation against the current month.

    Returns the remaining count (or ``-1`` when unlimited). Idempotent per
    (user, period): a repeat call for the same request is guarded upstream by
    the AIUsageEventDB ledger, and this aggregate only ever increments by the
    number of NEW events, so a duplicate cannot double-consume.

    NOTE: failures must never reach this function. Only call it after the
    generation actually succeeded with AI content (PART 19).
    """
    period_key = period_key or current_ai_period_key()
    if credits <= 0:
        return -1  # unlimited — never decremented, never displayed as capped

    _ensure_period_row(db, user_id, period_key)
    # Atomic guarded increment: never exceed the monthly cap even under a
    # concurrent race — the second request's guard fails instead.
    upd = db.execute(
        text(
            "UPDATE ai_generation_periods "
            "SET units_used = units_used + 1, updated_at = :now "
            "WHERE user_id = :uid AND period_type = :pt "
            "AND period_key = :pk AND units_used < :limit"
        ),
        {
            "now": datetime.utcnow(), "uid": user_id,
            "pt": PERIOD_TYPE_AI_CALENDAR_MONTH, "pk": period_key,
            "limit": credits,
        },
    )
    db.commit()
    if (upd.rowcount or 0) != 1:
        db.rollback()
    used = get_ai_units_used(db, user_id, period_key)
    return max(credits - used, 0)

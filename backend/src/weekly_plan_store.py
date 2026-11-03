"""Database repository for weekly class plans.

The hosted application uses this module as the only weekly-plan store. The
revision check is a conditional UPDATE executed by the database; a process
lock is never the concurrency authority.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from .database import WeeklyPlanDB
from .models import WeeklyClassPlan


class WeeklyPlanNotFound(Exception):
    """The plan does not exist, or is not owned by the caller."""


class StaleWeeklyPlanRevision(Exception):
    """The stored revision no longer matches the client's If-Match."""

    def __init__(self, current_revision: int):
        super().__init__(f"current revision is {current_revision}")
        self.current_revision = current_revision


def plan_from_row(row: WeeklyPlanDB) -> WeeklyClassPlan:
    return WeeklyClassPlan.model_validate(row.content or {})


def plan_document(row: WeeklyPlanDB) -> Dict[str, Any]:
    """The existing API document shape, with the canonical revision attached."""
    content = dict(row.content or {})
    content["updated_date"] = row.updated_at.isoformat() if row.updated_at else None
    return content


def version_token(row: WeeklyPlanDB) -> str:
    return str(int(row.revision or 1))


def get_row(db: Session, plan_id: str, owner_id: str) -> WeeklyPlanDB:
    row = db.query(WeeklyPlanDB).filter(
        WeeklyPlanDB.id == plan_id,
        WeeklyPlanDB.owner_id == owner_id,
    ).first()
    if row is None:
        raise WeeklyPlanNotFound(plan_id)
    return row


def list_rows(db: Session, owner_id: str) -> List[WeeklyPlanDB]:
    return (
        db.query(WeeklyPlanDB)
        .filter(WeeklyPlanDB.owner_id == owner_id)
        .order_by(WeeklyPlanDB.created_at.desc())
        .all()
    )


def create_row(
    db: Session,
    *,
    owner_id: str,
    plan: WeeklyClassPlan,
    school_id: Optional[str] = None,
) -> WeeklyPlanDB:
    now = datetime.utcnow()
    row = WeeklyPlanDB(
        id=plan.id,
        owner_id=owner_id,
        school_id=school_id,
        class_level=(
            plan.class_level.value
            if hasattr(plan.class_level, "value")
            else str(plan.class_level)
        ),
        week_number=plan.week_number,
        term=plan.term,
        academic_year=plan.academic_year,
        template_id=plan.template_id,
        content=plan.model_dump(mode="json"),
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_row(
    db: Session,
    *,
    plan_id: str,
    owner_id: str,
    content: Dict[str, Any],
    expected_version: Optional[str] = None,
) -> WeeklyPlanDB:
    """Conditionally replace the document and increment its revision.

    A missing ``expected_version`` is resolved from the current row (backward
    compatible for older clients), but the write is still a compare-and-swap:
    a concurrent writer that wins first makes this call fail with a stale
    revision instead of overwriting it.
    """
    current = get_row(db, plan_id, owner_id)
    expected = int(current.revision or 1)
    if expected_version not in (None, "", str(expected)):
        raise StaleWeeklyPlanRevision(expected)

    result = db.execute(
        update(WeeklyPlanDB)
        .where(
            WeeklyPlanDB.id == plan_id,
            WeeklyPlanDB.owner_id == owner_id,
            WeeklyPlanDB.revision == expected,
        )
        .values(
            content=content,
            revision=WeeklyPlanDB.revision + 1,
            updated_at=datetime.utcnow(),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        db.expire_all()
        try:
            latest = get_row(db, plan_id, owner_id)
            current_revision = int(latest.revision or 1)
        except WeeklyPlanNotFound:
            current_revision = expected
        raise StaleWeeklyPlanRevision(current_revision)

    db.commit()
    db.expire_all()
    return get_row(db, plan_id, owner_id)

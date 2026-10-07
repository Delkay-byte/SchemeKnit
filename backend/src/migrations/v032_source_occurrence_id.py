"""
Migration v032: source-occurrence identity for lesson plans (Priority 1).

Weekly curriculum coverage follows SOURCE OCCURRENCES in the teacher's
scheme: every instructional source occurrence becomes exactly one lesson plan
in its own source week. This column stores the stable identity of that source
occurrence (``week<source_week>:<position_in_week>:<indicator_code>``) so the
identity survives generation → persistence → reload → export.

Additive and dialect-portable: existing lessons stay valid with an empty
default, and no data is rewritten (legacy rows simply have no identity
recorded).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v032_source_occurrence_id"
MIGRATION_NAME = "Source occurrence identity for weekly lesson coverage"


def up(db):
    """Add lesson_plans.source_occurrence_id if missing (idempotent)."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    if "source_occurrence_id" not in cols:
        db.execute(text(
            "ALTER TABLE lesson_plans ADD COLUMN source_occurrence_id VARCHAR DEFAULT ''"
        ))
        db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; additive migrations are never rolled back."""
    pass

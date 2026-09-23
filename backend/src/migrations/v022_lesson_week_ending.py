"""
Migration v022: Add source week_ending columns to lesson_plans.

Source week-ending dates must survive parse → IR → allocation → generation →
preview → export. Without a stored column the export path re-derived Friday
from lesson_date and silently overwrote the curriculum source date.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v022_lesson_week_ending"
MIGRATION_NAME = "Add week_ending columns to lesson_plans"


def up(db):
    inspector = sa_inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
    if "week_ending" not in cols:
        db.execute(text("ALTER TABLE lesson_plans ADD COLUMN week_ending DATE"))
    if "week_ending_derived" not in cols:
        db.execute(text(
            "ALTER TABLE lesson_plans ADD COLUMN week_ending_derived "
            "BOOLEAN NOT NULL DEFAULT 0"
        ))
    db.commit()


def down(db):
    """SQLite does not support DROP COLUMN; no-op."""
    pass

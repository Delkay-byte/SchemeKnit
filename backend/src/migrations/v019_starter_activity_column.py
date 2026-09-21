"""
Migration v019: Add starter_activity column to lesson_plans.

The Generation V2 pipeline sets a dedicated starter_activity field on the
LessonPlan model, but the database table lacks the corresponding column.
This migration adds it so V2-enriched content persists correctly.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v019_starter_activity_column"
MIGRATION_NAME = "Add starter_activity column to lesson_plans"


def up(db):
    inspector = sa_inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
    if "starter_activity" not in cols:
        db.execute(text("ALTER TABLE lesson_plans ADD COLUMN starter_activity TEXT DEFAULT ''"))
        db.commit()


def down(db):
    """SQLite does not support DROP COLUMN; no-op."""
    pass

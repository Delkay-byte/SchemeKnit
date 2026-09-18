"""
Migration v010: Lesson content columns for model/DB parity.

The LessonPlan pydantic model already declares keywords, homework,
differentiation, and essential_questions, but the lesson_plans table lacks
them (v001 added a subset elsewhere). Additive, dialect-portable.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v010_lesson_content_columns"
MIGRATION_NAME = "Lesson content columns"


def up(db):
    """Add missing lesson content columns."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    wanted = {
        "keywords": "TEXT DEFAULT '[]'",
        "homework": "TEXT DEFAULT ''",
        "differentiation": "TEXT DEFAULT ''",
        "essential_questions": "TEXT DEFAULT '[]'",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE lesson_plans ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN."""
    pass

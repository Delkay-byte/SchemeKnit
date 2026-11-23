"""
Migration v057: persist Zeli pedagogy that must survive reload and export.

Three additive JSON columns on lesson_plans:
  * ``worked_example``     — concrete problem, explicit steps, answer, reasoning
  * ``practice_questions`` — answered questions with reasoning
  * ``resource_guidance``  — low-cost local preparation and use

They are optional. Legacy lessons keep empty values; no existing data is
rewritten and no column is dropped by down().
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v057_zeli_pedagogy_fields"
MIGRATION_NAME = "Persist Zeli worked examples, practice and resource guidance"


def up(db):
    """Add the three lesson_plans JSON columns when they are missing."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    for name in ("worked_example", "practice_questions", "resource_guidance"):
        if name not in cols:
            db.execute(text(
                f"ALTER TABLE lesson_plans ADD COLUMN {name} JSON"
            ))
            db.commit()


def down(db):
    """Additive migrations are never rolled back in production."""
    pass

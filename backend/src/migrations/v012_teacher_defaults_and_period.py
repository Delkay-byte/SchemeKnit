"""
Migration v012: Teacher profile defaults + lesson period column.

The teacher's reusable defaults (period, references, TLRs, keywords) belong on
the teacher profile, not re-typed on every lesson (PART 13). ``period`` is also
stored per lesson so a generated plan keeps the timetable slot the teacher
configured (PART 20). All additive and dialect-portable.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v012_teacher_defaults_and_period"
MIGRATION_NAME = "Teacher profile defaults and lesson period"


def up(db):
    inspector = sa_inspect(engine)

    # ── Teacher-level defaults (profile), so a teacher is not asked to re-type
    # school-level information on every lesson plan.
    if inspector.has_table("user_preferences"):
        cols = [c["name"] for c in inspector.get_columns("user_preferences")]
        wanted = {
            "default_period": "TEXT DEFAULT ''",
            "default_references": "TEXT DEFAULT '[]'",
            "default_tlrs": "TEXT DEFAULT '[]'",
            "default_keywords": "TEXT DEFAULT '[]'",
            "default_core_competencies": "TEXT DEFAULT '[]'",
        }
        for col, ddl in wanted.items():
            if col not in cols:
                db.execute(text(
                    f"ALTER TABLE user_preferences ADD COLUMN {col} {ddl}"))
                db.commit()

    # ── Per-lesson timetable period (e.g. "1st & 2nd"), configured by the
    # teacher, never invented by the generator.
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
        if "period" not in cols:
            db.execute(text(
                "ALTER TABLE lesson_plans ADD COLUMN period TEXT DEFAULT ''"))
            db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; no-op."""
    pass

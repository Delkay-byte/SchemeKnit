"""
Migration v036: Per-scheme lesson configuration (guided configuration step).

The teacher's lesson-configuration choices — school name, teacher's name,
class size, reference, lesson duration, period allocation, periods per week
and the days the subject is taught — are configured per plan AFTER extraction
and BEFORE generation (Phase 2). They persist on the scheme row as one JSON
document so the configuration survives navigation, reload and job resume, and
so an export re-renders with exactly the values the teacher confirmed.

Additive and dialect-portable: one nullable JSON column on ``schemes``.
Existing schemes keep NULL (unconfigured) and the generation flow falls back
to the teacher's saved preferences exactly as before. No data is rewritten.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v036_scheme_lesson_config"
MIGRATION_NAME = "Per-scheme guided lesson configuration"


def up(db):
    """Add ``schemes.lesson_config`` (idempotent)."""
    inspector = sa_inspect(engine)
    if not inspector.has_table("schemes"):
        return
    cols = [c["name"] for c in inspector.get_columns("schemes")]
    if "lesson_config" not in cols:
        db.execute(text(
            "ALTER TABLE schemes ADD COLUMN lesson_config JSON DEFAULT '{}'"))
        db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; no-op."""
    pass

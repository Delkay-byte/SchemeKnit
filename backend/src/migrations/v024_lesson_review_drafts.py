"""
Migration v024: Per-lesson review drafts on schemes (Sections H/Q).

Teachers can inspect and edit lesson-level review data (keywords, Other TLRs,
competencies, structured references) BEFORE generation. Drafts are stored on
the scheme keyed by lesson sequence so generation applies them per lesson.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v024_lesson_review_drafts"
MIGRATION_NAME = "Per-lesson review drafts on schemes"


def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("schemes"):
        return
    cols = [c["name"] for c in inspector.get_columns("schemes")]
    if "lesson_review_drafts" not in cols:
        db.execute(text(
            "ALTER TABLE schemes ADD COLUMN lesson_review_drafts TEXT DEFAULT '{}'"
        ))
        db.commit()


def down(db):
    """SQLite does not support DROP COLUMN; no-op."""
    pass

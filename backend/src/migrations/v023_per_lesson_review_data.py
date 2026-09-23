"""
Migration v023: Per-lesson review data (Sections F–N).

Adds provenance-aware columns to ``lesson_plans``:

- ``source_tlrs``  — TLRs FROM THE SCHEME (subject + source week + indicator)
- ``other_tlrs``   — teacher-added resources for THIS lesson only
- ``structured_references`` — {type,title,author_publisher,page,notes}

Existing lessons remain readable: new columns default to empty lists.
Existing ``teaching_learning_resources`` / ``references`` / ``keywords`` /
``core_competencies`` are untouched (backward compatible).
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v023_per_lesson_review_data"
MIGRATION_NAME = "Per-lesson source/other TLRs and structured references"


def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("lesson_plans"):
        return
    cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
    wanted = {
        "source_tlrs": "TEXT DEFAULT '[]'",
        "other_tlrs": "TEXT DEFAULT '[]'",
        "structured_references": "TEXT DEFAULT '[]'",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            db.execute(text(f"ALTER TABLE lesson_plans ADD COLUMN {col} {ddl}"))
            db.commit()


def down(db):
    """SQLite does not support DROP COLUMN; no-op."""
    pass

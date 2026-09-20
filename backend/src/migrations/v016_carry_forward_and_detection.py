"""
Migration v016: Indicator carry-forward + multi-subject document detection.

Two additive, dialect-portable changes:

1. ``lesson_plans`` learns the difference between the SOURCE curriculum week
   (existing ``week_number``) and the ACTUAL teaching week the lesson is
   delivered in (``teaching_week``), plus a ``carry_forward`` flag. This is the
   data needed to represent indicators that carry forward to a later teaching
   week without losing their curriculum origin (§7-§9).

2. ``schemes`` learns the detected document structure for documents that pack
   several subjects into one file (§4): the document title, the subjects
   detected, the detection confidence, and the serialized subject sections so a
   teacher can confirm which section to use.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v016_carry_forward_and_detection"
MIGRATION_NAME = "Indicator carry-forward and multi-subject detection"


def up(db):
    inspector = sa_inspect(engine)

    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
        if "teaching_week" not in cols:
            db.execute(text(
                "ALTER TABLE lesson_plans ADD COLUMN teaching_week INTEGER"))
            db.commit()
        if "carry_forward" not in cols:
            db.execute(text(
                "ALTER TABLE lesson_plans ADD COLUMN carry_forward BOOLEAN DEFAULT FALSE"))
            db.commit()

    if inspector.has_table("schemes"):
        cols = [c["name"] for c in inspector.get_columns("schemes")]
        wanted = {
            "document_title": "TEXT DEFAULT ''",
            "detected_subjects": "TEXT DEFAULT '[]'",
            "detection_status": "TEXT DEFAULT ''",
            "subject_sections": "TEXT DEFAULT '[]'",
        }
        for col, ddl in wanted.items():
            if col not in cols:
                db.execute(text(f"ALTER TABLE schemes ADD COLUMN {col} {ddl}"))
                db.commit()


def down(db):
    """SQLite doesn't support DROP COLUMN; no-op."""
    pass

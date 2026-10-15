"""
Migration v033: structured assessment for lesson plans (Phase 3).

Two additive JSON columns:
  * ``assessment_items``  — DoK-levelled assessment prompts with marking
    guidance; empty for early-years/single-check lessons.
  * ``assessment_rubric`` — the analytic marking rubric for the lesson when
    its assessment genuinely marks a learner-created product or performance;
    NULL when a short oral/written check is sufficient.

Both are generated deterministically (AI OFF) and are optional: existing
lesson rows stay valid with empty defaults, and no existing data is rewritten.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v033_assessment_structure"
MIGRATION_NAME = "Structured assessment prompts and analytic rubric"


def up(db):
    """Add lesson_plans.assessment_items / assessment_rubric if missing."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    if "assessment_items" not in cols:
        db.execute(text(
            "ALTER TABLE lesson_plans ADD COLUMN assessment_items JSON"
        ))
        db.commit()
    if "assessment_rubric" not in cols:
        db.execute(text(
            "ALTER TABLE lesson_plans ADD COLUMN assessment_rubric JSON"
        ))
        db.commit()


def down(db):
    """Additive migrations are never rolled back."""
    pass

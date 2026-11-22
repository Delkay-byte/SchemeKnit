"""
Migration v056: WAPEF academic-year profile (Deep Hope + Storyline).

Deep Hope and Storyline are chosen once per teacher per academic year and
reused on every WAPEF lesson plan in that year. The row is keyed by
(teacher_id, academic_year), so a new year starts empty and can never
silently inherit or overwrite a prior year's values.

Additive: creates one new table. Existing rows and plans are untouched.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v056_wapef_annual_profile"
MIGRATION_NAME = "WAPEF academic-year Deep Hope and Storyline"


def up(db):
    """Create the annual profile table (idempotent)."""
    if sa_inspect(engine).has_table("wapef_annual_profiles"):
        return
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS wapef_annual_profiles ("
        "id VARCHAR PRIMARY KEY, "
        "teacher_id VARCHAR NOT NULL REFERENCES users(id), "
        "academic_year VARCHAR NOT NULL DEFAULT '', "
        "deep_hope TEXT NOT NULL DEFAULT '', "
        "storyline TEXT NOT NULL DEFAULT '', "
        "created_at TIMESTAMP, "
        "updated_at TIMESTAMP, "
        "CONSTRAINT uq_wapef_annual_teacher_year "
        "UNIQUE (teacher_id, academic_year)"
        ")"
    ))
    db.commit()


def down(db):
    """Dropping the table would destroy teacher choices; no-op."""
    pass

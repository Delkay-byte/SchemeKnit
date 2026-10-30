"""
Migration v035: Zeli generation provenance and whole-lesson cache.

Additive, dialect-portable changes:

* ``lesson_plans.ai_provider`` / ``ai_model`` / ``generation_method`` - durable
  provenance for AI-produced content and the method that produced it.
* ``zeli_generation_cache`` - whole-lesson provider output keyed by method,
  provider, model, prompt version and every material lesson/config input. It is
  separate from the section-level enrichment cache because it is created before
  a lesson row exists.

Existing rows keep empty provenance and are valid; no data is rewritten.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v035_zeli_generation_provenance_cache"
MIGRATION_NAME = "Zeli generation provenance and whole-lesson cache"


def up(db):
    """Add lesson provenance columns and the Zeli cache table (idempotent)."""
    inspector = sa_inspect(engine)
    cols = []
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]

    for name in ("ai_provider", "ai_model", "generation_method"):
        if name not in cols:
            default = "standard" if name == "generation_method" else ""
            db.execute(text(
                f"ALTER TABLE lesson_plans ADD COLUMN {name} "
                f"VARCHAR DEFAULT '{default}'"
            ))
            db.commit()

    if not inspector.has_table("zeli_generation_cache"):
        db.execute(text(
            "CREATE TABLE zeli_generation_cache ("
            "id VARCHAR NOT NULL PRIMARY KEY, "
            "cache_key VARCHAR NOT NULL UNIQUE, "
            "content TEXT DEFAULT '', "
            "provider VARCHAR DEFAULT '', "
            "model VARCHAR DEFAULT '', "
            "generation_method VARCHAR DEFAULT 'zeli', "
            "created_at TIMESTAMP"
            ")"
        ))
        db.commit()


def down(db):
    """Additive migrations are never rolled back."""
    pass

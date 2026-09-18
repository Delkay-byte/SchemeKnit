"""
Migration v001: Add educational taxonomy and curriculum profile fields.

Adds new columns to existing tables and creates new tables
for the complete Ghana educational taxonomy.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine, generate_id


MIGRATION_NAME = "Educational taxonomy and curriculum profiles"


def up(db):
    """Apply migration."""
    inspector = sa_inspect(engine)
    
    # Add educational_level to schemes if not exists
    if inspector.has_table("schemes"):
        cols = [c["name"] for c in inspector.get_columns("schemes")]
        if "educational_level" not in cols:
            db.execute(text("ALTER TABLE schemes ADD COLUMN educational_level VARCHAR DEFAULT 'Junior High School'"))
    
    # Add educational_level and template_id to lesson_plans if not exists
    if inspector.has_table("lesson_plans"):
        cols = [c["name"] for c in inspector.get_columns("lesson_plans")]
        if "educational_level" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN educational_level VARCHAR DEFAULT 'Junior High School'"))
        if "template_id" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN template_id VARCHAR"))
        if "essential_questions" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN essential_questions TEXT DEFAULT '[]'"))
        if "keywords" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN keywords TEXT DEFAULT '[]'"))
        if "core_competencies" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN core_competencies TEXT DEFAULT '[]'"))
        if "homework" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN homework TEXT DEFAULT ''"))
        if "differentiation" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN differentiation TEXT DEFAULT ''"))
        if "remediation" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN remediation TEXT DEFAULT ''"))
        if "extension" not in cols:
            db.execute(text("ALTER TABLE lesson_plans ADD COLUMN extension TEXT DEFAULT ''"))
    
    db.commit()


def down(db):
    """Rollback migration."""
    db.commit()

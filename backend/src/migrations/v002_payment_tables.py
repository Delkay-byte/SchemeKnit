"""
Migration v002: Add payment, entitlement, and subscription tables.

Creates new tables for the commercial system.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine, Base


MIGRATION_NAME = "Payment, entitlement, and subscription tables"


def up(db):
    """Apply migration - create new tables."""
    Base.metadata.create_all(bind=engine)
    db.commit()


def down(db):
    """Rollback migration."""
    db.commit()

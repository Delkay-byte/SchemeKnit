"""
SchemeKnit Database Migration System

Versioned, non-destructive migrations with rollback support.
Tracks applied migrations in a separate table.
"""

import os
import importlib
import inspect
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy.orm import Session

from .database import Base, engine, generate_id


class MigrationRecord(Base):
    __tablename__ = "teachflow_migrations"
    id = __import__('sqlalchemy').Column(__import__('sqlalchemy').String, primary_key=True)
    version = __import__('sqlalchemy').Column(__import__('sqlalchemy').String, nullable=False, unique=True)
    name = __import__('sqlalchemy').Column(__import__('sqlalchemy').String, nullable=False)
    applied_at = __import__('sqlalchemy').Column(__import__('sqlalchemy').DateTime, default=datetime.utcnow)
    checksum = __import__('sqlalchemy').Column(__import__('sqlalchemy').String, default="")


def ensure_migration_table():
    """Create the migration tracking table if it doesn't exist."""
    from sqlalchemy import Column, String, DateTime
    if not sa_inspect(engine).has_table("teachflow_migrations"):
        MigrationRecord.__table__.create(engine)


def get_applied_migrations() -> List[str]:
    """Get list of already-applied migration versions."""
    ensure_migration_table()
    from .database import SessionLocal
    db = SessionLocal()
    try:
        records = db.query(MigrationRecord).order_by(MigrationRecord.version).all()
        return [r.version for r in records]
    finally:
        db.close()


def apply_migration(version: str, name: str, up_fn: Callable, down_fn: Optional[Callable] = None):
    """Apply a single migration if not already applied."""
    from .database import SessionLocal
    ensure_migration_table()
    db = SessionLocal()
    try:
        existing = db.query(MigrationRecord).filter(MigrationRecord.version == version).first()
        if existing:
            return False
        up_fn(db)
        record = MigrationRecord(
            id=generate_id(),
            version=version,
            name=name,
            applied_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def rollback_migration(version: str, down_fn: Callable):
    """Rollback a migration."""
    from .database import SessionLocal
    ensure_migration_table()
    db = SessionLocal()
    try:
        record = db.query(MigrationRecord).filter(MigrationRecord.version == version).first()
        if not record:
            return False
        down_fn(db)
        db.delete(record)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_all_migrations():
    """Run all pending migrations in order."""
    from . import migrations as migration_module
    from .database import engine, Base, generate_id

    migration_dir = Path(migration_module.__file__).parent
    migration_files = sorted(migration_dir.glob("v*.py"))

    applied = get_applied_migrations()
    results = []

    for mf in migration_files:
        version = mf.stem
        if version in applied:
            continue

        spec = importlib.util.spec_from_file_location(f"migrations.{version}", mf)
        mod = importlib.util.module_from_spec(spec)

        # Inject database objects so relative imports (from ..database import ...)
        # resolve correctly even in PyInstaller-frozen builds.
        # We pre-populate sys.modules so that the migration's
        # "from ..database import engine" finds a resolvable parent.
        mod.__package__ = "src.migrations"
        import sys
        sys.modules["src"] = sys.modules.get("src", type(sys)("src"))
        sys.modules["src"].database = type(sys)("database")
        sys.modules["src"].database.engine = engine
        sys.modules["src"].database.Base = Base
        sys.modules["src"].database.generate_id = generate_id
        sys.modules["src.migrations"] = migration_module

        spec.loader.exec_module(mod)

        name = getattr(mod, 'MIGRATION_NAME', version)
        up_fn = getattr(mod, 'up', None)
        down_fn = getattr(mod, 'down', None)

        if up_fn:
            apply_migration(version, name, up_fn, down_fn)
            results.append((version, name, "applied"))

    return results

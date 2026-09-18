"""
Migration v004: Add commercial licensing tables and role-based authorization.

New tables:
- schools
- school_memberships
- school_licenses
- activation_codes
- platform_audit_logs
- license_cache

Updated tables:
- users: add role, school_id columns
- product_plans: add seat_limit column
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine


MIGRATION_NAME = "Commercial licensing and role-based authorization"


def up(db):
    """Apply migration."""
    inspector = sa_inspect(engine)

    # ── Update users table ────────────────────────────────────────────────────
    if inspector.has_table("users"):
        cols = [c["name"] for c in inspector.get_columns("users")]
        if "role" not in cols:
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'teacher'"))
        if "school_id" not in cols:
            db.execute(text("ALTER TABLE users ADD COLUMN school_id VARCHAR"))
        # Migrate existing is_admin users to role system
        db.execute(text("UPDATE users SET role = 'school_admin' WHERE is_admin = TRUE AND role = 'teacher'"))

    # ── Update product_plans table ────────────────────────────────────────────
    if inspector.has_table("product_plans"):
        cols = [c["name"] for c in inspector.get_columns("product_plans")]
        if "seat_limit" not in cols:
            db.execute(text("ALTER TABLE product_plans ADD COLUMN seat_limit INTEGER DEFAULT 10"))

    # ── Create schools table ──────────────────────────────────────────────────
    if not inspector.has_table("schools"):
        db.execute(text("""
            CREATE TABLE schools (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                school_code VARCHAR NOT NULL UNIQUE,
                contact_name VARCHAR DEFAULT '',
                contact_phone VARCHAR DEFAULT '',
                contact_email VARCHAR DEFAULT '',
                address TEXT DEFAULT '',
                status VARCHAR DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    # ── Create school_memberships table ───────────────────────────────────────
    if not inspector.has_table("school_memberships"):
        db.execute(text("""
            CREATE TABLE school_memberships (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                school_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                status VARCHAR DEFAULT 'active',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, school_id)
            )
        """))
        db.execute(text("CREATE INDEX ix_membership_user_school ON school_memberships(user_id, school_id)"))

    # ── Create school_licenses table ──────────────────────────────────────────
    if not inspector.has_table("school_licenses"):
        db.execute(text("""
            CREATE TABLE school_licenses (
                id VARCHAR PRIMARY KEY,
                school_id VARCHAR NOT NULL,
                product_plan_id VARCHAR NOT NULL,
                license_code VARCHAR NOT NULL UNIQUE,
                status VARCHAR DEFAULT 'pending',
                start_date DATE NOT NULL,
                expiry_date DATE NOT NULL,
                seat_limit INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX ix_license_school ON school_licenses(school_id)"))
        db.execute(text("CREATE INDEX ix_license_code ON school_licenses(license_code)"))

    # ── Create activation_codes table ─────────────────────────────────────────
    if not inspector.has_table("activation_codes"):
        db.execute(text("""
            CREATE TABLE activation_codes (
                id VARCHAR PRIMARY KEY,
                license_id VARCHAR NOT NULL,
                code VARCHAR NOT NULL UNIQUE,
                status VARCHAR DEFAULT 'active',
                used_by_school_id VARCHAR,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX ix_activation_code ON activation_codes(code)"))

    # ── Create platform_audit_logs table ──────────────────────────────────────
    if not inspector.has_table("platform_audit_logs"):
        db.execute(text("""
            CREATE TABLE platform_audit_logs (
                id VARCHAR PRIMARY KEY,
                actor_id VARCHAR NOT NULL,
                actor_role VARCHAR NOT NULL,
                action VARCHAR NOT NULL,
                target_type VARCHAR DEFAULT '',
                target_id VARCHAR DEFAULT '',
                details JSON DEFAULT '{}',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX ix_platform_audit_actor ON platform_audit_logs(actor_id)"))
        db.execute(text("CREATE INDEX ix_platform_audit_timestamp ON platform_audit_logs(timestamp)"))

    # ── Create license_cache table ────────────────────────────────────────────
    if not inspector.has_table("license_cache"):
        db.execute(text("""
            CREATE TABLE license_cache (
                id VARCHAR PRIMARY KEY,
                school_id VARCHAR NOT NULL,
                license_code VARCHAR NOT NULL,
                plan_name VARCHAR DEFAULT '',
                seat_limit INTEGER DEFAULT 10,
                features JSON DEFAULT '[]',
                expiry_date DATE NOT NULL,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                validated_at TIMESTAMP,
                signature VARCHAR DEFAULT ''
            )
        """))

    db.commit()


def down(db):
    """Rollback migration."""
    db.execute(text("DROP TABLE IF EXISTS license_cache"))
    db.execute(text("DROP TABLE IF EXISTS platform_audit_logs"))
    db.execute(text("DROP TABLE IF EXISTS activation_codes"))
    db.execute(text("DROP TABLE IF EXISTS school_licenses"))
    db.execute(text("DROP TABLE IF EXISTS school_memberships"))
    db.execute(text("DROP TABLE IF EXISTS schools"))
    db.commit()

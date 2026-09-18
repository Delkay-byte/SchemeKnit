"""
SchemeKnit Production Database Reset & Verification
===================================================

Creates a CLEAN production database:
  1. Applies all migrations (v001 → current)
  2. Seeds ONLY legitimate system/product configuration:
     - Ghana public holidays
     - Payment configuration (product catalog)
     - Product plans (FREE_TEACHER, TEACHER_PRO, SCHOOL)
     - Approved system templates
  3. Verifies ZERO customer data:
     users=0, schools=0, memberships=0, licenses=0, activation_codes=0,
     payments=0, subscriptions=0, schemes=0, lessons=0, jobs=0, exports=0,
     customer_templates=0, sessions/tokens=0

Usage
-----
    # Create/verify the production database pointed at by DATABASE_URL
    python -m src.tools.production_reset

    # Also wipe and recreate (DESTRUCTIVE — needs --confirm)
    python -m src.tools.production_reset --reset --confirm

The script NEVER touches TEST_DATABASE_URL. Tests must use their own DB.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure src is importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_settings  # noqa: E402
from src.logging_config import setup_logging, get_logger  # noqa: E402

setup_logging("INFO")
logger = get_logger()


# ── Tables that must be EMPTY (customer/transactional data) ─────────────

MUST_BE_ZERO = {
    "users":                     "All user accounts (platform admin, school admin, teacher)",
    "schools":                   "Schools",
    "school_memberships":        "School memberships (teacher↔school)",
    "school_licenses":           "School licenses",
    "activation_codes":          "License activation codes",
    "payments":                  "Payment records",
    "payment_audit":             "Payment audit records",
    "subscriptions":             "Individual teacher subscriptions",
    "individual_entitlements":   "Individual entitlements (AI/feature)",
    "schemes":                   "Uploaded schemes of work",
    "lessons":                   "Generated lesson plans",
    "generation_jobs":           "Generation jobs",
    "export_events":             "Export events (DOCX/PDF/XLSX/ZIP)",
    "custom_templates":          "Custom templates created by users",
    "template_versions":         "Template versions created by users",
    "password_reset_tokens":     "Password reset tokens",
    "ai_caches":                 "AI response caches",
    "workflow_states":           "Workflow states",
}

# Tables that are INTENTIONALLY non-zero (system configuration)

MAY_BE_NONZERO = {
    "schema_migrations":         "Migration history (required)",
    "holidays":                  "Ghana public holidays (system seed)",
    "payment_config":            "Payment instructions (product config)",
    "product_plans":             "Product plan definitions (FREE_TEACHER, TEACHER_PRO, SCHOOL)",
    # System templates are approved product configuration
}


def count_rows(db, table: str) -> int:
    from sqlalchemy import text
    result = db.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
    return result.scalar() or 0


def table_exists(db, table: str) -> bool:
    from sqlalchemy import text
    result = db.execute(text(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:t"
        if "sqlite" in str(db.bind.url)
        else "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=:t"
    ), {"t": table})
    return (result.scalar() or 0) > 0


def verify_clean_db(db) -> tuple[list[str], list[str]]:
    """Return (failures, warnings). failures = customer data present."""
    failures: list[str] = []
    warnings: list[str] = []

    for table, description in MUST_BE_ZERO.items():
        if not table_exists(db, table):
            # Table doesn't exist yet — migration may not have created it
            # on this DB engine. Not a failure, just note it.
            warnings.append(f"table '{table}' does not exist ({description})")
            continue
        count = count_rows(db, table)
        if count > 0:
            failures.append(f"{table} = {count} (expected 0) — {description}")

    # Verify no platform admin exists
    from sqlalchemy import text
    if table_exists(db, "users"):
        admins = db.execute(text(
            "SELECT COUNT(*) FROM users WHERE role = 'platform_admin' AND is_active = 1"
        )).scalar() or 0
        if admins > 0:
            failures.append(
                f"platform_admin = {admins} (expected 0) — "
                "the production DB must have NO seeded admin; use /setup/platform-admin"
            )

    return failures, warnings


def list_nonzero_system(db) -> list[tuple[str, int]]:
    """Show intentionally-preserved system tables that have rows."""
    preserved = []
    for table, description in MAY_BE_NONZERO.items():
        if table_exists(db, table):
            count = count_rows(db, table)
            if count > 0:
                preserved.append((table, count))
    return preserved


def main():
    parser = argparse.ArgumentParser(
        description="Create and verify a clean SchemeKnit production database."
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop and recreate all tables before running migrations "
             "(DESTRUCTIVE — requires --confirm)",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Confirm the destructive --reset operation.",
    )
    args = parser.parse_args()

    settings = get_settings()
    db_url = settings.DATABASE_URL

    if "sqlite" in db_url:
        logger.warning("production_reset_using_sqlite",
                       note="SQLite is for development/desktop only. "
                            "Production must use PostgreSQL.")
    if "test" in db_url.lower():
        logger.error("production_reset_refused",
                     db_url=db_url,
                     note="Refusing to operate on what looks like a TEST database. "
                          "Set DATABASE_URL to the production database.")
        sys.exit(1)

    from src.database import engine, SessionLocal, Base

    if args.reset:
        if not args.confirm:
            logger.error("production_reset_needs_confirm",
                         note="--reset requires --confirm to acknowledge data loss.")
            sys.exit(1)
        logger.info("production_reset_dropping_tables")
        Base.metadata.drop_all(bind=engine)

    # ── Run migrations ──────────────────────────────────────────────────
    from src.database import init_db
    init_db()

    from src.migration_runner import run_all_migrations
    results = run_all_migrations()
    if results:
        for v, n, s in results:
            logger.info("migration_applied", version=v, name=n, status=s)

    # ── Seed system configuration ───────────────────────────────────────
    # (imported from main.py to reuse the exact same seed logic)
    from src.main import _seed_global_holidays, _seed_payment_config, _seed_product_plans
    _seed_global_holidays()
    _seed_payment_config()
    _seed_product_plans()

    # ── Verify ──────────────────────────────────────────────────────────
    db = SessionLocal()
    try:
        failures, warnings = verify_clean_db(db)
        preserved = list_nonzero_system(db)
    finally:
        db.close()

    # ── Report ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SCHEMEKNIT PRODUCTION DATABASE VERIFICATION")
    print("=" * 70)
    print(f"  DATABASE_URL: {db_url}")
    print()

    print("- ZERO-CUSTOMER-DATA CHECK " + "-" * 41)
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
    else:
        print("  ALL CUSTOMER TABLES ARE EMPTY (PASS)")
    print()

    print("- SYSTEM CONFIGURATION (intentionally preserved) " + "-" * 19)
    if preserved:
        for table, count in preserved:
            print(f"  OK    {table:28s} {count:5d} rows  ({MAY_BE_NONZERO.get(table, '')})")
    else:
        print("  (none seeded yet)")
    print()

    if warnings:
        print("- WARNINGS " + "-" * 59)
        for w in warnings:
            print(f"  WARN  {w}")
        print()

    print("=" * 70)
    if failures:
        print("RESULT: FAIL — customer data present, database is NOT production-clean")
        sys.exit(1)
    else:
        print("RESULT: PASS — clean production database, system configuration only")
        print()
        print("Next steps:")
        print("  1. Set PLATFORM_ADMIN_BOOTSTRAP_SECRET to a strong value")
        print("  2. Deploy the application")
        print("  3. Open /setup/platform-admin to create the first platform admin")
        print("  4. Remove or rotate the bootstrap secret")
        sys.exit(0)


if __name__ == "__main__":
    main()

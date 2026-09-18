#!/usr/bin/env python3
"""
SchemeKnit Platform Admin Bootstrap Script

Creates the first Platform Administrator user. Requires local filesystem access.
This is the ONLY supported way to create a platform_admin user.

Usage:
    python -m src.tools.create_platform_admin --email admin@bloomcore.com --password Secret123 --name "Admin Name"

Environment:
    TEACHFLOW_DATA_DIR  - Override database directory (default: ~/teachflow_data)
"""

import argparse
import datetime
import sys
import os

def main():
    parser = argparse.ArgumentParser(
        description="Create a SchemeKnit Platform Administrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.tools.create_platform_admin --email admin@bloomcore.com --password MyPass123
    python -m src.tools.create_platform_admin --email admin@bloomcore.com --password MyPass123 --name "Kobla Saviour"
    TEACHFLOW_DATA_DIR=/custom/path python -m src.tools.create_platform_admin --email admin@bloomcore.com --password MyPass123
        """
    )
    parser.add_argument("--email", required=True, help="Email address for the platform admin")
    parser.add_argument("--password", required=True, help="Password for the platform admin")
    parser.add_argument("--name", default="Platform Administrator", help="Full name (default: Platform Administrator)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    # PostgreSQL (production): honor an explicit DATABASE_URL first.
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql"):
        db_url = database_url
        db_label = "PostgreSQL (DATABASE_URL)"
    else:
        db_url = None
        db_label = None

    # Determine database path — check multiple locations
    candidates = []

    # 1. Environment variable override
    data_dir = os.environ.get("TEACHFLOW_DATA_DIR")
    if data_dir:
        candidates.append(os.path.join(data_dir, "teachflow.db"))

    # 2. Current working directory (dev mode: sqlite:///./teachflow.db)
    candidates.append(os.path.join(os.getcwd(), "teachflow.db"))

    # 3. AppData (Electron/packaged mode)
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "teachflow-desktop", "data", "teachflow.db"))

    # 4. ~/teachflow_data (fallback)
    candidates.append(os.path.expanduser("~/teachflow_data/teachflow.db"))

    db_path = None
    if not db_url:
        for path in candidates:
            if os.path.exists(path):
                db_path = path
                break

        if not db_path:
            print(f"\nERROR: Database not found. Searched:")
            for path in candidates:
                print(f"  - {path}")
            print(f"\nMake sure SchemeKnit has been run at least once, or set TEACHFLOW_DATA_DIR.")
            sys.exit(1)

    print(f"SchemeKnit Platform Admin Bootstrap")
    print(f"=" * 40)
    print(f"Database: {db_label or db_path}")

    # Import after verifying DB exists (avoids import errors if deps missing)
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    if db_url:
        engine = create_engine(db_url)
    else:
        if not os.path.exists(db_path):
            print(f"\nERROR: Database not found at {db_path}")
            print(f"Make sure SchemeKnit has been run at least once, or set TEACHFLOW_DATA_DIR.")
            sys.exit(1)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Check existing users
        result = db.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()

        result = db.execute(text("SELECT COUNT(*) FROM users WHERE role = 'platform_admin'"))
        admin_count = result.scalar()

        print(f"Existing users: {user_count}")
        print(f"Existing platform admins: {admin_count}")

        if admin_count > 0:
            print(f"\nA platform admin already exists ({admin_count} found).")
            if not args.force:
                response = input("Create another platform admin? [y/N]: ").strip().lower()
                if response != "y":
                    print("Aborted.")
                    sys.exit(0)
            else:
                print("Use --force to create additional platform admins.")

        # Enforce the same production password policy as every other account
        # creation path — the bootstrap account is not a backdoor around it.
        from src.validation import validate_password, validate_email, normalize_email
        ok, msg = validate_email(args.email)
        if not ok:
            print(f"\nERROR: {msg}")
            sys.exit(1)
        ok, msg = validate_password(args.password)
        if not ok:
            print(f"\nERROR: {msg}")
            sys.exit(1)

        # Check email uniqueness (normalized, so casing cannot create a dup)
        result = db.execute(text("SELECT id FROM users WHERE email = :email"),
                            {"email": normalize_email(args.email)})
        if result.fetchone():
            print(f"\nERROR: A user with email '{args.email}' already exists.")
            sys.exit(1)

        # Hash password
        from src.auth import hash_password
        hashed = hash_password(args.password)

        # Generate ID
        import uuid
        user_id = str(uuid.uuid4())

        # Insert platform admin (TRUE literals: valid on PostgreSQL and SQLite)
        # Email is stored normalized (lowercase) so login matching is stable.
        db.execute(text("""
            INSERT INTO users (id, email, full_name, hashed_password, is_admin, is_active, role, school_id)
            VALUES (:id, :email, :name, :password, TRUE, TRUE, 'platform_admin', NULL)
        """), {
            "id": user_id,
            "email": normalize_email(args.email),
            "name": args.name,
            "password": hashed,
        })

        # Write audit log
        db.execute(text("""
            INSERT INTO platform_audit_logs (id, actor_id, actor_role, action, target_type, target_id, details, timestamp)
            VALUES (:id, :actor_id, 'platform_admin', 'platform_admin_created', 'user', :target_id, :details, :now)
        """), {
            "id": str(uuid.uuid4()),
            "actor_id": user_id,
            "target_id": user_id,
            "now": datetime.datetime.utcnow(),
            "details": f'{{"email": "{args.email}", "method": "cli_bootstrap"}}',
        })

        db.commit()

        print(f"\nSUCCESS: Platform Administrator created!")
        print(f"  ID:    {user_id}")
        print(f"  Email: {args.email}")
        print(f"  Name:  {args.name}")
        print(f"  Role:  platform_admin")
        print(f"\nYou can now log in at the SchemeKnit login page with these credentials.")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()

"""
PostgreSQL safety tests for Phase 16.6 migrations (v021 / v022).

Two layers:

1. Static audit (always runs): no migration may pair BOOLEAN columns with
   integer defaults — that is what crashed Render with
   DatatypeMismatch on week_ending_derived.

2. Live PostgreSQL harness (runs when a scratch PostgreSQL URL is provided
   via POSTGRES_MIGRATION_TEST_URL or TEACHFLOW_TEST_DATABASE_URL):
   reproduces the production failure with the old SQL, applies the fixed
   migrations through the real runner, and asserts BOOLEAN/FALSE semantics.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_DIR / "src" / "migrations"
HARNESS = BACKEND_DIR / "tests" / "pg_migration_harness.py"

_UNSAFE_BOOL_DEFAULT = re.compile(
    r"BOOLEAN(?:\s+NOT\s+NULL)?\s+DEFAULT\s+[01]\b", re.IGNORECASE
)


def _normalise(source: str) -> str:
    """Collapse quotes/whitespace so split string literals are still matched."""
    return re.sub(r"[\"'\s]+", " ", source)


def _postgres_url():
    for key in ("POSTGRES_MIGRATION_TEST_URL", "TEACHFLOW_TEST_DATABASE_URL"):
        url = os.environ.get(key, "")
        if url.startswith("postgres"):
            return url
    return None


def test_no_postgres_unsafe_boolean_integer_defaults():
    """Every migration must use FALSE/TRUE (or no default) for BOOLEAN DDL."""
    offenders = []
    for path in sorted(MIGRATIONS_DIR.glob("v*.py")):
        normalised = _normalise(path.read_text(encoding="utf-8"))
        if _UNSAFE_BOOL_DEFAULT.search(normalised):
            offenders.append(path.name)
    assert not offenders, (
        "BOOLEAN columns with integer defaults (PostgreSQL DatatypeMismatch): "
        + ", ".join(offenders)
    )


def test_v021_and_v022_use_false_default():
    """Spot-check the exact Phase 16.6 statements."""
    v021 = (MIGRATIONS_DIR / "v021_week_ending_derived.py").read_text(encoding="utf-8")
    v022 = (MIGRATIONS_DIR / "v022_lesson_week_ending.py").read_text(encoding="utf-8")
    assert "week_ending_derived BOOLEAN NOT NULL DEFAULT FALSE" in _normalise(v021)
    normalised_v022 = _normalise(v022)
    assert "BOOLEAN NOT NULL DEFAULT FALSE" in normalised_v022
    assert "DEFAULT 0" not in normalised_v022


def test_no_sqlite_only_datetime_ddl_types():
    """PostgreSQL rejects the SQLite-only DATETIME type name.

    Regression guard: v028 crashed the Render deploy with psycopg
    UndefinedObject (type "datetime" does not exist) on
    ``ALTER TABLE entitlements ADD COLUMN starts_at DATETIME`` and the
    service failed its health check. TIMESTAMP is portable across SQLite
    and PostgreSQL (the v008 convention).
    """
    offenders = []
    for path in sorted(MIGRATIONS_DIR.glob("v*.py")):
        src = path.read_text(encoding="utf-8")
        # Ignore docstrings and comments: only literal DDL counts.
        src = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)
        src = re.sub(r"#.*", "", src)
        if re.search(r"\bDATETIME\b", src):
            offenders.append(path.name)
    assert not offenders, (
        "SQLite-only DATETIME in migration DDL (breaks PostgreSQL): "
        + ", ".join(offenders)
    )


@pytest.mark.skipif(
    _postgres_url() is None,
    reason="Set POSTGRES_MIGRATION_TEST_URL (scratch PostgreSQL) to run the live harness",
)
def test_postgres_v021_v022_migration_harness():
    """Run the production-like migration scenario against real PostgreSQL."""
    url = _postgres_url()
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    proc = subprocess.run(
        [sys.executable, str(HARNESS)],
        env=env,
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"harness failed (rc={proc.returncode})\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert '"ok": true' in proc.stdout.replace("'", '"')


def _scratch_postgres():
    url = _postgres_url()
    if not url:
        return None
    # Only ever touch a scratch database; refuse anything that is not named
    # like a test database.
    if "test" not in url.rsplit("/", 1)[-1].split("?")[0].lower():
        return None
    return url


def test_v050_migration_is_additive_and_clears_only_legacy_pending():
    """v050 adds pending columns; enrolled secrets survive, unverified ones go."""
    url = _scratch_postgres()
    if not url:
        pytest.skip("Set POSTGRES_MIGRATION_TEST_URL to a scratch test database")
    import importlib.util
    import sys
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from src import migrations as migration_module

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        conn.execute(text(
            "CREATE TABLE users (id VARCHAR PRIMARY KEY, email VARCHAR, "
            "mfa_enabled BOOLEAN DEFAULT FALSE, mfa_secret VARCHAR)"))
        conn.execute(text(
            "INSERT INTO users (id, email, mfa_enabled, mfa_secret) VALUES "
            "('u1', 'enrolled@test.local', TRUE, 'ACTIVESECRET'), "
            "('u2', 'legacy@test.local', FALSE, 'LEGACYSECRET')"))

    spec = importlib.util.spec_from_file_location(
        "v050_test", MIGRATIONS_DIR / "v050_user_mfa_pending.py")
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "src.migrations"
    sys.modules["src.migrations"] = migration_module
    spec.loader.exec_module(mod)
    mod.engine = engine
    with Session(engine) as db:
        mod.up(db)

    with engine.connect() as conn:
        cols = {c["name"] for c in __import__("sqlalchemy").inspect(engine).get_columns("users")}
        assert {"mfa_pending_secret", "mfa_pending_expires_at"} <= cols
        rows = dict(conn.execute(text(
            "SELECT email, mfa_secret FROM users")).fetchall())
    assert rows["enrolled@test.local"] == "ACTIVESECRET"
    assert rows["legacy@test.local"] is None
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
    engine.dispose()


def test_concurrent_setup_converges_on_one_pending_secret_on_postgres():
    from concurrent.futures import ThreadPoolExecutor
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from src.database import Base, User
    from src.routers.auth import _ensure_pending_mfa_secret

    url = _scratch_postgres()
    if not url:
        pytest.skip("Set POSTGRES_MIGRATION_TEST_URL to a scratch test database")
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    user_id = str(uuid.uuid4())
    with Session(engine) as db:
        db.add(User(id=user_id, email=f"race-{user_id[:8]}@test.local",
                    full_name="Race", hashed_password="x",
                    role="platform_admin", is_admin=True,
                    mfa_enabled=False))
        db.commit()

    def install(_):
        with Session(engine) as db:
            secret, _expires = _ensure_pending_mfa_secret(db, user_id)
            return secret

    with ThreadPoolExecutor(max_workers=8) as pool:
        secrets = list(pool.map(install, range(8)))
    assert len(set(secrets)) == 1
    Base.metadata.drop_all(engine)
    engine.dispose()

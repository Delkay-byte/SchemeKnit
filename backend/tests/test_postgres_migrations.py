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

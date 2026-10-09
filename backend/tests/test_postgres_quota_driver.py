"""Production-stack quota regression: PostgreSQL + psycopg3.

The default suite runs on SQLite, where the Oct 2026 quota incident did NOT
manifest: SQLite reports a truthful ``rowcount`` for
``INSERT ... ON CONFLICT DO NOTHING``, while the production stack
(PostgreSQL + psycopg3 + SQLAlchemy 2.0.35) reports ``rowcount == -1`` and
the old ``rowcount == 1`` check misread every insert as an already-counted
conflict — the counter stayed at ``used=0`` and the limit never bound.

These tests run ONLY when the suite is pointed at a real PostgreSQL, so they
act as the named gate for the driver behaviour production actually uses:

    TEACHFLOW_TEST_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db" \\
        pytest tests/test_postgres_quota_driver.py -q

They would have failed before the fix (``consumed`` stayed 0 and the counter
never incremented) and must keep passing on every dependency upgrade.
"""

from __future__ import annotations

import os
import sys
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import Base, User, UsageUnitDB, generate_id  # noqa: E402
from src.auth import hash_password  # noqa: E402
from src.usage_quota import (  # noqa: E402
    current_period_key, get_units_used, release_lesson_units,
    reserve_lesson_units,
)
from tests.conftest import make_user  # noqa: E402

TEST_URL = os.environ.get("TEACHFLOW_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_URL.startswith(("postgresql://", "postgresql+psycopg://")),
    reason="production-stack quota gate: set TEACHFLOW_TEST_DATABASE_URL "
           "to a postgresql(+psycopg) URL to run",
)


def test_reserve_increments_and_reads_back_across_sessions(db, db_engine):
    """Invariant H on the production driver: reserve → committed → visible."""
    user = make_user(db, email="pg_readback@test.com")
    period = current_period_key()

    r = reserve_lesson_units(db, user.id, "pg-scheme", ["P1", "P2"], 5,
                             period_key=period)
    assert r.allowed and r.consumed == 2 and r.remaining == 3

    fresh = sessionmaker(bind=db_engine)()
    try:
        assert get_units_used(fresh, user.id, period) == 2
    finally:
        fresh.close()


def test_fifth_permitted_sixth_refused_ledger_stays_at_five(db):
    """Invariants A + E on the production driver."""
    user = make_user(db, email="pg_limit@test.com")
    period = current_period_key()

    r = reserve_lesson_units(db, user.id, "pg-scheme",
                             [f"P{i}" for i in range(5)], 5, period_key=period)
    assert r.allowed and r.consumed == 5 and r.remaining == 0

    r2 = reserve_lesson_units(db, user.id, "pg-scheme", ["P5"], 5,
                              period_key=period)
    assert not r2.allowed and r2.reason == "quota_exceeded"
    assert get_units_used(db, user.id, period) == 5
    assert db.query(UsageUnitDB).filter_by(user_id=user.id).count() == 5


def test_duplicate_reservation_stays_free_and_release_restores_zero(db):
    """Invariants B + C on the production driver."""
    user = make_user(db, email="pg_idem@test.com")
    period = current_period_key()

    r = reserve_lesson_units(db, user.id, "pg-scheme", ["D1"], 5,
                             period_key=period)
    assert r.consumed == 1
    again = reserve_lesson_units(db, user.id, "pg-scheme", ["D1"], 5,
                                 period_key=period)
    assert again.allowed and again.consumed == 0
    assert get_units_used(db, user.id, period) == 1

    released = release_lesson_units(db, user.id, ["pg-scheme:D1"], period)
    assert released == 1
    assert get_units_used(db, user.id, period) == 0


def test_concurrent_reservations_cannot_oversubscribe_on_postgres():
    """Invariant G: 10 racing single-unit reservations against limit 5."""
    engine = create_engine(TEST_URL)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    setup = Session()
    user = User(
        id=generate_id(), email="pg_conc@test.com", full_name="PG Conc",
        hashed_password=hash_password("TestPass1!"), is_active=True,
        role="teacher", subscription_type="individual",
    )
    setup.add(user)
    setup.commit()
    uid = user.id
    setup.close()

    period = current_period_key()
    results = []
    lock = threading.Lock()

    def worker(i):
        s = Session()
        try:
            r = reserve_lesson_units(s, uid, "pg-scheme", [f"C{i}"], 5,
                                     period_key=period)
            with lock:
                results.append(r.allowed)
        except Exception:
            with lock:
                results.append(False)
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check = Session()
    try:
        used = get_units_used(check, uid, period)
    finally:
        check.close()
    engine.dispose()

    assert used <= 5
    assert sum(1 for a in results if a) <= 5
    assert used == sum(1 for a in results if a)

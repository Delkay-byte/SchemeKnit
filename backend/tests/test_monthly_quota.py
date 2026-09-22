"""
Monthly lesson-plan quota tests (PART W).

The Free Tier lesson-plan allowance is 5 per CALENDAR MONTH, enforced entirely
server-side by the usage ledger. One indicator → one period → one lesson →
one unit.
"""

import os
import sys
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import Base, User, generate_id
from src.auth import hash_password
from src.usage_quota import (
    current_period_key, get_units_used, reserve_lesson_units, release_lesson_units,
)
from src.entitlements import resolve_entitlement, FREE_TIER_LESSON_PLANS_PER_MONTH
from tests.conftest import make_user


def _free_teacher(db, email="quota@t.test"):
    """A free individual teacher (no entitlement row needed: free defaults)."""
    u = make_user(db, role="teacher", email=email)
    u.school_id = None
    u.subscription_type = "individual"
    db.commit()
    return u


class TestMonthlyQuotaModel:
    def test_current_period_key_is_yyyy_mm(self):
        assert current_period_key(datetime(2026, 1, 5)) == "2026-01"
        assert current_period_key(datetime(2026, 12, 31)) == "2026-12"

    def test_new_month_starts_at_zero_with_five_available(self, db):
        u = _free_teacher(db)
        assert get_units_used(db, u.id, "2026-01") == 0
        r = reserve_lesson_units(db, u.id, "s", ["A"], 5, period_key="2026-01")
        assert r.allowed and r.consumed == 1 and r.remaining == 4
        resolved = resolve_entitlement(db, u)
        assert resolved["generation_limit"] == FREE_TIER_LESSON_PLANS_PER_MONTH

    def test_generating_one_consumes_one(self, db):
        u = _free_teacher(db)
        reserve_lesson_units(db, u.id, "s", ["A"], 5, period_key="2026-03")
        assert get_units_used(db, u.id, "2026-03") == 1

    def test_generating_five_consumes_five_sixth_blocked(self, db):
        u = _free_teacher(db)
        r = reserve_lesson_units(
            db, u.id, "s", [f"B{i}" for i in range(5)], 5, period_key="2026-03")
        assert r.allowed and r.consumed == 5 and r.remaining == 0
        r2 = reserve_lesson_units(db, u.id, "s", ["B6"], 5, period_key="2026-03")
        assert not r2.allowed and r2.reason == "quota_exceeded"
        assert get_units_used(db, u.id, "2026-03") == 5

    def test_next_calendar_month_resets_allowance(self, db):
        u = _free_teacher(db)
        reserve_lesson_units(db, u.id, "s", [f"C{i}" for i in range(5)], 5,
                             period_key="2026-01")
        assert get_units_used(db, u.id, "2026-01") == 5
        # February is untouched and starts fresh at 5.
        assert get_units_used(db, u.id, "2026-02") == 0
        r = reserve_lesson_units(db, u.id, "s2", ["D1"], 5, period_key="2026-02")
        assert r.allowed and r.remaining == 4

    def test_failure_release_does_not_consume(self, db):
        u = _free_teacher(db)
        r = reserve_lesson_units(db, u.id, "s", ["E1", "E2"], 5, period_key="2026-04")
        assert r.consumed == 2
        released = release_lesson_units(db, u.id, r.reserved_keys, "2026-04")
        assert released == 2
        assert get_units_used(db, u.id, "2026-04") == 0

    def test_duplicate_request_does_not_double_consume(self, db):
        u = _free_teacher(db)
        r1 = reserve_lesson_units(db, u.id, "s", ["F1", "F2"], 5, period_key="2026-05")
        assert r1.consumed == 2
        # Same indicators, same scheme, same month → nothing new is charged.
        r2 = reserve_lesson_units(db, u.id, "s", ["F1", "F2"], 5, period_key="2026-05")
        assert r2.allowed and r2.consumed == 0
        assert get_units_used(db, u.id, "2026-05") == 2

    def test_regeneration_of_same_indicator_is_free(self, db):
        u = _free_teacher(db)
        reserve_lesson_units(db, u.id, "s", ["G1"], 5, period_key="2026-06")
        assert get_units_used(db, u.id, "2026-06") == 1
        # Regenerate the same lesson → replaces in place, no new unit.
        r = reserve_lesson_units(db, u.id, "s", ["G1"], 5, period_key="2026-06")
        assert r.consumed == 0
        assert get_units_used(db, u.id, "2026-06") == 1

    def test_selecting_two_of_twenty_consumes_two(self, db):
        u = _free_teacher(db)
        twenty = [f"H{i}" for i in range(20)]
        selected = twenty[:2]
        r = reserve_lesson_units(db, u.id, "s", selected, 5, period_key="2026-07")
        assert r.consumed == 2
        assert r.remaining == 3
        assert get_units_used(db, u.id, "2026-07") == 2

    def test_selecting_more_than_remaining_is_rejected(self, db):
        u = _free_teacher(db)
        r = reserve_lesson_units(
            db, u.id, "s", [f"I{i}" for i in range(6)], 5, period_key="2026-08")
        assert not r.allowed
        assert get_units_used(db, u.id, "2026-08") == 0

    def test_unlimited_plan_never_consumes(self, db):
        u = _free_teacher(db)
        r = reserve_lesson_units(db, u.id, "s", ["J1"], 0, period_key="2026-09")
        assert r.allowed and r.unlimited
        assert get_units_used(db, u.id, "2026-09") == 0


class TestConcurrentQuota:
    """Concurrent reservations must never oversubscribe the allowance."""

    def test_concurrent_reservations_cannot_oversubscribe(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'quota.db'}"
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        setup = Session()
        user = User(
            id=generate_id(), email="conc@t.test", full_name="Concurrent",
            hashed_password=hash_password("TestPass1!"), is_active=True,
            role="teacher", subscription_type="individual",
        )
        setup.add(user)
        setup.commit()
        uid = user.id
        setup.close()

        results = []
        lock = threading.Lock()

        def worker(i):
            s = Session()
            try:
                r = reserve_lesson_units(
                    s, uid, "scheme", [f"K{i}"], 5, period_key="2026-10")
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
        used = get_units_used(check, uid, "2026-10")
        check.close()
        engine.dispose()

        # THE invariant: never more than the allowance, and the counter equals
        # the number of successful reservations.
        assert used <= 5
        assert sum(1 for a in results if a) <= 5
        assert used == sum(1 for a in results if a)

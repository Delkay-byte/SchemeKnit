"""Ten-teacher shared-peer isolation and broad IP-signal tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base, RateLimitCounterDB
from src.login_security import account_key
from src.security import (
    AUTHENTICATED_BUDGETS, RATE_LIMITS, DbRateLimiter, RateLimiter,
    client_key, enforce_authenticated_budget,
)

PEER = "203.0.113.50"


def _budget(monkeypatch):
    limiter = RateLimiter()
    monkeypatch.setattr("src.security.get_rate_limiter", lambda: limiter)
    return limiter


def test_ten_teachers_do_not_exhaust_each_others_upload_budget(monkeypatch):
    _budget(monkeypatch)
    for i in range(10):
        for _ in range(10):
            enforce_authenticated_budget(f"teacher-{i}", "upload")


def test_one_teacher_exhaustion_does_not_block_another(monkeypatch):
    _budget(monkeypatch)
    limit = AUTHENTICATED_BUDGETS["generate"][0]
    for _ in range(limit):
        enforce_authenticated_budget("abuser", "generate")
    with pytest.raises(HTTPException) as exc:
        enforce_authenticated_budget("abuser", "generate")
    assert exc.value.status_code == 429
    enforce_authenticated_budget("honest", "generate")


def test_exports_are_per_account(monkeypatch):
    _budget(monkeypatch)
    limit = AUTHENTICATED_BUDGETS["export"][0]
    for _ in range(limit):
        enforce_authenticated_budget("exporter", "export")
    with pytest.raises(HTTPException):
        enforce_authenticated_budget("exporter", "export")
    enforce_authenticated_budget("other-exporter", "export")


def test_account_lockout_keys_are_independent():
    assert account_key("a@example.test") != account_key("b@example.test")


def test_ordinary_shared_peer_usage_does_not_trip_ip_breaker():
    limiter = RateLimiter()
    key = client_key(PEER)
    # 10 teachers x 20 generation requests = 200 in the window, below the
    # deliberate 300/min broad IP ceiling.
    for _ in range(200):
        assert limiter.is_allowed(key, "/api/generation/x", now=1000)[0]
    assert limiter.is_allowed(key, "/api/generation/x", now=1000)[0]


def test_ip_breaker_still_blocks_after_sustained_abuse():
    limiter = RateLimiter()
    key = client_key(PEER)
    budget = max(m for p, m, _ in RATE_LIMITS if p == "/api/generation/")
    for _ in range(budget):
        assert limiter.is_allowed(key, "/api/generation/x", now=1000)[0]
    assert limiter.is_allowed(key, "/api/generation/x", now=1000)[0] is False


def test_different_peer_addresses_have_separate_ip_buckets():
    limiter = RateLimiter()
    a = client_key("203.0.113.51")
    b = client_key("203.0.113.52")
    for _ in range(300):
        limiter.is_allowed(a, "/api/generation/x", now=1000)
    assert limiter.is_allowed(a, "/api/generation/x", now=1000)[0] is False
    assert limiter.is_allowed(b, "/api/generation/x", now=1000)[0] is True


def test_db_limiter_is_shared_across_instances(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'counters.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    first = DbRateLimiter(Session)
    second = DbRateLimiter(Session)
    for _ in range(5):
        assert first.is_allowed_for("same", "test", 10, 60, now=1000)[0]
    for _ in range(5):
        assert second.is_allowed_for("same", "test", 10, 60, now=1000)[0]
    assert second.is_allowed_for("same", "test", 10, 60, now=1000)[0] is False


def test_db_limiter_concurrent_calls_are_bounded(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'counters-concurrent.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def call(_):
        try:
            return DbRateLimiter(Session).is_allowed_for(
                "same", "test", 10, 60, now=1000)[0]
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(30)))
    assert sum(1 for r in results if r) <= 10

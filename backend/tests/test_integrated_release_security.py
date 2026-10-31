"""Integrated ten-teacher shared-peer acceptance for the four workstreams."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src import ai_spend, storage_quota  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.engines import zeli_generation as zg  # noqa: E402
from src.security import (  # noqa: E402
    AUTHENTICATED_BUDGETS, RateLimiter, client_key,
    enforce_authenticated_budget,
)

PEER = "198.51.100.77"


@pytest.fixture(autouse=True)
def _settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ten_teachers_keep_independent_allowances_on_one_peer(db, monkeypatch):
    limiter = RateLimiter()
    monkeypatch.setattr("src.security.get_rate_limiter", lambda: limiter)

    # Ordinary combined traffic from ten teachers using the same Render peer
    # stays well below the broad IP breaker.
    for teacher in range(10):
        user_id = f"teacher-{teacher}"
        enforce_authenticated_budget(user_id, "upload")
        enforce_authenticated_budget(user_id, "generate")
        enforce_authenticated_budget(user_id, "export")
        enforce_authenticated_budget(user_id, "resume")
        reservation = storage_quota.reserve(
            db, user_id,
            object_key=f"production/uploads/{user_id}/scheme.docx",
            size_bytes=1024 * 1024,
            idempotency_key=f"upload-{teacher}",
        )
        storage_quota.commit(db, reservation)
        assert limiter.is_allowed(
            client_key(PEER), "/api/generation/x")[0]

    for teacher in range(10):
        usage = storage_quota.usage(db, f"teacher-{teacher}")
        assert usage["used_bytes"] == 1024 * 1024
        assert usage["used_bytes"] < usage["quota_bytes"]

    # One abusive account exhausts only its own generation allowance.
    limit = AUTHENTICATED_BUDGETS["generate"][0]
    for _ in range(limit):
        enforce_authenticated_budget("abuser", "generate")
    with pytest.raises(HTTPException) as exc:
        enforce_authenticated_budget("abuser", "generate")
    assert exc.value.status_code == 429
    enforce_authenticated_budget("teacher-0", "generate")
    assert storage_quota.usage(db, "teacher-0")["used_bytes"] == 1024 * 1024


def test_global_ai_budget_stop_does_not_consume_teacher_credits(
        db, monkeypatch):
    monkeypatch.setenv("AI_MONTHLY_BUDGET_USD", "0.0001")
    monkeypatch.setenv("AI_DAILY_BUDGET_USD", "0")
    monkeypatch.setenv("AI_DEEPSEEK_MONTHLY_BUDGET_USD", "0")
    monkeypatch.setenv("AI_GROQ_MONTHLY_BUDGET_USD", "0")
    get_settings.cache_clear()
    from src.database import AIUsageEventDB

    class Provider:
        model = "deepseek-flash"
        last_error = None
        last_cache_hit = False
        last_usage = None
        calls = 0

        def is_available(self):
            return True

        def get_name(self):
            return "deepseek"

        def generate_lesson_v2(self, **kwargs):
            self.calls += 1
            return {}

    provider = Provider()
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_content(
            provider=provider,
            context={"subject": "Science", "class_level": "Basic 9"},
            db=db, user_id="teacher-1", request_id="job-1",
        )
    assert exc.value.status_code == 503
    assert provider.calls == 0
    # No teacher generation credit was recorded for a request that never ran.
    assert db.query(AIUsageEventDB).count() == 0
    status = ai_spend.budget_status(db)
    assert status["monthly"]["budget_usd"] == 0.0001


def test_storage_of_one_teacher_is_not_visible_to_another(db):
    storage_quota.reserve(
        db, "teacher-a", object_key="production/uploads/a/a.docx",
        size_bytes=2048)
    other = storage_quota.usage(db, "teacher-b")
    assert other["used_bytes"] == 0
    assert other["reserved_bytes"] == 0

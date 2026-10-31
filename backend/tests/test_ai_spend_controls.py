"""Provider spend controls: budgets, usage accounting and hard stops.

No live provider is called. Fakes report the same ``last_usage`` shape as the
real DeepSeek/Groq transports.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src import ai_spend  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.database import (  # noqa: E402
    AIProviderUsageDB, AISpendCounterDB, AIUsageEventDB,
)
from src.engines import zeli_generation as zg  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _set(monkeypatch, **values):
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class UsageProvider:
    def __init__(self, name="deepseek", model="deepseek-flash", *,
                 error=None, usage=None, content=None):
        self.name = name
        self.model = model
        self.error = error
        self.usage = usage
        self.content = content or {
            "learning_objectives": ["a", "b"],
            "prior_knowledge": "prior",
            "key_vocabulary": ["word"],
            "resources": {"source_resources": ["chart"]},
            "starter": {"activity": "start"},
            "main_learning": {
                "phase1": {"name": "P1", "activity": "one"},
                "phase2": {"name": "P2", "activity": "two"},
            },
            "assessment": {"activity": "assess"},
            "plenary": {"activity": "end"},
            "differentiation": {"support": "s", "core": "c", "extension": "e"},
        }
        self.calls = 0
        self.last_cache_hit = False
        self.last_error = None
        self.last_usage = None

    def is_available(self):
        return True

    def get_name(self):
        return self.name

    def generate_lesson_v2(self, **kwargs):
        self.calls += 1
        if self.error:
            self.last_error = self.error
            return {}
        self.last_usage = dict(self.usage or {
            "provider": self.name,
            "model": self.model,
            "input_tokens": 1200,
            "cached_input_tokens": 200,
            "output_tokens": 800,
            "total_tokens": 2000,
        })
        return json.loads(json.dumps(self.content))


def _context():
    return {
        "subject": "Science", "class_level": "Basic 9",
        "strand": "Matter", "sub_strand": "Compounds",
        "indicator_code": "B9.1.1.1", "indicator_text": "Name compounds",
        "duration_minutes": 60,
    }


def test_pricing_uses_peak_deepseek_and_groq_rates():
    deep = ai_spend.cost_micros(
        "deepseek", input_tokens=1_000_000, output_tokens=1_000_000)
    assert deep == 1_500_000  # $1.50 = peak input 0.30 + output 1.20
    groq = ai_spend.cost_micros(
        "groq", input_tokens=1_000_000, output_tokens=1_000_000)
    assert groq == 750_000  # $0.75 = 0.15 + 0.60
    cached = ai_spend.cost_micros(
        "deepseek", input_tokens=1_000_000, cached_input_tokens=1_000_000,
        output_tokens=0)
    assert cached == 6_000  # cache-hit input only


def test_successful_attempt_records_actual_usage_and_settles(db):
    provider = UsageProvider()
    result = zg.generate_zeli_content(
        provider=provider, context=_context(), db=db,
        user_id="teacher-1", request_id="req-1")
    assert result
    rows = db.query(AIProviderUsageDB).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "deepseek"
    assert row.input_tokens == 1200
    assert row.cached_input_tokens == 200
    assert row.output_tokens == 800
    assert row.usage_source == "actual"
    assert row.pricing_version == ai_spend.PRICING_VERSION
    assert row.cost_micros > 0
    assert row.outcome == "success"
    assert row.user_id == "teacher-1"
    assert row.request_id == "req-1"


def test_duplicate_finish_is_idempotent(db):
    attempt = ai_spend.begin_attempt(
        db, provider="deepseek", model="deepseek-flash",
        prompt_chars=1000, user_id="u", request_id="r")
    usage = {
        "input_tokens": 100, "output_tokens": 50,
        "cached_input_tokens": 0, "model": "deepseek-flash",
    }
    first = attempt.finish("success", usage=usage)
    second = attempt.finish("success", usage=usage)
    assert first == second
    assert db.query(AIProviderUsageDB).count() == 1
    counter = db.query(AISpendCounterDB).filter(
        AISpendCounterDB.scope == "monthly").one()
    assert counter.reserved_micros == 0
    assert counter.spent_micros == first


def test_failed_deepseek_then_groq_fallback_records_both(db):
    primary = UsageProvider(error="timeout")
    fallback = UsageProvider(
        name="groq", model="openai/gpt-oss-120b",
        usage={
            "provider": "groq", "model": "openai/gpt-oss-120b",
            "input_tokens": 900, "cached_input_tokens": 0,
            "output_tokens": 600, "total_tokens": 1500,
        })
    content, meta = zg.generate_zeli_with_fallback(
        primary=primary, fallback=fallback, context=_context(), db=db,
        user_id="teacher-1", request_id="job-1")
    assert content and meta["fallback_used"] is True
    by_provider = {
        row.provider: row for row in db.query(AIProviderUsageDB).all()
    }
    assert set(by_provider) == {"deepseek", "groq"}
    # The failed DeepSeek attempt is an estimated cost (no usage reported).
    assert by_provider["deepseek"].outcome == "failure"
    assert by_provider["deepseek"].usage_source == "estimated"
    assert by_provider["deepseek"].cost_micros > 0
    # Groq reports actual usage.
    assert by_provider["groq"].usage_source == "actual"
    assert by_provider["groq"].input_tokens == 900
    # No teacher credit is consumed here: that happens once at the router for
    # the one successful qualifying generation.
    assert db.query(AIUsageEventDB).count() == 0


def test_cache_hit_creates_no_usage_or_reservation(db):
    provider = UsageProvider()
    zg.generate_zeli_content(provider=provider, context=_context(), db=db)
    before = db.query(AIProviderUsageDB).count()
    zg.generate_zeli_content(provider=provider, context=_context(), db=db)
    assert provider.calls == 1
    assert db.query(AIProviderUsageDB).count() == before == 1


def test_auth_failure_without_a_provider_call_costs_nothing(db):
    provider = UsageProvider(error="missing_api_key")
    with pytest.raises(zg.ZeliGenerationError):
        zg.generate_zeli_content(provider=provider, context=_context(), db=db)
    row = db.query(AIProviderUsageDB).one()
    assert row.outcome == "failure"
    assert row.usage_source == "none"
    assert row.cost_micros == 0


def test_exhausted_budget_blocks_before_the_provider_is_called(db, monkeypatch):
    _set(monkeypatch, AI_MONTHLY_BUDGET_USD=0.0001,
         AI_DAILY_BUDGET_USD=0, AI_DEEPSEEK_MONTHLY_BUDGET_USD=0,
         AI_GROQ_MONTHLY_BUDGET_USD=0)
    provider = UsageProvider()
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_content(provider=provider, context=_context(), db=db)
    assert exc.value.status_code == 503
    assert provider.calls == 0
    assert db.query(AIProviderUsageDB).count() == 0
    status = ai_spend.budget_status(db)
    assert status["monthly"]["budget_usd"] == 0.0001
    assert status["monthly"]["spent_usd"] == 0
    assert status["monthly"]["reserved_usd"] == 0


def test_hard_budget_exhaustion_is_reported_as_paused(db, monkeypatch):
    _set(monkeypatch, AI_MONTHLY_BUDGET_USD=0.01, AI_DAILY_BUDGET_USD=0,
         AI_DEEPSEEK_MONTHLY_BUDGET_USD=0, AI_GROQ_MONTHLY_BUDGET_USD=0)
    monthly_key, _ = ai_spend.current_period_keys()
    db.add(AISpendCounterDB(
        id="counter-1", scope="monthly", period_key=monthly_key,
        provider="", spent_micros=10_000, reserved_micros=0,
        active_requests=0, warning_sent=False,
    ))
    db.commit()
    status = ai_spend.budget_status(db)
    assert status["monthly"]["paused"] is True
    assert status["monthly"]["remaining_usd"] == 0
    provider = UsageProvider()
    with pytest.raises(zg.ZeliGenerationError):
        zg.generate_zeli_content(provider=provider, context=_context(), db=db)
    assert provider.calls == 0


def test_budget_pause_does_not_call_the_fallback(db, monkeypatch):
    _set(monkeypatch, AI_MONTHLY_BUDGET_USD=0.0001,
         AI_DAILY_BUDGET_USD=0, AI_DEEPSEEK_MONTHLY_BUDGET_USD=0,
         AI_GROQ_MONTHLY_BUDGET_USD=0)
    primary = UsageProvider(error="timeout")
    fallback = UsageProvider(name="groq")
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_with_fallback(
            primary=primary, fallback=fallback, context=_context(), db=db)
    assert exc.value.status_code == 503
    assert getattr(exc.value, "budget_blocked", False) is True
    assert primary.calls == 0 and fallback.calls == 0


def test_per_teacher_concurrency_is_bounded(db, monkeypatch):
    _set(monkeypatch, AI_MAX_CONCURRENT_PER_TEACHER=1,
         AI_GLOBAL_MAX_CONCURRENT=8)
    first = ai_spend.begin_attempt(
        db, provider="deepseek", model="deepseek-flash",
        prompt_chars=1000, user_id="teacher-1", request_id="a")
    with pytest.raises(ai_spend.AISpendConcurrencyExceeded):
        ai_spend.begin_attempt(
            db, provider="deepseek", model="deepseek-flash",
            prompt_chars=1000, user_id="teacher-1", request_id="b")
    # A different teacher still has a slot.
    other = ai_spend.begin_attempt(
        db, provider="deepseek", model="deepseek-flash",
        prompt_chars=1000, user_id="teacher-2", request_id="c")
    first.finish("success", usage={"input_tokens": 10, "output_tokens": 5})
    other.finish("success", usage={"input_tokens": 10, "output_tokens": 5})
    again = ai_spend.begin_attempt(
        db, provider="deepseek", model="deepseek-flash",
        prompt_chars=1000, user_id="teacher-1", request_id="d")
    again.finish("success", usage={"input_tokens": 10, "output_tokens": 5})


def test_oversized_input_is_rejected_before_provider(db, monkeypatch):
    _set(monkeypatch, AI_MAX_INPUT_CHARS=1000)
    provider = UsageProvider()
    big_context = _context()
    big_context["huge"] = "x" * 5000
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_content(
            provider=provider, context=big_context, db=db)
    assert exc.value.status_code == 413
    assert provider.calls == 0
    assert db.query(AIProviderUsageDB).count() == 0


def test_owner_summary_is_secret_free(db):
    provider = UsageProvider()
    zg.generate_zeli_content(
        provider=provider, context=_context(), db=db)
    status = ai_spend.budget_status(db)
    usage = ai_spend.usage_summary(db)
    rendered = json.dumps({"budget": status, "usage": usage})
    assert "api_key" not in rendered.lower()
    assert "sk-" not in rendered
    assert usage["providers"]["deepseek"]["attempts"] == 1
    assert usage["total_cost_usd"] > 0
    assert status["monthly"]["budget_usd"] == 10.0


def test_owner_endpoint_returns_budget_and_usage(db):
    from src.routers.platform_admin import ai_spend_summary
    admin = make_user(db, role="platform_admin", is_admin=True)
    body = asyncio.run(ai_spend_summary(user=admin, db=db))
    assert body["budget"]["enabled"] is True
    assert "providers" in body["usage"]

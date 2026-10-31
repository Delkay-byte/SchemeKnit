"""DeepSeek migration contracts for the Zeli generation method.

Covers the operational configuration surface, the exact request body sent to
the provider, timeout/retry enforcement by the HTTP client, usage capture and
the pre-quota rejection path. No network call is made: ``requests.post`` is
always mocked.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Settings  # noqa: E402
from src.engines import zeli_generation as zg  # noqa: E402
from src.engines.ai_provider import (  # noqa: E402
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekProvider,
    get_provider,
)

_ALL_ENV = (
    "ZELI_ENABLED", "ZELI_PROVIDER", "ZELI_MODEL", "ZELI_BASE_URL",
    "ZELI_API_KEY", "ZELI_TEMPERATURE", "ZELI_MAX_TOKENS",
    "ZELI_THINKING_MODE", "ZELI_CONNECT_TIMEOUT_SECONDS",
    "ZELI_READ_TIMEOUT_SECONDS", "ZELI_MAX_RETRIES",
    "DEEPSEEK_API_KEY", "GROQ_API_KEY", "GROQ_MODEL", "GROQ_BASE_URL",
)


@pytest.fixture
def clean_env(monkeypatch):
    for key in _ALL_ENV:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def _fake_settings(**overrides):
    base = dict(
        ZELI_ENABLED=True, ZELI_PROVIDER="deepseek", ZELI_MODEL="",
        ZELI_BASE_URL="", ZELI_API_KEY="", DEEPSEEK_API_KEY="test-deepseek-key",
        ZELI_FALLBACK_PROVIDER="",
        GROQ_API_KEY="gsk_test_key", GROQ_MODEL="openai/gpt-oss-120b",
        GROQ_BASE_URL="https://api.groq.com/openai/v1",
        ZELI_TEMPERATURE=0.3, ZELI_MAX_TOKENS=2000,
        ZELI_THINKING_MODE="disabled",
        ZELI_CONNECT_TIMEOUT_SECONDS=10.0, ZELI_READ_TIMEOUT_SECONDS=90.0,
        ZELI_MAX_RETRIES=2,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _ok(content='{"learning_objectives": ["x"]}', usage=True):
    payload = {
        "choices": [{"message": {"content": content}}],
    }
    if usage:
        payload["usage"] = {
            "prompt_tokens": 120,
            "completion_tokens": 80,
            "total_tokens": 200,
            "prompt_cache_hit_tokens": 64,
            "prompt_cache_miss_tokens": 56,
        }
    return _Resp(200, payload)


# â”€â”€ 1. Settings: defaults and validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_defaults_are_deepseek(clean_env):
    s = _settings()
    assert s.ZELI_PROVIDER == "deepseek"
    assert s.ZELI_FALLBACK_PROVIDER == "groq"
    assert s.ZELI_MODEL == ""
    assert s.ZELI_BASE_URL == ""
    assert s.ZELI_TEMPERATURE == 0.3
    assert s.ZELI_MAX_TOKENS == 2000
    assert s.ZELI_THINKING_MODE == "disabled"
    assert s.ZELI_CONNECT_TIMEOUT_SECONDS == 10.0
    assert s.ZELI_READ_TIMEOUT_SECONDS == 90.0
    assert s.ZELI_MAX_RETRIES == 2
    assert s.DEEPSEEK_API_KEY == ""


@pytest.mark.parametrize("field,value", [
    ("ZELI_PROVIDER", "not-a-provider"),
    ("ZELI_TEMPERATURE", -0.1),
    ("ZELI_TEMPERATURE", 2.1),
    ("ZELI_MAX_TOKENS", 0),
    ("ZELI_MAX_TOKENS", 8193),
    ("ZELI_THINKING_MODE", "sometimes"),
    ("ZELI_CONNECT_TIMEOUT_SECONDS", 0),
    ("ZELI_CONNECT_TIMEOUT_SECONDS", 61),
    ("ZELI_READ_TIMEOUT_SECONDS", 0),
    ("ZELI_READ_TIMEOUT_SECONDS", 601),
    ("ZELI_MAX_RETRIES", -1),
    ("ZELI_MAX_RETRIES", 6),
])
def test_invalid_configuration_is_rejected(clean_env, field, value):
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_text_overrides_are_trimmed(clean_env):
    s = _settings(ZELI_MODEL="  deepseek-flash  ",
                  ZELI_BASE_URL="  https://api.deepseek.com  ",
                  ZELI_API_KEY="  test-key  ")
    assert s.ZELI_MODEL == "deepseek-flash"
    assert s.ZELI_BASE_URL == "https://api.deepseek.com"
    assert s.ZELI_API_KEY == "test-key"


# â”€â”€ 2. Resolution precedence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_deepseek_defaults_and_key_fallback():
    cfg = zg._zeli_config(_fake_settings(ZELI_API_KEY="", DEEPSEEK_API_KEY="test-ds-key"))
    assert cfg.provider == "deepseek"
    assert cfg.model == DEFAULT_DEEPSEEK_MODEL
    assert cfg.base_url == DEFAULT_DEEPSEEK_BASE_URL
    assert cfg.api_key == "test-ds-key"
    assert cfg.max_tokens == 2000
    assert cfg.temperature == 0.3
    assert cfg.thinking_mode == "disabled"


def test_zeli_api_key_takes_precedence():
    cfg = zg._zeli_config(_fake_settings(
        ZELI_API_KEY="test-zeli-key", DEEPSEEK_API_KEY="test-ds-key"))
    assert cfg.api_key == "test-zeli-key"


def test_groq_selection_never_uses_deepseek_key():
    cfg = zg._zeli_config(_fake_settings(
        ZELI_PROVIDER="groq", ZELI_API_KEY="",
        DEEPSEEK_API_KEY="test-ds-key", GROQ_API_KEY="gsk-groq"))
    assert cfg.provider == "groq"
    assert cfg.api_key == "gsk-groq"
    assert cfg.model == "openai/gpt-oss-120b"
    assert cfg.base_url == "https://api.groq.com/openai/v1"


def test_fallback_groq_uses_its_own_model_and_key():
    cfg = zg._zeli_config(_fake_settings(
        ZELI_FALLBACK_PROVIDER="groq",
        DEEPSEEK_API_KEY="test-ds-key", GROQ_API_KEY="gsk-groq"))
    assert cfg.provider == "deepseek"
    assert cfg.api_key == "test-ds-key"
    assert cfg.fallback_provider == "groq"
    assert cfg.fallback_model == "openai/gpt-oss-120b"
    assert cfg.fallback_base_url == "https://api.groq.com/openai/v1"
    assert cfg.fallback_api_key == "gsk-groq"
    assert cfg.fallback_api_key != cfg.api_key


def test_fallback_can_be_disabled():
    cfg = zg._zeli_config(_fake_settings(ZELI_FALLBACK_PROVIDER=""))
    assert cfg.fallback_provider == ""
    assert zg.get_zeli_fallback_provider(_fake_settings(
        ZELI_FALLBACK_PROVIDER="")) is None


def test_fallback_cannot_be_the_same_as_primary():
    cfg = zg._zeli_config(_fake_settings(ZELI_FALLBACK_PROVIDER="deepseek"))
    assert cfg.fallback_provider == ""


@pytest.mark.parametrize("value", ["not-a-provider", "openai-ish", "groq-gateway"])
def test_invalid_fallback_provider_is_rejected(clean_env, value):
    with pytest.raises(ValidationError):
        _settings(ZELI_FALLBACK_PROVIDER=value)


def test_tuning_is_wired_onto_the_provider():
    provider = zg.get_zeli_provider(_fake_settings(
        ZELI_TEMPERATURE=0.9, ZELI_MAX_TOKENS=1234,
        ZELI_THINKING_MODE="enabled",
        ZELI_CONNECT_TIMEOUT_SECONDS=4.0, ZELI_READ_TIMEOUT_SECONDS=45.0,
        ZELI_MAX_RETRIES=4,
    ))
    assert isinstance(provider, DeepSeekProvider)
    assert provider.get_name() == "deepseek"
    assert provider.model == DEFAULT_DEEPSEEK_MODEL
    assert provider.temperature == 0.9
    assert provider.max_tokens == 1234
    assert provider.thinking_mode == "enabled"
    assert provider.connect_timeout == 4.0
    assert provider.read_timeout == 45.0
    assert provider.max_retries == 4


def test_factory_returns_deepseek():
    assert isinstance(get_provider("deepseek", api_key="test-key"), DeepSeekProvider)


# â”€â”€ 3. Request body: thinking / temperature / max_tokens â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_body_maps_max_tokens_and_sends_thinking():
    p = DeepSeekProvider(api_key="test-key", model="deepseek-flash",
                         temperature=0.3, max_tokens=2000,
                         thinking_mode="disabled")
    body = p.build_request_body("prompt", json_mode=True, system="sys")
    assert body["max_tokens"] == 2000
    assert "max_completion_tokens" not in body
    assert body["thinking"] == {"type": "disabled"}
    assert body["temperature"] == 0.3
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0] == {"role": "system", "content": "sys"}


def test_temperature_omitted_when_thinking_enabled():
    p = DeepSeekProvider(api_key="test-key", model="deepseek-flash",
                         temperature=0.7, thinking_mode="enabled")
    body = p.build_request_body("prompt")
    assert "temperature" not in body
    assert body["thinking"] == {"type": "enabled"}


def test_temperature_omitted_for_reasoner_model():
    p = DeepSeekProvider(api_key="test-key", model="deepseek-reasoner",
                         temperature=0.7, thinking_mode="disabled")
    body = p.build_request_body("prompt")
    assert "temperature" not in body


def test_auto_thinking_mode_omits_the_parameter():
    p = DeepSeekProvider(api_key="test-key", thinking_mode="auto")
    body = p.build_request_body("prompt")
    assert "thinking" not in body
    assert body["temperature"] == 0.3


def test_schema_is_not_sent_as_strict_json_schema():
    p = DeepSeekProvider(api_key="test-key")
    body = p.build_request_body("prompt", schema={"type": "object"})
    assert body["response_format"] == {"type": "json_object"}
    assert "json_schema" not in json.dumps(body)


# â”€â”€ 4. Transport: timeouts, retries, usage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_connect_and_read_timeouts_are_enforced(monkeypatch):
    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["timeout"] = kwargs.get("timeout")
        seen["headers"] = kwargs.get("headers")
        return _ok()

    monkeypatch.setattr("requests.post", fake_post)
    p = DeepSeekProvider(api_key="test-key", connect_timeout=2.5, read_timeout=7.5)
    assert p._chat("prompt") != ""
    assert seen["timeout"] == (2.5, 7.5)
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["Authorization"].startswith("Bearer ")


def test_transient_rate_limit_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_post(url, **kwargs):
        calls["n"] += 1
        return _Resp(429) if calls["n"] == 1 else _ok()

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("random.uniform", lambda a, b: 0)

    p = DeepSeekProvider(api_key="test-key", max_retries=2)
    assert p._chat("prompt") != ""
    assert calls["n"] == 2
    assert p.last_error is None
    assert sleeps and sleeps[0] >= 1.0


def test_auth_failure_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        return _Resp(401, {"error": {"message": "bad key"}})

    monkeypatch.setattr("requests.post", fake_post)
    p = DeepSeekProvider(api_key="test-key", max_retries=3)
    assert p._chat("prompt") == ""
    assert calls["n"] == 1
    assert p.last_error == "auth_failed"


def test_timeout_is_retried_up_to_the_bound(monkeypatch):
    calls = {"n": 0}

    class _Timeout(Exception):
        pass

    _Timeout.__name__ = "Timeout"

    def fake_post(url, **kwargs):
        calls["n"] += 1
        raise _Timeout("read timed out")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("random.uniform", lambda a, b: 0)
    p = DeepSeekProvider(api_key="test-key", max_retries=2)
    assert p._chat("prompt") == ""
    assert calls["n"] == 3
    assert p.last_error == "timeout"


def test_unsupported_json_mode_is_dropped_once(monkeypatch):
    bodies = []

    def fake_post(url, **kwargs):
        bodies.append(dict(kwargs.get("json") or {}))
        if len(bodies) == 1:
            return _Resp(400, {"error": {"message": "response_format unsupported"}})
        return _ok()

    monkeypatch.setattr("requests.post", fake_post)
    p = DeepSeekProvider(api_key="test-key", max_retries=2)
    assert p._chat("prompt", json_mode=True) != ""
    assert len(bodies) == 2
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]


def test_usage_metadata_includes_cached_tokens(monkeypatch):
    monkeypatch.setattr("requests.post", lambda url, **kw: _ok())
    p = DeepSeekProvider(api_key="test-key")
    p._chat("prompt")
    assert p.last_usage == {
        "provider": "deepseek",
        "model": "deepseek-flash",
        "input_tokens": 120,
        "output_tokens": 80,
        "total_tokens": 200,
        "cached_input_tokens": 64,
        "uncached_input_tokens": 56,
        "duration_seconds": p.last_usage["duration_seconds"],
    }
    assert p.last_usage["duration_seconds"] >= 0


def test_usage_absent_is_safe(monkeypatch):
    monkeypatch.setattr("requests.post", lambda url, **kw: _ok(usage=False))
    p = DeepSeekProvider(api_key="test-key")
    assert p._chat("prompt") != ""
    assert p.last_usage is None


def test_provider_error_text_is_not_surfaced(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda url, **kw: _Resp(500, {"error": {"message": "internal stack"}}),
    )
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("random.uniform", lambda a, b: 0)
    p = DeepSeekProvider(api_key="test-key", max_retries=0)
    assert p._chat("prompt") == ""
    assert p.last_error == "http_500"
    assert "internal stack" not in (p.last_error or "")


def test_missing_key_makes_no_request(monkeypatch):
    called = {"n": 0}

    def fake_post(url, **kwargs):
        called["n"] += 1
        return _ok()

    monkeypatch.setattr("requests.post", fake_post)
    p = DeepSeekProvider(api_key="")
    assert p._chat("prompt") == ""
    assert p.last_error == "missing_api_key"
    assert called["n"] == 0


def test_insufficient_balance_is_classified_safely(monkeypatch):
    monkeypatch.setattr("requests.post", lambda url, **kw: _Resp(402, {}))
    p = DeepSeekProvider(api_key="test-key", max_retries=3)
    assert p._chat("prompt") == ""
    assert p.last_error == "insufficient_balance"
    err = zg.zeli_failure_from_provider(p.last_error)
    assert err.status_code == 503
    assert "quota" in err.message.lower()


# â”€â”€ 5. Availability â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_missing_deepseek_key_is_unavailable_and_secret_free():
    state = zg.zeli_availability(_fake_settings(
        ZELI_API_KEY="", DEEPSEEK_API_KEY=""))
    assert state["available"] is False
    assert state["configured"] is True
    assert state["state"] == "MISSING_KEY"
    assert "test-key" not in json.dumps(state)
    assert "deepseek" not in json.dumps(state).lower()


def test_configured_deepseek_is_available():
    state = zg.zeli_availability(_fake_settings())
    assert state["available"] is True
    assert state["state"] == "CONFIGURED"


def test_invalid_provider_is_reported_without_details():
    state = zg.zeli_availability(_fake_settings(ZELI_PROVIDER="not-a-provider"))
    assert state["available"] is False
    assert state["state"] == "INVALID_CONFIG"
    assert "not-a-provider" not in json.dumps(state)


# â”€â”€ 6. Pre-quota rejection on the real generate route â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_unconfigured_deepseek_is_rejected_before_any_quota_or_job(db, monkeypatch):
    from test_zeli_generation_method import (
        _app, _config, _entitle_ai, _seed_scheme, make_user,
    )
    from src.database import (
        EntitlementDB, GenerationJobDB, LessonPlanDB, AIGenerationPeriodDB,
    )
    from fastapi.testclient import TestClient

    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=1)
    monkeypatch.setattr(
        "src.engines.zeli_generation.get_settings",
        lambda: _fake_settings(ZELI_API_KEY="", DEEPSEEK_API_KEY=""),
    )
    db.commit()

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id, method="zeli").model_dump(mode="json"),
        )

    assert resp.status_code == 503
    assert "No lesson plans were saved" in resp.json()["detail"]
    assert db.query(GenerationJobDB).count() == 0
    assert db.query(LessonPlanDB).count() == 0
    ent = db.query(EntitlementDB).filter(EntitlementDB.user_id == user.id).one()
    assert (ent.ai_credits_used or 0) == 0
    assert db.query(AIGenerationPeriodDB).count() == 0


# â”€â”€ 7. .env.example is a placeholder-only contract â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_env_example_documents_every_zeli_variable_with_placeholders_only():
    text = (BACKEND / ".env.example").read_text(encoding="utf-8", errors="replace")
    required = (
        "ZELI_ENABLED=", "ZELI_PROVIDER=deepseek", "ZELI_MODEL=deepseek-flash",
        "ZELI_BASE_URL=https://api.deepseek.com", "ZELI_API_KEY=",
        "ZELI_TEMPERATURE=0.3", "ZELI_MAX_TOKENS=2000",
        "ZELI_THINKING_MODE=disabled", "ZELI_CONNECT_TIMEOUT_SECONDS=10",
        "ZELI_READ_TIMEOUT_SECONDS=90", "ZELI_MAX_RETRIES=2",
        "DEEPSEEK_API_KEY=",
    )
    for needle in required:
        assert needle in text, f"missing {needle}"
    # No secret-shaped values anywhere in the example.
    for line in text.splitlines():
        if line.startswith(("DEEPSEEK_API_KEY=", "ZELI_API_KEY=", "GROQ_API_KEY=")):
            assert line.strip() == line.split("=")[0] + "=", line
    for pattern in ("sk-", "gsk_", "AIza"):
        assert pattern not in text

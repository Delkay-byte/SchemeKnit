"""
AI provider tests for Gemini + Groq (Phase 8 / Phase 10).

Unit tests are deterministic (mocked HTTP). Live integration tests are
isolated, clearly marked, and skipped unless the matching API key is set.
API keys are NEVER printed, asserted against literals, or written to logs.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import config FIRST so load_dotenv() runs and populates os.environ
# before pytest evaluates @pytest.mark.skipif at collection time.
import src.config  # noqa: F401  isort:skip

from src.engines.ai_provider import (
    AIResponseParseError,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    GeminiProvider,
    GroqProvider,
    MockProvider,
    NAMED_PROVIDERS,
    _parse_json_response,
    _strip_fences,
    get_provider,
    resolve_provider_mode,
)


# ════════════════════════════════════════════════════════════════════════════
# FACTORY + RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

class TestProviderFactory:
    def test_named_providers_registered(self):
        assert isinstance(get_provider("gemini"), GeminiProvider)
        assert isinstance(get_provider("groq"), GroqProvider)

    def test_off_basic_enhanced_still_mock(self):
        assert isinstance(get_provider("OFF"), MockProvider)
        assert isinstance(get_provider("BASIC"), MockProvider)
        assert isinstance(get_provider("ENHANCED"), MockProvider)
        assert isinstance(get_provider("unknown"), MockProvider)

    def test_named_providers_set(self):
        assert "gemini" in NAMED_PROVIDERS
        assert "groq" in NAMED_PROVIDERS
        assert "ollama" in NAMED_PROVIDERS


class TestResolveProviderMode:
    def test_off_stays_off(self):
        assert resolve_provider_mode("OFF") == "OFF"
        assert resolve_provider_mode(None) == "OFF"

    def test_named_passthrough(self):
        assert resolve_provider_mode("gemini") == "gemini"
        assert resolve_provider_mode("groq") == "groq"

    def test_pinned_env_wins_when_ai_on(self):
        with patch.dict("os.environ", {"AI_MODE": "groq"}):
            # Ensure pydantic settings don't override via _env fallback for AI_MODE
            with patch("src.engines.ai_provider._env", return_value="groq"):
                assert resolve_provider_mode("BASIC") == "groq"

    def test_auto_selects_gemini_when_key_present(self):
        with patch("src.engines.ai_provider._env") as env:
            def fake_env(name, default=""):
                if name == "AI_MODE":
                    return ""
                if name == "GEMINI_API_KEY":
                    return "test-key-not-real"
                if name == "GROQ_API_KEY":
                    return ""
                if name == "OPENAI_API_KEY":
                    return ""
                if name == "OPENCODE_ZEN_API_KEY":
                    return ""
                return default
            env.side_effect = fake_env
            with patch.object(GeminiProvider, "is_available", return_value=True), \
                 patch.object(GroqProvider, "is_available", return_value=False), \
                 patch.object(GeminiProvider, "__init__", lambda self, **k: None):
                # Direct auto-order check via resolve with no pin
                mode = resolve_provider_mode("ENHANCED")
                # Gemini key was visible → gemini preferred
                assert mode == "gemini"

    def test_falls_back_to_basic_when_no_provider(self):
        unavailable = MagicMock()
        unavailable.is_available.return_value = False
        with patch("src.engines.ai_provider._env", return_value=""):
            with patch("src.engines.ai_provider.get_provider", return_value=unavailable):
                assert resolve_provider_mode("ENHANCED") == "ENHANCED"
                assert resolve_provider_mode("BASIC") == "BASIC"


# ════════════════════════════════════════════════════════════════════════════
# ENV-CONFIGURED MODELS (no hard-coded obsolete IDs)
# ════════════════════════════════════════════════════════════════════════════

class TestModelConfiguration:
    def test_gemini_default_model_is_flash_not_gemini_pro(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "k", "GEMINI_MODEL": ""}):
            with patch("src.engines.ai_provider._env") as env:
                def fake(name, default=""):
                    if name == "GEMINI_API_KEY":
                        return "k"
                    if name == "GEMINI_MODEL":
                        return default
                    return default
                env.side_effect = fake
                p = GeminiProvider()
                assert p.model == DEFAULT_GEMINI_MODEL
                assert p.model != "gemini-pro"
                assert "flash" in p.model

    def test_gemini_model_from_env(self):
        with patch("src.engines.ai_provider._env") as env:
            def fake(name, default=""):
                if name == "GEMINI_API_KEY":
                    return "k"
                if name == "GEMINI_MODEL":
                    return "gemini-2.0-flash"
                return default
            env.side_effect = fake
            assert GeminiProvider().model == "gemini-2.0-flash"

    def test_groq_default_model_from_env_contract(self):
        with patch("src.engines.ai_provider._env") as env:
            def fake(name, default=""):
                if name == "GROQ_API_KEY":
                    return "k"
                if name == "GROQ_MODEL":
                    return default
                return default
            env.side_effect = fake
            p = GroqProvider()
            assert p.model == DEFAULT_GROQ_MODEL
            assert p.is_available()

    def test_groq_unavailable_without_key(self):
        with patch("src.engines.ai_provider._env", return_value=""):
            assert not GroqProvider(api_key="", model="x").is_available()


# ════════════════════════════════════════════════════════════════════════════
# STRUCTURED JSON / MALFORMED / TIMEOUT / REFUSAL HANDLING
# ════════════════════════════════════════════════════════════════════════════

class TestStructuredOutputHandling:
    def test_parse_valid_json(self):
        assert _parse_json_response('{"a": 1}') == {"a": 1}

    def test_parse_fenced_json(self):
        assert _parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}

    def test_parse_malformed_raises_structure_error(self):
        import pytest
        with pytest.raises(AIResponseParseError):
            _parse_json_response("not json at all")
        with pytest.raises(AIResponseParseError):
            _parse_json_response('{"partial": ')
        with pytest.raises(AIResponseParseError):
            _parse_json_response("")
        with pytest.raises(AIResponseParseError):
            _parse_json_response("[]")  # parseable but not an object

    def test_non_object_json_raises_schema_invalid(self):
        import pytest
        with pytest.raises(AIResponseParseError) as exc_info:
            _parse_json_response("[1, 2, 3]")
        assert exc_info.value.args[0] == "schema_invalid"

    def test_parse_json_embedded_in_text(self):
        assert _parse_json_response('Here you go: {"ok": true} thanks') == {"ok": True}

    def test_strip_fences_unclosed(self):
        assert _strip_fences('```json\n{"a": 1}') == '{"a": 1}'


class TestGeminiFailurePaths:
    def _provider(self):
        with patch("src.engines.ai_provider._env") as env:
            def fake(name, default=""):
                if name == "GEMINI_API_KEY":
                    return "test-key"
                if name == "GEMINI_MODEL":
                    return default
                return default
            env.side_effect = fake
            return GeminiProvider(api_key="test-key", model=DEFAULT_GEMINI_MODEL)

    def test_timeout_records_diagnostic_not_exception(self):
        import requests
        p = self._provider()
        with patch("requests.post", side_effect=requests.exceptions.Timeout("timed out")):
            out = p.generate_structured("{}")
        assert out == {}
        assert p.last_error is not None
        assert "Timeout" in p.last_error or "timed" in p.last_error.lower()
        # Secret never appears in the diagnostic
        assert "test-key" not in (p.last_error or "")

    def test_rate_limit_diagnostic(self):
        p = self._provider()
        resp = MagicMock(status_code=429, text="rate limited")
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "rate_limit"

    def test_auth_key_rejected_diagnostic_not_format_unsupported(self):
        # 401 ACCESS_TOKEN_TYPE_UNSUPPORTED is Google's generic "credential
        # rejected" for the CURRENT AQ authorization-key format (which is the
        # supported format) — the diagnostic must not imply the format is
        # unsupported or that a legacy standard key should be minted.
        p = self._provider()
        resp = MagicMock(status_code=401)
        resp.text = ('{"error":{"code":401,"status":"UNAUTHENTICATED",'
                     '"details":[{"reason":"ACCESS_TOKEN_TYPE_UNSUPPORTED"}]}}')
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "auth_key_rejected"
        assert p.last_error != "auth_key_type_unsupported"
        # provider_status must still resolve it to a live auth failure.
        from src.engines.ai_provider import provider_status
        assert provider_status(p) == "LIVE_AUTH_FAILURE"

    def test_content_refusal_empty_candidates(self):
        p = self._provider()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "promptFeedback": {"blockReason": "SAFETY"},
            "candidates": [],
        }
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert "refused" in (p.last_error or "") or "empty" in (p.last_error or "")

    def test_malformed_json_body_yields_empty_dict_with_diagnostic(self):
        p = self._provider()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "not-json"}]}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_structured("prompt")
        assert out == {}
        # 16H: malformed output is a DISTINCT diagnostic from "valid empty".
        assert p.last_error == "malformed_json"

    def test_v2_schema_invalid_content_is_not_a_false_success(self):
        """A well-formed JSON object that lacks the V2 lesson shape must NOT be
        accepted as a successful lesson (16H/16J — never fabricate success)."""
        p = self._provider()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"note": "hello"}'}]}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_lesson_v2(
                subject="Science", class_level="Basic 9", strand="Energy",
                sub_strand="Forms", content_standard="Describe",
                indicator_code="B9.1.1.1", indicator_text="Identify energy forms",
            )
        assert out == {}
        assert p.last_error == "schema_invalid"

    def test_valid_structured_lesson_json(self):
        p = self._provider()
        payload = {
            "learning_objectives": ["Learners can identify energy forms"],
            "starter": {"activity": "Warm-up question"},
            "assessment": {"activity": "Label three forms"},
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_structured("prompt")
        assert out["learning_objectives"][0].startswith("Learners can")

    def test_auth_uses_header_not_query_string(self):
        """API key must be sent as a header — never in the URL (log safety)."""
        p = self._provider()
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers") or {}
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
            return resp

        with patch("requests.post", side_effect=fake_post):
            p.generate_structured("{}")
        assert "test-key" not in captured["url"]
        assert captured["headers"].get("x-goog-api-key") == "test-key"


class TestGroqFailurePaths:
    def _provider(self):
        return GroqProvider(api_key="gsk-test-key", model=DEFAULT_GROQ_MODEL)

    def test_timeout_records_diagnostic(self):
        import requests
        p = self._provider()
        with patch("requests.post", side_effect=requests.exceptions.Timeout("t")):
            assert p.generate_structured("{}") == {}
        assert p.last_error is not None
        assert "gsk-test-key" not in p.last_error

    def test_rate_limit(self):
        p = self._provider()
        resp = MagicMock(status_code=429, text="slow down")
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "rate_limit"

    def test_model_not_found(self):
        p = self._provider()
        resp = MagicMock(status_code=404, text="model not found")
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "model_not_found"

    def test_refusal_message(self):
        p = self._provider()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "choices": [{"message": {"content": "", "refusal": "I cannot"}}],
        }
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "content_refusal"

    def test_empty_choices(self):
        p = self._provider()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"choices": []}
        with patch("requests.post", return_value=resp):
            assert p.generate_structured("{}") == {}
        assert p.last_error == "empty_output"

    def test_valid_json_object_response(self):
        p = self._provider()
        body = {"learning_objectives": ["Learners can classify matter"]}
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(body)}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_structured("prompt")
        assert out["learning_objectives"][0].startswith("Learners can")

    def test_auth_uses_bearer_header(self):
        p = self._provider()
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers") or {}
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
            return resp

        with patch("requests.post", side_effect=fake_post):
            p.generate_structured("{}")
        assert "gsk-test-key" not in captured["url"]
        assert captured["headers"].get("Authorization", "").startswith("Bearer ")


class TestGenerateLessonV2Schema:
    """Both providers must return the same canonical lesson schema shape."""

    def _v2_kwargs(self):
        return dict(
            subject="Science", class_level="Basic 9", strand="Diversity of Matter",
            sub_strand="Separating mixtures",
            content_standard="Separate mixtures by filtration",
            indicator_code="B9.1.1.1.1", indicator_text="Separate mixtures by filtration",
        )

    def test_gemini_v2_returns_canonical_keys(self):
        p = GeminiProvider(api_key="k", model=DEFAULT_GEMINI_MODEL)
        payload = {
            "learning_objectives": ["Learners can separate mixtures by filtration"],
            "starter": {"activity": "Show sandy water"},
            "main_learning": {"phase1": {"name": "Demo", "activity": "Filter", "duration_minutes": 20}},
            "assessment": {"activity": "Learners filter a sample"},
            "plenary": {"activity": "Review steps"},
            "differentiation": {"support": "Prompt steps", "core": "Filter", "extension": "New mixture"},
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_lesson_v2(**self._v2_kwargs())
        for key in ("learning_objectives", "starter", "assessment", "plenary", "differentiation"):
            assert key in out

    def test_groq_v2_returns_canonical_keys(self):
        p = GroqProvider(api_key="k", model=DEFAULT_GROQ_MODEL)
        payload = {
            "learning_objectives": ["Learners can separate mixtures by filtration"],
            "starter": {"activity": "Show sandy water"},
            "main_learning": {"phase1": {"name": "Demo", "activity": "Filter", "duration_minutes": 20}},
            "assessment": {"activity": "Learners filter a sample"},
            "plenary": {"activity": "Review steps"},
            "differentiation": {"support": "x", "core": "y", "extension": "z"},
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload)}}],
        }
        with patch("requests.post", return_value=resp):
            out = p.generate_lesson_v2(**self._v2_kwargs())
        for key in ("learning_objectives", "starter", "assessment", "plenary", "differentiation"):
            assert key in out


class TestSecretHygiene:
    def test_no_api_key_literals_in_source(self):
        from pathlib import Path
        src = Path(__file__).parent.parent / "src" / "engines" / "ai_provider.py"
        text = src.read_text(encoding="utf-8")
        # Real-looking key patterns must never appear in source.
        assert "AQ." not in text
        assert "gsk_" not in text
        assert "sk-proj-" not in text

    def test_env_example_has_no_real_keys(self):
        from pathlib import Path
        example = Path(__file__).parent.parent / ".env.example"
        text = example.read_text(encoding="utf-8")
        assert "AQ." not in text
        assert "gsk_" not in text


# ════════════════════════════════════════════════════════════════════════════
# LIVE INTEGRATION (isolated — skipped unless key present)
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.live
class TestLiveGemini:
    @pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set — live Gemini test skipped",
    )
    def test_one_indicator_structured_generation(self):
        p = GeminiProvider()
        assert p.is_available()
        out = p.generate_lesson_v2(
            subject="Science", class_level="Basic 9",
            strand="Diversity of Matter", sub_strand="Separating mixtures",
            content_standard="Separate mixtures by filtration",
            indicator_code="B9.1.1.1.1",
            indicator_text="Separate mixtures by filtration and evaporation",
            duration_minutes=40,
        )
        if not out and p.last_error in ("auth_failed", "auth_key_rejected",
                                        "invalid_api_key", "missing_api_key"):
            pytest.skip(f"Gemini credentials rejected (last_error={p.last_error}) — update GEMINI_API_KEY")
        assert out, f"Gemini returned empty (last_error={p.last_error})"
        assert "learning_objectives" in out or "starter" in out or "assessment" in out


@pytest.mark.live
class TestLiveGroq:
    @pytest.mark.skipif(
        not os.environ.get("GROQ_API_KEY"),
        reason="GROQ_API_KEY not set — live Groq test skipped",
    )
    def test_one_indicator_structured_generation(self):
        p = GroqProvider()
        assert p.is_available()
        out = p.generate_lesson_v2(
            subject="Science", class_level="Basic 9",
            strand="Diversity of Matter", sub_strand="Separating mixtures",
            content_standard="Separate mixtures by filtration",
            indicator_code="B9.1.1.1.1",
            indicator_text="Separate mixtures by filtration and evaporation",
            duration_minutes=40,
        )
        if not out and p.last_error in ("auth_failed", "invalid_api_key",
                                        "missing_api_key", "model_not_found",
                                        "http_404"):
            pytest.skip(f"Groq blocked (last_error={p.last_error}) — verify GROQ_API_KEY/GROQ_MODEL")
        assert out, f"Groq returned empty (last_error={p.last_error})"
        assert "learning_objectives" in out or "starter" in out or "assessment" in out

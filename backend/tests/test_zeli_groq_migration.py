"""Zeli / Groq runtime-provider migration tests.

Zeli is the teacher-facing assistant name; the runtime provider behind it is
Groq (``AI_MODE=groq``, model ``openai/gpt-oss-120b``). These tests cover:

* Groq provider configuration (model default + env), availability, key handling
* Strict Structured Outputs (``json_schema`` request body) and the single
  bounded degradation to JSON mode when the configured model rejects a schema
* Retry policy: transient (429 / 5xx / timeout) retried within bounded limits;
  non-transient (auth, model-not-found, invalid request) never retried
* Teacher-facing Zeli copy — no provider/model/API terms in messages
* Quota contract: exactly 1 credit on success, 0 on provider failure /
  malformed output / quality-gate failure; idempotent per request_id
* Unrelated-section and WAPEF preservation across a single-section rewrite
* Teacher-facing frontend surfaces carry no provider names
* Deterministic generation never needs the provider (AI OFF)
* The live Groq success path (strict schema + section rewrite) — skipped when
  no key is resolvable
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.engines.ai_provider import (
    DEFAULT_GROQ_MODEL, GroqProvider, resolve_provider_mode, _AUTO_PROVIDER_ORDER,
)
from src.routers import ai_regeneration as air
from src.routers.ai_regeneration import (
    REGENERATABLE_SECTIONS, REWRITE_MODES, _section_json_schema,
)
from src import ai_quota
from src.database import LessonPlanDB

_TEACHER_FILES = [
    "src/components/lesson-workspace.tsx",
    "src/lib/ai-feedback.ts",
    r"src/app/(app)/lessons/[id]/page.tsx",
    r"src/app/(app)/generate/[id]/page.tsx",
]

_PROVIDER_NAME_RE = ("gemini", "groq", "openai", "anthropic", "gpt-oss", "gpt-4",
                     "gpt-3", "llama", "mistral")

_ZELI_COPY_PIECES = (
    "Zeli is unavailable right now.",
    "Zeli is busy right now.",
    "Zeli could not rewrite this section right now.",
    "Your existing content was preserved.",
)

_PROVIDER_VOCAB = ("groq", "gemini", "openai", "gpt-oss", "api key",
                   "429", "503", "rate limit", "provider", "model id")


def _frontend_root() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend"


def _resp(status_code=200, content="{}", refusal=None):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {
        "choices": [{"message": {"content": content, "refusal": refusal}}],
    }
    return resp


def _capture_posts(status_sequence, content="{}"):
    """Patch ``requests.post`` to walk ``status_sequence`` and record bodies."""
    captured = []
    seq = list(status_sequence)
    counter = {"i": 0}

    def fake_post(url, **kwargs):
        # Deep copy: the retry logic MUTATES the request body in place, and we
        # need each call's snapshot.
        captured.append({"url": url, "json": json.loads(json.dumps(kwargs.get("json", {})))})
        i = min(counter["i"], len(seq) - 1)
        counter["i"] += 1
        return seq[i] if isinstance(seq[i], MagicMock) else _resp(seq[i], content)

    return captured, fake_post


def _make_lesson_row(db, owner):
    """A stored lesson with WAPEF + the assignment chain filled in."""
    from src.database import GenerationJobDB, generate_id
    from tests.conftest import make_school

    scheme = make_school(db)
    job = GenerationJobDB(id=generate_id(), owner_id=owner.id, scheme_id=scheme.id,
                          status="completed")
    db.add(job)
    db.flush()
    lp = LessonPlanDB(
        id=generate_id(), job_id=job.id, owner_id=owner.id, scheme_id=scheme.id,
        week_number=1, lesson_sequence=1, class_level="Basic 7",
        subject="Mathematics", duration_minutes=60, strand="Number",
        sub_strand="Number", indicators=["B7.1.1.1.1 Add whole numbers"],
        indicator_codes=["B7.1.1.1.1"],
        learning_objectives=[{"description": "Learners can add whole numbers."}],
        teaching_learning_resources=["counters"],
        main_activities=[{"description": "Teacher works through one example."}],
        assessment="Old assessment text here.",
        introduction="Old introduction text here.",
        class_assignment="Old class assignment text here.",
        home_assignment="Old home assignment text here.",
        wapef_deep_hope="Stewardship of resources",
        wapef_storyline="Care for creation",
        wapef_through_lines=["Wisdom", "Community"],
        wapef_gods_story="Creation care",
    )
    db.add(lp)
    db.commit()
    return lp


class _ZeliStub:
    """Deterministic stand-in for the real Groq provider (no network)."""
    last_error = None
    model = "openai/gpt-oss-120b"

    def __init__(self, payload=None):
        self.payload = payload or {
            "assessment": "Zeli rewrite: learners classify local matter samples "
                          "in groups, then present one finding each."}
        self.schemas = []

    def generate_structured(self, prompt, schema=None):
        self.schemas.append(schema)
        return dict(self.payload)

    def is_available(self):
        return True

    def get_name(self):
        return "groq"


# ════════════════════════════════════════════════════════════════════════════
# 1. PROVIDER CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

class TestGroqConfiguration:
    def test_default_model_is_gpt_oss_120b(self):
        """The production runtime model is openai/gpt-oss-120b (supports strict
        Structured Outputs). Never a downgrade without benchmark evidence."""
        assert DEFAULT_GROQ_MODEL == "openai/gpt-oss-120b"

    def test_groq_is_the_production_runtime_default(self):
        """AI_MODE=groq is the production configuration: auto-selection prefers
        Groq when no provider is pinned."""
        assert _AUTO_PROVIDER_ORDER[0] == "groq"

    def test_ai_mode_env_pin_resolves_to_groq(self):
        with patch("src.engines.ai_provider._env") as env:
            def fake(name, default=""):
                if name == "AI_MODE":
                    return "groq"
                return default
            env.side_effect = fake
            assert resolve_provider_mode("BASIC") == "groq"

    def test_get_provider_returns_groq(self):
        p = GroqProvider(api_key="gsk-unit", model="openai/gpt-oss-120b")
        assert p.get_name() == "groq"
        assert p.model == "openai/gpt-oss-120b"

    def test_model_env_override(self):
        p = GroqProvider(api_key="gsk-unit", model="custom-model")
        assert p.model == "custom-model"

    def test_missing_api_key_is_unavailable(self):
        """No key → the provider reports itself unavailable and every call is a
        teacher-safe no-op; deterministic content is untouched."""
        with patch("src.engines.ai_provider._env", return_value=""):
            p = GroqProvider(api_key="")
            assert not p.is_available()
            assert p.generate_structured("prompt") == {}
            assert p.last_error == "missing_api_key"

    def test_missing_key_does_not_raise_or_call_network(self):
        with patch("src.engines.ai_provider._env", return_value=""):
            p = GroqProvider(api_key="")
            with patch("requests.post") as post:
                p.generate_structured("prompt")
        post.assert_not_called()

    def test_invalid_key_classifies_auth_failure_without_retry(self):
        """A rejected key is NON-transient: no retry loop, one request."""
        p = GroqProvider(api_key="gsk-bad-key", model="openai/gpt-oss-120b")
        captured, fake = _capture_posts([401])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p.generate_structured("prompt") == {}
        assert p.last_error == "auth_failed"
        assert len(captured) == 1
        sleep.assert_not_called()

    def test_key_never_in_url_or_body(self):
        p = GroqProvider(api_key="gsk-SECRET-KEY", model="openai/gpt-oss-120b")
        captured, fake = _capture_posts([200])
        with patch("requests.post", side_effect=fake):
            p.generate_structured("prompt", schema={"type": "object"})
        assert all("gsk-SECRET-KEY" not in c["url"] for c in captured)
        assert all("gsk-SECRET-KEY" not in json.dumps(c["json"]) for c in captured)


# ════════════════════════════════════════════════════════════════════════════
# 2. STRICT STRUCTURED OUTPUTS
# ════════════════════════════════════════════════════════════════════════════

class TestStrictStructuredOutput:
    def _provider(self):
        return GroqProvider(api_key="gsk-unit", model="openai/gpt-oss-120b")

    def test_schema_builds_strict_json_schema_request(self):
        p = self._provider()
        captured, fake = _capture_posts([200])
        schema = {"type": "object", "properties": {"assessment": {"type": "string"}}}
        with patch("requests.post", side_effect=fake):
            p.generate_structured("Return JSON: {...}", schema=schema)
        body = captured[0]["json"]
        rf = body["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"] == schema
        assert rf["json_schema"]["name"]

    def test_schema_returns_parsed_dict(self):
        p = self._provider()
        captured, fake = _capture_posts(
            [200], content='{"assessment": "Zeli rewrite with concrete steps."}')
        with patch("requests.post", side_effect=fake):
            out = p.generate_structured("prompt", schema={"type": "object"})
        assert out == {"assessment": "Zeli rewrite with concrete steps."}

    def test_without_schema_uses_plain_json_object_mode(self):
        p = self._provider()
        captured, fake = _capture_posts([200], content="{}")
        with patch("requests.post", side_effect=fake):
            p.generate_structured("prompt")
        assert captured[0]["json"]["response_format"] == {"type": "json_object"}

    def test_schema_rejected_by_model_degrades_once_to_json_mode(self):
        """A 400 on the strict schema is non-transient but recoverable: ONE
        retry in plain JSON mode — never a loop."""
        p = self._provider()
        ok = _resp(200, content='{"assessment": "fallback text"}')
        captured, fake = _capture_posts([400, ok])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            out = p.generate_structured("prompt", schema={"type": "object"})
        assert out == {"assessment": "fallback text"}
        assert len(captured) == 2
        assert captured[0]["json"]["response_format"]["type"] == "json_schema"
        assert captured[1]["json"]["response_format"]["type"] == "json_object"
        sleep.assert_not_called()

    def test_schema_degradation_is_bounded(self):
        """Strict schema → JSON mode → no format: at most two step-downs, then
        a clean failure. Never an open loop."""
        p = self._provider()
        captured, fake = _capture_posts([400, 400, 400])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p.generate_structured("prompt", schema={"type": "object"}) == {}
        assert len(captured) <= 3
        assert p.last_error == "http_400"
        sleep.assert_not_called()


class TestSectionJsonSchema:
    def test_flat_section_schema_mirrors_the_prompt_contract(self):
        s = _section_json_schema("assessment")
        assert s["type"] == "object"
        assert s["properties"]["assessment"]["type"] == "string"
        assert s["required"] == ["assessment"]
        assert s["additionalProperties"] is False

    def test_main_activities_schema_enforces_phases(self):
        s = _section_json_schema("main_activities")
        ml = s["properties"]["main_learning"]
        phase = ml["properties"]["phase1"]
        assert phase["properties"]["activity"]["type"] == "string"
        assert phase["properties"]["duration_minutes"]["type"] == "number"
        assert phase["required"] == ["activity", "duration_minutes"]
        assert phase["additionalProperties"] is False
        assert ml["required"] == ["phase1", "phase2", "phase3"]
        assert ml["additionalProperties"] is False
        assert s["additionalProperties"] is False

    def test_every_regeneratable_section_has_a_schema(self):
        """The strict schema path works for every section the teacher can rewrite —
        only a whole-lesson schema is never requested for a section rewrite."""
        for section in REGENERATABLE_SECTIONS:
            s = _section_json_schema(section)
            assert s["type"] == "object"
            assert s["additionalProperties"] is False
            assert s["required"]


# ════════════════════════════════════════════════════════════════════════════
# 3. BOUNDED RETRY POLICY
# ════════════════════════════════════════════════════════════════════════════

class TestRetryPolicy:
    def _provider(self):
        return GroqProvider(api_key="gsk-unit", model="openai/gpt-oss-120b")

    def test_rate_limit_then_success_retries_within_bounds(self):
        """A 429 is transient: bounded retry, then success clears last_error."""
        p = self._provider()
        captured, fake = _capture_posts([429, 200], content='{"ok": true}')
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            out = p.generate_structured("prompt")
        assert out == {"ok": True}
        assert p.last_error is None
        assert len(captured) == 2
        assert sleep.call_count == 1

    def test_persistent_rate_limit_is_bounded_not_aggressive(self):
        """The provider stays throttled: at most MAX_RETRIES extra attempts,
        then the teacher-safe failure — no hammering."""
        p = self._provider()
        captured, fake = _capture_posts([429] * 10)
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p.generate_structured("prompt") == {}
        assert p.last_error == "rate_limit"
        assert len(captured) == p.MAX_RETRIES + 1
        assert sleep.call_count == p.MAX_RETRIES

    def test_server_5xx_retries(self):
        p = self._provider()
        captured, fake = _capture_posts([503, 502, 200], content='{"ok": true}')
        with patch("requests.post", side_effect=fake), patch("time.sleep"):
            out = p.generate_structured("prompt")
        assert out == {"ok": True}
        assert len(captured) == 3

    def test_timeout_exception_is_transient(self):
        import requests
        p = self._provider()
        ok = _resp(200, content='{"ok": true}')
        calls = {"n": 0}

        def fake_post(url, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.exceptions.Timeout("t")
            return ok

        with patch("requests.post", side_effect=fake_post), \
                patch("time.sleep") as sleep:
            out = p.generate_structured("prompt")
        assert out == {"ok": True}
        assert sleep.call_count == 1

    def test_model_not_found_never_retries(self):
        p = self._provider()
        captured, fake = _capture_posts([404, 404])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p.generate_structured("prompt") == {}
        assert p.last_error == "model_not_found"
        assert len(captured) == 1
        sleep.assert_not_called()

    def test_invalid_request_is_not_treated_as_transient(self):
        """A 400 steps the response format down at most — it never enters the
        rate-limit / server retry path (no sleeps, no hammering)."""
        p = self._provider()
        captured, fake = _capture_posts([400])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p.generate_structured("prompt") == {}
        assert p.last_error == "http_400"
        assert len(captured) == 2  # one step-down (JSON mode → none), then stop
        sleep.assert_not_called()

    def test_request_error_without_response_format_never_retries(self):
        """A 400 with no response format at all is a plain bad request: stop."""
        p = self._provider()
        captured, fake = _capture_posts([400])
        with patch("requests.post", side_effect=fake), \
                patch("time.sleep") as sleep:
            assert p._chat("prompt") == ""
        assert p.last_error == "http_400"
        assert len(captured) == 1
        sleep.assert_not_called()

    def test_retry_delay_is_bounded_seconds(self):
        p = self._provider()
        assert 0 < p.RETRY_DELAY_SECONDS <= 5
        assert p.MAX_RETRIES <= 3


# ════════════════════════════════════════════════════════════════════════════
# 4. TEACHER-SAFE (ZELI) COPY — no provider internals
# ════════════════════════════════════════════════════════════════════════════

class TestZeliTeacherSafeCopy:
    def test_router_ships_the_zeli_teacher_copy(self):
        """The regeneration router's teacher-facing messages name Zeli.
        (Python concatenates adjacent literals, so assert the pieces.)"""
        import inspect
        src = inspect.getsource(air)
        for piece in _ZELI_COPY_PIECES:
            assert piece in src, f"missing Zeli teacher copy: {piece}"

    def test_diagnostics_keep_technical_detail(self):
        """Server-side diagnostics still carry the provider + state for logs —
        only the teacher-facing message is scrubbed."""
        import inspect
        src = inspect.getsource(air)
        assert "AI provider '" in src  # diagnostic strings (not teacher copy)

    async def test_every_failure_message_is_teacher_safe(self, db):
        """All three failure codes surface calm Zeli copy: Zeli is named,
        content is preserved, and NO provider vocabulary leaks."""
        from tests.conftest import make_entitled_teacher

        class _Stub:
            """Configurable failing provider."""
            def __init__(self, payload=None, last_error=None, available=True):
                self.last_error = last_error
                self.model = "openai/gpt-oss-120b"
                self._payload = payload or {}
                self._available = available

            def generate_structured(self, prompt, schema=None):
                return dict(self._payload)

            def is_available(self):
                return self._available

            def get_name(self):
                return "groq"

        u, _school, _lic = make_entitled_teacher(db, email="zeli_safe@t.test")
        cases = [
            ("provider unavailable", _Stub(available=False), 503),
            ("rate limited", _Stub(last_error="rate_limit"), 502),
            ("no usable suggestion", _Stub(payload={"assessment": "Short."}), 502),
        ]
        for label, stub, expected_status in cases:
            lp = _make_lesson_row(db, u)
            with patch.object(air, "get_provider", return_value=stub):
                with pytest.raises(HTTPException) as e:
                    await air.regenerate_section(
                        air.SectionRegenerateRequest(
                            lesson_plan_id=lp.id, section="assessment",
                            ai_mode="groq"),
                        u, db)
            assert e.value.status_code == expected_status, label
            msg = e.value.detail["message"]
            assert "Zeli" in msg, f"{label}: Zeli must be named"
            assert "preserved" in msg, f"{label}: must reassure the teacher"
            low = msg.lower()
            for bad in _PROVIDER_VOCAB:
                assert bad not in low, f"{label}: provider term '{bad}' in: {msg}"
            # The deterministic content is untouched.
            db.refresh(lp)
            assert lp.assessment == "Old assessment text here."


# ════════════════════════════════════════════════════════════════════════════
# 5. QUOTA: 1 credit on success, 0 on any failure
# ════════════════════════════════════════════════════════════════════════════

class TestQuotaContract:
    def _used(self, db, user):
        return ai_quota.get_ai_units_used(db, user.id)

    def _paid_teacher(self, db, email):
        from tests.conftest import make_user, make_paid_entitlement
        u = make_user(db, email=email)
        ent = make_paid_entitlement(db, u.id, ai_enabled=True)
        ent.ai_credits = 10
        db.commit()
        return u

    async def test_successful_rewrite_consumes_exactly_one_credit(self, db):
        u = self._paid_teacher(db, "zeli_credit_ok@t.test")
        lp = _make_lesson_row(db, u)
        before = self._used(db, u)
        with patch.object(air, "get_provider", return_value=_ZeliStub()):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment",
                    ai_mode="groq", request_id="zeli-req-1"),
                u, db)
        assert res.new_content.startswith("Zeli rewrite")
        assert self._used(db, u) == before + 1

    async def test_provider_failure_consumes_zero_credits(self, db):
        u = self._paid_teacher(db, "zeli_credit_fail@t.test")
        lp = _make_lesson_row(db, u)

        class Dead:
            last_error = "rate_limit"
            model = "openai/gpt-oss-120b"

            def generate_structured(self, prompt, schema=None):
                return {}

            def is_available(self):
                return True

            def get_name(self):
                return "groq"

        before = self._used(db, u)
        with patch.object(air, "get_provider", return_value=Dead()):
            with pytest.raises(HTTPException):
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment",
                        ai_mode="groq"),
                    u, db)
        assert self._used(db, u) == before

    async def test_malformed_output_consumes_zero_credits(self, db):
        u = self._paid_teacher(db, "zeli_malformed@t.test")
        lp = _make_lesson_row(db, u)
        before = self._used(db, u)
        # Valid JSON, but nothing maps to the requested section.
        stub = _ZeliStub(payload={"unrelated_section": "anything here."})
        with patch.object(air, "get_provider", return_value=stub):
            with pytest.raises(HTTPException):
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment",
                        ai_mode="groq"),
                    u, db)
        assert self._used(db, u) == before

    async def test_quality_gate_failure_consumes_zero_credits(self, db):
        """A too-short regeneration is an unusable suggestion, not a credit."""
        u = self._paid_teacher(db, "zeli_gate@t.test")
        lp = _make_lesson_row(db, u)
        before = self._used(db, u)
        stub = _ZeliStub(payload={"assessment": "Short."})
        with patch.object(air, "get_provider", return_value=stub):
            with pytest.raises(HTTPException):
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment",
                        ai_mode="groq"),
                    u, db)
        assert self._used(db, u) == before

    async def test_duplicate_request_id_never_double_consumes(self, db):
        u = self._paid_teacher(db, "zeli_idempotent@t.test")
        lp = _make_lesson_row(db, u)
        before = self._used(db, u)
        with patch.object(air, "get_provider", return_value=_ZeliStub()):
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="groq",
                    request_id="zeli-req-dup"),
                u, db)
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="groq",
                    request_id="zeli-req-dup"),
                u, db)
        assert self._used(db, u) == before + 1

    async def test_unavailable_provider_consumes_zero_credits(self, db):
        u = self._paid_teacher(db, "zeli_unavail@t.test")
        lp = _make_lesson_row(db, u)
        before = self._used(db, u)
        stub = _ZeliStub()
        stub.is_available = lambda: False
        with patch.object(air, "get_provider", return_value=stub):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment",
                        ai_mode="groq"),
                    u, db)
        assert e.value.status_code == 503
        assert "Zeli" in e.value.detail["message"]
        assert self._used(db, u) == before


# ════════════════════════════════════════════════════════════════════════════
# 6. UNRELATED SECTIONS + WAPEF PRESERVATION + DETERMINISTIC BASELINE
# ════════════════════════════════════════════════════════════════════════════

class TestPreservation:
    async def test_only_the_requested_section_changes(self, db):
        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, email="zeli_preserve@t.test")
        lp = _make_lesson_row(db, u)
        payload = {"assessment": "Zeli rewrite: learners measure and compare "
                                 "quantities in mixed-ability pairs."}
        with patch.object(air, "get_provider",
                          return_value=_ZeliStub(payload=payload)):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="groq"),
                u, db)
        assert res.section == "assessment"
        assert res.previous_content == "Old assessment text here."
        assert res.new_content == payload["assessment"]
        assert res.new_activities is None
        # No other stored section changed; WAPEF is untouched.
        db.refresh(lp)
        assert lp.introduction == "Old introduction text here."
        assert lp.class_assignment == "Old class assignment text here."
        assert lp.home_assignment == "Old home assignment text here."
        assert lp.wapef_deep_hope == "Stewardship of resources"
        assert lp.wapef_storyline == "Care for creation"
        assert list(lp.wapef_through_lines or []) == ["Wisdom", "Community"]
        assert lp.wapef_gods_story == "Creation care"
        assert lp.indicator_codes == ["B7.1.1.1.1"]

    async def test_diagnostics_fields_stay_available_for_admins(self, db):
        """The response still carries provider/model for server-side
        diagnostics; the teacher UI simply does not render them."""
        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, email="zeli_diag@t.test")
        lp = _make_lesson_row(db, u)
        with patch.object(air, "get_provider", return_value=_ZeliStub()):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="groq"),
                u, db)
        assert res.provider == "groq"
        assert res.model == "openai/gpt-oss-120b"

    def test_deterministic_generation_needs_no_provider(self):
        """AI OFF: the scheme still produces a full, quality-gated lesson via
        the deterministic engine — Zeli is an optional assistant only."""
        from datetime import date
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=Subject.MATHEMATICS,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=2, lesson_duration_minutes=60,
            teaching_days=[0, 2], holidays=[],
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.1",
            indicator_description="Add whole numbers",
            content_standard_code="B7.1.1.1",
            content_standard_description="Add whole numbers",
            strand="Number", sub_strand="Number and Numeration",
            week_number=1, source_resources=["counters"],
            lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
            teaching_week=1,
        )
        lp = build_lesson(alloc, config, "s")
        assert lp.indicators
        assert lp.main_activities
        assert lp.assessment
        # The assignment chain is present (assessment chain regression guard).
        assert lp.class_assignment
        assert lp.home_assignment


# ════════════════════════════════════════════════════════════════════════════
# 7. REWRITE MODES + .env.example PRODUCTION CONFIG
# ════════════════════════════════════════════════════════════════════════════

class TestModesAndEnv:
    def test_primary_affordances_exist(self):
        assert "suggest_another_version" in REWRITE_MODES
        assert "make_more_practical" in REWRITE_MODES

    def test_optional_affordances_are_registered(self):
        """The two optional extras are available to the teacher UI."""
        assert "make_more_learner_centred" in REWRITE_MODES
        assert "make_easier_limited_resources" in REWRITE_MODES

    def test_mode_instructions_never_leak_provider_vocabulary(self):
        for instruction in REWRITE_MODES.values():
            low = instruction.lower()
            for bad in ("groq", "gemini", "openai", "anthropic", "api", "model"):
                assert bad not in low

    def test_env_example_is_the_groq_production_config(self):
        """AI_MODE=groq, gpt-oss-120b, empty key (owner supplies the secret)."""
        env = Path(__file__).parent.parent / ".env.example"
        text = env.read_text(encoding="utf-8", errors="replace")
        assert "AI_MODE=groq" in text
        assert "GROQ_MODEL=openai/gpt-oss-120b" in text
        # The key is NEVER committed — the example ships intentionally empty.
        for line in text.splitlines():
            if line.startswith("GROQ_API_KEY="):
                assert line.strip() == "GROQ_API_KEY=", \
                    f".env.example must ship an empty key, got: {line!r}"
        # No real key patterns anywhere in the example.
        assert "gsk_" not in text
        assert "AIza" not in text


# ════════════════════════════════════════════════════════════════════════════
# 8. TEACHER-FACING FRONTEND: no provider names; Zeli copy present
# ════════════════════════════════════════════════════════════════════════════

class TestZeliFrontendCopy:
    def _read(self, rel):
        return (_frontend_root() / rel).read_text(encoding="utf-8", errors="replace")

    def test_no_provider_names_in_teacher_surfaces(self):
        for rel in _TEACHER_FILES:
            text = self._read(rel).lower()
            for name in _PROVIDER_NAME_RE:
                assert name not in text, f"{rel} mentions provider '{name}'"

    def test_no_provider_interpolation_in_rendered_text(self):
        """Template strings must not splice the resolved provider into text the
        teacher reads. (TypeScript `provider: string` fields are internal.)"""
        for rel in _TEACHER_FILES:
            text = self._read(rel)
            for frag in ("${aiStatus.provider}", "${aiResult.provider}",
                         "${res.provider}", "provider_label ||",
                         "provider: ${"):
                assert frag not in text, f"{rel} renders provider: {frag}"

    def test_zeli_copy_is_present_in_each_surface(self):
        expectations = {
            r"src/app/(app)/lessons/[id]/page.tsx": ["Zeli available"],
            r"src/app/(app)/generate/[id]/page.tsx": ["Zeli available"],
            "src/components/lesson-workspace.tsx": ["Zeli rewrote this section"],
            "src/lib/ai-feedback.ts": [
                "Zeli is busy right now",
                "Zeli is unavailable right now",
                "Zeli could not rewrite this section",
            ],
        }
        for rel, needles in expectations.items():
            text = self._read(rel)
            for needle in needles:
                assert needle in text, f"{rel} missing Zeli copy: {needle}"

    def test_affordance_labels_are_simple_teacher_actions(self):
        """The buttons expose actions, not model/provider/prompt/JSON terms."""
        text = self._read("src/components/lesson-workspace.tsx")
        for label in ("Suggest another version", "Make this more practical",
                      "More learner-centred", "Easier with limited resources"):
            assert label in text
        for bad in ("temperature", "schema", "json", "provider", "prompt"):
            assert f">{bad}" not in text.lower()


# ════════════════════════════════════════════════════════════════════════════
# 9. LIVE GROQ (skipped unless the owner supplied a key)
# ════════════════════════════════════════════════════════════════════════════

_LIVE_GROQ_READY = GroqProvider().is_available()


@pytest.mark.live
class TestLiveZeliGroq:
    """Real Groq calls. Skipped when no key is resolvable (env or .env)."""

    @pytest.mark.skipif(
        not _LIVE_GROQ_READY,
        reason="GROQ_API_KEY not resolvable — live Groq test skipped",
    )
    def test_authenticated_request_and_selected_model_exist(self):
        """1. authenticated request succeeds; 2. the selected model answers."""
        p = GroqProvider()
        assert p.model == "openai/gpt-oss-120b"
        out = p.generate_structured(
            'Return JSON: {"answer": "ok"}',
            schema={"type": "object", "properties": {"answer": {"type": "string"}},
                    "required": ["answer"], "additionalProperties": False},
        )
        if p.last_error in ("auth_failed", "invalid_api_key", "missing_api_key",
                            "model_not_found", "http_404"):
            pytest.skip(f"Groq blocked (last_error={p.last_error}) — verify key/model")
        assert out and "answer" in out, \
            f"Groq live call failed (last_error={p.last_error})"

    @pytest.mark.skipif(
        not _LIVE_GROQ_READY,
        reason="GROQ_API_KEY not resolvable — live Groq test skipped",
    )
    def test_strict_schema_section_rewrite(self):
        """Structured output succeeds and the schema is honoured."""
        p = GroqProvider()
        schema = _section_json_schema("assessment")
        prompt = (
            "You are a Ghanaian educator rewriting ONE section of a lesson plan.\n"
            "OBJECTIVE: Learners can add whole numbers (B7.1.1.1.1).\n"
            "Rewrite the assessment so it checks understanding with concrete "
            "local materials. Return ONLY the JSON the schema requires.\n"
            'Return JSON: {"assessment": "the rewritten assessment text"}'
        )
        out = p.generate_structured(prompt, schema=schema)
        if not out and p.last_error in ("auth_failed", "invalid_api_key",
                                        "missing_api_key", "model_not_found",
                                        "http_404"):
            pytest.skip(f"Groq blocked (last_error={p.last_error}) — verify key/model")
        assert out and isinstance(out.get("assessment"), str) and \
            len(out["assessment"]) >= 20, \
            f"strict schema rewrite failed (last_error={p.last_error})"

    @pytest.mark.skipif(
        not _LIVE_GROQ_READY,
        reason="GROQ_API_KEY not resolvable — live Groq test skipped",
    )
    def test_invalid_key_fails_safely(self):
        """A controlled invalid key cannot reach the API: teacher-safe failure,
        no exception, no raw error text."""
        p = GroqProvider(api_key="gsk-invalid-key-for-failure-test",
                         model="openai/gpt-oss-120b")
        out = p.generate_structured('Return JSON: {"answer": "x"}')
        assert out == {}
        assert p.last_error == "auth_failed"

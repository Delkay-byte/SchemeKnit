"""DeepSeek primary / Groq fallback contracts for Zeli whole-lesson generation.

The fallback is bounded to ONE eligible provider failure. These tests cover
transport, HTTP, malformed-output and auth paths, plus provenance, cache and
credit behaviour. No live provider is called here; live verification is a
separate staging step.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.database import (  # noqa: E402
    AIUsageEventDB, EntitlementDB, GenerationJobDB, LessonPlanDB, SchemeDB,
    UsagePeriodDB, UsageUnitDB, WeekDB, generate_id,
)
from src.engines import zeli_generation as zg  # noqa: E402
from src.engines.generation_pipeline import GenerationPipeline  # noqa: E402
from src.models import AIMode, TermConfig  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _science_lesson():
    return {
        "learning_objectives": [
            "Learners can identify by name at least five binary chemical compounds from their chemical formulae.",
            "Learners can discuss one use of each named binary chemical compound.",
            "Learners can name one further binary compound not discussed in class.",
        ],
        "prior_knowledge": (
            "Learners know that matter is made of elements and that elements "
            "combine to form compounds. They have seen water, table salt and "
            "carbon dioxide in everyday life."),
        "key_vocabulary": [
            "binary compound", "chemical formula", "element", "compound",
            "water", "sodium chloride", "carbon dioxide"],
        "resources": {
            "source_resources": ["Chart"],
            "suggested_alternatives": ["Chalkboard", "Samples of table salt and water"],
        },
        "starter": {
            "activity": (
                "Teacher displays water, table salt and carbon dioxide and asks "
                "learners to identify the elements in each binary compound. "
                "Learners discuss in pairs and name the binary compounds they see."),
            "duration_minutes": 10,
            "teacher_action": "Display the substances and ask guiding questions.",
            "learner_action": "Name each binary compound and its elements.",
        },
        "main_learning": {
            "phase1": {
                "name": "Presentation",
                "activity": (
                    "Teacher presents the names and formulae of common binary "
                    "compounds: water, sodium chloride, carbon dioxide, hydrogen "
                    "chloride, ammonia and calcium oxide. Teacher explains that "
                    "each binary compound contains exactly two elements and "
                    "discusses one use of each binary compound."),
                "duration_minutes": 15,
                "teacher_action": "Write each formula and explain its two elements.",
                "learner_action": "Copy the formulae and ask questions.",
                "resources_used": ["Chalkboard"],
            },
            "phase2": {
                "name": "Discussion",
                "activity": (
                    "Learners work in small groups to list at least five binary "
                    "compounds and one use of each binary compound. Teacher moves "
                    "around to correct misconceptions about binary compounds."),
                "duration_minutes": 15,
                "teacher_action": "Guide groups and correct misconceptions.",
                "learner_action": "List compounds and uses, then share with the class.",
                "resources_used": ["Exercise books"],
            },
            "phase3": {
                "name": "Application",
                "activity": (
                    "Each group presents its list of binary compounds and uses. "
                    "Learners then complete a matching task that links each binary "
                    "compound formula to its name and one use."),
                "duration_minutes": 10,
                "teacher_action": "Check each group's matching task and give feedback.",
                "learner_action": "Match formulae to names and state one use.",
                "resources_used": ["Chalkboard"],
            },
        },
        "assessment": {
            "method": "Oral questioning and a written matching task",
            "activity": (
                "Teacher asks each learner to identify by name three binary "
                "compounds from their formulae and state one use of each binary "
                "compound. Teacher also checks the matching task."),
            "success_criteria": (
                "Each learner correctly names three binary compounds, states one "
                "use of each, and names one further binary compound."),
            "duration_minutes": 10,
        },
        "plenary": {
            "activity": (
                "Teacher summarises the lesson and asks each learner to write one "
                "binary compound and one use on an exit slip. Teacher collects the "
                "slips to check individual understanding."),
            "duration_minutes": 5,
            "teacher_action": "Collect exit slips and correct misconceptions.",
            "learner_action": "Write one binary compound and one use on the slip.",
        },
        "differentiation": {
            "support": "Provide a word bank and pair with a stronger learner.",
            "core": "List five binary compounds and one use of each.",
            "extension": "Write the formula for one extra binary compound.",
        },
        "homework_or_extension": (
            "Learners list three binary compounds used at home and state one use "
            "of each."),
        "teacher_notes": "Use local examples such as table salt and water.",
    }


class FakeProvider:
    def __init__(self, content=None, error=None, name="deepseek",
                 model="fake-model", available=True):
        self.content = _science_lesson() if content is None else content
        self.last_error = error
        self.name = name
        self.model = model
        self.available = available
        self.calls = 0
        self.last_cache_hit = False

    def is_available(self):
        return self.available

    def get_name(self):
        return self.name

    def generate_lesson_v2(self, **kwargs):
        self.calls += 1
        if self.last_error:
            return {}
        return json.loads(json.dumps(self.content))


def _context():
    return {
        "subject": "Science", "class_level": "Basic 9",
        "strand": "Diversity of Matter", "sub_strand": "Materials",
        "content_standard": "B9.1.1.1 Standard",
        "indicator_code": "B9.1.1.1.1",
        "indicator_text": "Identify binary compounds",
        "duration_minutes": 60,
    }


# ── Unit contracts ──────────────────────────────────────────────────────────

def test_primary_success_does_not_call_fallback(db):
    primary = FakeProvider(name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")
    content, meta = zg.generate_zeli_with_fallback(
        primary=primary, fallback=fallback, context=_context(), db=db)
    assert content
    assert primary.calls == 1
    assert fallback.calls == 0
    assert meta["fallback_used"] is False
    assert meta["provider"] == "deepseek"
    assert meta["model"] == "deepseek-flash"


@pytest.mark.parametrize("error,status", [
    ("timeout while reading", 504),
    ("rate_limit", 429),
    ("http_500", 502),
    ("malformed_json", 502),
    ("schema_invalid:missing_sections", 502),
])
def test_eligible_primary_failure_falls_back_once(db, error, status):
    primary = FakeProvider(error=error, name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")
    content, meta = zg.generate_zeli_with_fallback(
        primary=primary, fallback=fallback, context=_context(), db=db)
    assert content
    assert primary.calls == 1
    assert fallback.calls == 1
    assert meta["fallback_used"] is True
    assert meta["provider"] == "groq"
    assert meta["model"] == "groq-model"
    assert meta["primary_provider"] == "deepseek"
    assert meta["primary_error"] == (
        "timeout" if "timeout" in error else
        "rate_limit" if "rate_limit" in error else
        "http_500" if "http_500" in error else
        "malformed_json" if "malformed_json" in error else
        "schema_invalid"
    )
    assert len(meta["attempts"]) == 2
    assert meta["attempts"][0]["ok"] is False
    assert meta["attempts"][1]["ok"] is True


@pytest.mark.parametrize("error", [
    "auth_failed", "missing_api_key", "invalid_api_key",
    "model_not_found", "invalid_request",
])
def test_ineligible_primary_failure_does_not_fall_back(db, error):
    primary = FakeProvider(error=error, name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")
    with pytest.raises(zg.ZeliGenerationError):
        zg.generate_zeli_with_fallback(
            primary=primary, fallback=fallback, context=_context(), db=db)
    assert fallback.calls == 0


def test_unavailable_fallback_does_not_mask_primary_failure(db):
    primary = FakeProvider(error="timeout", name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model", available=False)
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_with_fallback(
            primary=primary, fallback=fallback, context=_context(), db=db)
    assert exc.value.status_code == 504
    assert fallback.calls == 0


def test_both_providers_fail_without_content_or_credit(db):
    primary = FakeProvider(error="timeout", name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(error="rate_limit", name="groq", model="groq-model")
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_with_fallback(
            primary=primary, fallback=fallback, context=_context(), db=db)
    assert exc.value.status_code in (429, 502, 503)
    assert len(exc.value.attempts) == 2
    assert primary.calls == 1 and fallback.calls == 1


def test_cache_hit_makes_no_external_call_and_reports_it(db):
    primary = FakeProvider(name="deepseek", model="deepseek-flash")
    # First run writes the cache.
    zg.generate_zeli_with_fallback(
        primary=primary, fallback=None, context=_context(), db=db)
    # Second run must hit the cache and make no provider call.
    content, meta = zg.generate_zeli_with_fallback(
        primary=primary, fallback=None, context=_context(), db=db)
    assert content
    assert primary.calls == 1  # only the first run
    assert meta["cache_hit"] is True
    assert meta["external_calls"] == 0


# ── Pipeline / HTTP integration ─────────────────────────────────────────────

def _seed_scheme(db, owner_id):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="fallback.docx",
        subject="Science", class_level="Basic 9", term="1",
        academic_year="2026/2027", status="processed", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    db.add(WeekDB(
        id=generate_id(), scheme_id=scheme.id, week_number=1,
        week_type="instruction", start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 11), week_ending_derived=False,
        strand="Diversity of Matter", sub_strand="Materials",
        content_standards=["B9.1.1.1 Standard"],
        indicators=["B9.1.1.1.1 Identify binary compounds"],
        resources=["Chart"],
    ))
    db.commit()
    return scheme


def _config(scheme_id):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 9, 11),
        lessons_per_week=1, lesson_duration_minutes=60, class_size=35,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        generation_method="zeli", include_special_weeks=False,
        class_level="Basic 9", subject="Science",
        selected_indicator_codes=["B9.1.1.1.1"],
    )


def _entitle(db, user):
    db.add(EntitlementDB(
        id=generate_id(), user_id=user.id, edition="free",
        features=["ai_basic"], ai_enabled=True, subscription_type="individual",
        status="active", ai_credits=5, generation_limit=5,
    ))
    db.commit()


def _app(db, user):
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _run_http(db, monkeypatch, user, scheme, primary, fallback):
    import src.routers.generation as gen
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: primary)
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_fallback_provider",
        lambda: fallback)
    monkeypatch.setattr(gen, "zeli_availability", lambda: {
        "enabled": True, "configured": True, "available": True,
        "state": "CONFIGURED", "method": "zeli", "reason": None,
    })
    with TestClient(_app(db, user)) as client:
        return client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id).model_dump(mode="json"),
        )


def test_http_fallback_persists_actual_provider_and_charges_once(db, monkeypatch):
    user = make_user(db)
    _entitle(db, user)
    scheme = _seed_scheme(db, user.id)
    primary = FakeProvider(error="timeout", name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")

    resp = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai"]["provider"] == "groq"
    assert body["ai"]["fallback_used"] is True
    assert body["ai"]["primary_provider"] == "deepseek"
    assert body["ai"]["primary_error"] == "timeout"
    assert body["quota"]["used"] == 1
    assert body["ai_credits_remaining"] == 4

    lesson = db.query(LessonPlanDB).one()
    assert lesson.ai_provider == "groq"
    assert lesson.ai_model == "groq-model"
    assert lesson.generation_method == "zeli"
    # Exactly one lesson unit and one AI request event.
    assert db.query(UsageUnitDB).count() == 1
    assert db.query(AIUsageEventDB).count() == 1


def test_http_both_providers_fail_no_lesson_no_credit(db, monkeypatch):
    user = make_user(db)
    _entitle(db, user)
    scheme = _seed_scheme(db, user.id)
    primary = FakeProvider(error="timeout", name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(error="rate_limit", name="groq", model="groq-model")

    resp = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert resp.status_code in (429, 502, 503)
    assert db.query(LessonPlanDB).count() == 0
    assert db.query(UsageUnitDB).count() == 0
    assert db.query(AIUsageEventDB).count() == 0


def test_http_quality_rejection_falls_back_once(db, monkeypatch):
    user = make_user(db)
    _entitle(db, user)
    scheme = _seed_scheme(db, user.id)
    weak = _science_lesson()
    weak["learning_objectives"] = [
        "Learners can discuss the topic.",
        "Learners can understand binary compounds.",
    ]
    primary = FakeProvider(content=weak, name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")

    resp = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai"]["provider"] == "groq"
    assert body["ai"]["fallback_used"] is True
    assert body["ai"]["primary_provider"] == "deepseek"
    assert body["ai"]["primary_error"] == "quality_gate_rejected"
    assert db.query(LessonPlanDB).one().ai_provider == "groq"
    assert db.query(UsageUnitDB).count() == 1
    assert db.query(AIUsageEventDB).count() == 1


def test_http_primary_auth_failure_does_not_fall_back(db, monkeypatch):
    user = make_user(db)
    _entitle(db, user)
    scheme = _seed_scheme(db, user.id)
    primary = FakeProvider(error="auth_failed", name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")

    resp = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert resp.status_code == 503
    assert fallback.calls == 0
    assert db.query(LessonPlanDB).count() == 0


def test_http_pure_cache_replay_does_not_charge_ai_credit(db, monkeypatch):
    user = make_user(db)
    _entitle(db, user)
    scheme = _seed_scheme(db, user.id)
    primary = FakeProvider(name="deepseek", model="deepseek-flash")
    fallback = FakeProvider(name="groq", model="groq-model")

    first = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert first.status_code == 200, first.text
    assert primary.calls == 1
    assert db.query(AIUsageEventDB).count() == 1

    # A fresh job for the same inputs is served from the Zeli cache.
    second = _run_http(db, monkeypatch, user, scheme, primary, fallback)
    assert second.status_code == 200, second.text
    assert second.json()["ai"]["fallback_used"] is False
    assert primary.calls == 1  # no external call
    # One lesson-plan unit (same scheme+indicator) and no second AI event.
    assert db.query(UsageUnitDB).count() == 1
    assert db.query(AIUsageEventDB).count() == 1

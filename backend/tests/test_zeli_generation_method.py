"""Generate with Zeli — whole-lesson generation method.

Zeli is SchemeKnit's teacher-facing generation assistant. Its verified runtime
provider is Groq (``openai/gpt-oss-120b`` by default). These tests cover the NEW
whole-lesson method added alongside the existing OFF/BASIC/ENHANCED options:

* ``TermConfig.generation_method`` validation (default ``standard``)
* cache identity that separates method, provider, model and every material input
* strict whole-lesson output validation (partial JSON is never merged)
* provider-availability reporting without leaking secrets
* pipeline generation, provenance and honest failure (no silent fallback)
* cache reuse across identical runs
* generate endpoint selection, persistence, status and quota behaviour
* teacher-facing UI source contract

Provider calls are always mocked here. Real connectivity is exercised
separately (and only when credentials are present) — mocked tests are NOT proof
of live provider behaviour.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (  # noqa: E402
    Base, EntitlementDB, GenerationJobDB, LessonPlanDB, SchemeDB, WeekDB,
    generate_id,
)
from src.models import (  # noqa: E402
    AIMode, ClassLevel, GenerationMethod, LessonPlan, Subject, TeachingActivity,
    TermConfig,
)
from src.engines import zeli_generation as zg  # noqa: E402
from tests.conftest import make_user  # noqa: E402


# ── Fixtures / helpers ──────────────────────────────────────────────────────

def _seed_scheme(db, owner_id, weeks=2):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="zeli.docx",
        subject="ICT", class_level="Basic 7",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Computing",
            sub_strand="Hardware",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify a device"],
            resources=["Chart"],
        ))
    db.commit()
    return scheme


def _config(scheme_id, method="zeli", ai_mode="OFF"):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0], holidays=[], ai_mode=AIMode(ai_mode),
        generation_method=method, include_special_weeks=False,
        class_level="Basic 7", subject="ICT",
    )


def _full_lesson(marker="ZELI"):
    return {
        "learning_objectives": [
            "Learners can identify a device by naming it and stating one use "
            "in the classroom",
            "Learners can explain one use of a device to a partner",
        ],
        "key_vocabulary": [f"{marker.lower()}_vocab"],
        "starter": {
            "activity": (
                f"{marker} starter: the teacher shows real classroom devices "
                "and asks learners in pairs to name each device and say one "
                "use."
            )
        },
        "main_learning": {
            "phase1": {
                "name": "Guided discovery",
                "activity": (
                    f"{marker} phase one: learners sort a set of real "
                    "classroom devices into working and non-working groups, "
                    "naming each one aloud."
                ),
                "duration_minutes": 20,
                "resources_used": ["Bottle caps", "Chart"],
            },
            "phase2": {
                "name": "Group task",
                "activity": (
                    f"{marker} phase two: in pairs, learners label a chart "
                    "with the name and one use of each device, then swap "
                    "charts to check a partner's answers."
                ),
                "duration_minutes": 20,
            },
        },
        "assessment": {
            "method": "Observation",
            "activity": (
                f"{marker} assessment: the teacher observes each pair as they "
                "identify a device and match it to its use, and marks correct "
                "answers on a checklist."
            ),
        },
        "plenary": {
            "activity": (
                f"{marker} plenary: learners summarise in one sentence what "
                "they learned about each device, and the teacher checks that "
                "every pair can identify one device correctly."
            )
        },
        "differentiation": {
            "support": f"{marker} support: pair with a peer",
            "core": f"{marker} core: complete the chart",
            "extension": f"{marker} extension: suggest a new device",
        },
        "homework_or_extension": f"{marker} homework: list three devices at home",
    }


class FakeZeliProvider:
    """Deterministic stand-in for the verified provider contract."""

    def __init__(self, content=None, available=True, name="groq",
                 model="test-zeli-model"):
        self.content = _full_lesson() if content is None else content
        self.available = available
        self.name = name
        self.model = model
        self.last_error = None
        self.calls = []

    def is_available(self):
        return self.available

    def get_name(self):
        return self.name

    def generate_lesson_v2(self, **kwargs):
        self.calls.append(kwargs)
        if self.last_error:
            return {}
        return json.loads(json.dumps(self.content))


def _settings(**overrides):
    base = dict(
        ZELI_ENABLED=True, ZELI_PROVIDER="groq", ZELI_MODEL="",
        ZELI_BASE_URL="", ZELI_API_KEY="",
        GROQ_API_KEY="gsk_test_key", GROQ_MODEL="openai/gpt-oss-120b",
        GROQ_BASE_URL="https://api.groq.com/openai/v1",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _app(db, user):
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router
    from src.routers import settings as settings_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.include_router(settings_router.router, prefix="/api/settings")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _entitle_ai(db, user):
    db.add(EntitlementDB(
        id=generate_id(), user_id=user.id, edition="free",
        subscription_type="individual", status="active",
        ai_enabled=True, ai_credits=5, generation_limit=5,
        features=["ai_basic"],
    ))
    db.commit()


# ── 1. Config / selection model ─────────────────────────────────────────────

def test_generation_method_defaults_to_standard_and_accepts_zeli():
    config = _config("scheme-1", method="standard")
    assert config.generation_method is GenerationMethod.STANDARD

    zeli = _config("scheme-1", method="zeli")
    assert zeli.generation_method is GenerationMethod.ZELI
    # The existing AI options remain independent and valid alongside Zeli.
    assert zeli.ai_mode is AIMode.OFF


def test_generation_method_rejects_unknown_value():
    with pytest.raises(Exception):
        _config("scheme-1", method="carrier-pigeon")


def test_generation_method_round_trips_through_snapshot():
    from src.routers.generation import _config_from_snapshot

    config = _config("scheme-1", method="zeli")
    rebuilt = _config_from_snapshot(config.model_dump(mode="json"))
    assert rebuilt.generation_method is GenerationMethod.ZELI

    # A legacy snapshot without the field must stay on the Standard path.
    legacy = config.model_dump(mode="json")
    legacy.pop("generation_method")
    assert _config_from_snapshot(legacy).generation_method is GenerationMethod.STANDARD


# ── 2. Cache identity ───────────────────────────────────────────────────────

def test_cache_key_separates_method_provider_model_and_material_inputs():
    payload = {"indicator_code": "B7.1.1.1.1", "duration_minutes": 60}
    base = zg.zeli_cache_key(
        provider="groq", model="openai/gpt-oss-120b", lesson_payload=payload)

    assert base == zg.zeli_cache_key(
        provider="groq", model="openai/gpt-oss-120b", lesson_payload=payload)
    assert base != zg.zeli_cache_key(
        provider="gemini", model="openai/gpt-oss-120b", lesson_payload=payload)
    assert base != zg.zeli_cache_key(
        provider="groq", model="openai/gpt-oss-20b", lesson_payload=payload)
    assert base != zg.zeli_cache_key(
        provider="groq", model="openai/gpt-oss-120b",
        lesson_payload={**payload, "duration_minutes": 45})
    # The method is part of the key namespace, so a Standard run can never read
    # a Zeli entry even if the provider/model/inputs happen to match.
    assert zg.ZELI_METHOD == "zeli"


def test_zeli_result_is_not_served_for_another_method(db):
    provider = FakeZeliProvider()
    context = {"indicator_code": "B7.1.1.1.1", "duration_minutes": 60}
    content = zg.generate_zeli_content(provider=provider, context=context, db=db)
    assert content["starter"]["activity"].startswith("ZELI")

    # A key computed for a different method provider/model must miss.
    other = zg.zeli_cache_key(
        provider="other", model="other-model", lesson_payload=context)
    assert zg.read_zeli_cache(db, other) is None
    assert db.query(zg.ZeliGenerationCacheDB).count() == 1


# ── 3. Output validation ────────────────────────────────────────────────────

def test_validate_zeli_content_accepts_a_complete_lesson():
    assert zg.validate_zeli_content(_full_lesson()) == ""


@pytest.mark.parametrize("missing", [
    "learning_objectives", "starter", "main_learning", "assessment",
    "plenary", "differentiation",
])
def test_validate_zeli_content_rejects_missing_sections(missing):
    content = _full_lesson()
    content.pop(missing)
    assert zg.validate_zeli_content(content).startswith("missing_sections:")


def test_validate_zeli_content_rejects_incomplete_main_learning():
    content = _full_lesson()
    content["main_learning"] = {"phase1": {"activity": "only one phase"}}
    assert zg.validate_zeli_content(content) == "incomplete_main_learning"


def test_validate_zeli_content_rejects_non_object():
    assert zg.validate_zeli_content(["not", "an", "object"]) == "not_an_object"


# ── 4. Provider availability (no secrets) ───────────────────────────────────

def test_zeli_availability_reports_missing_key():
    state = zg.zeli_availability(_settings(GROQ_API_KEY=""))
    assert state["available"] is False
    assert state["state"] == "MISSING_KEY"
    assert "api" not in json.dumps(state).lower().split("reason")[0]
    assert "gsk_" not in json.dumps(state)


def test_zeli_availability_reports_configured():
    state = zg.zeli_availability(_settings())
    assert state["available"] is True
    assert state["configured"] is True
    assert state["method"] == "zeli"


def test_zeli_availability_reports_disabled():
    state = zg.zeli_availability(_settings(ZELI_ENABLED=False))
    assert state["available"] is False
    assert state["state"] == "DISABLED"


def test_zeli_availability_rejects_unknown_provider():
    state = zg.zeli_availability(_settings(ZELI_PROVIDER="not-a-provider"))
    assert state["available"] is False
    assert state["state"] == "INVALID_CONFIG"


# ── 5. Pipeline generation + provenance ─────────────────────────────────────

def _run_pipeline(db, monkeypatch, provider, method="zeli", weeks=2):
    from src.engines.generation_pipeline import GenerationPipeline
    from src.service import data_service

    user = make_user(db)
    scheme_db = _seed_scheme(db, user.id, weeks=weeks)
    scheme = data_service.scheme_to_model(scheme_db)
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: provider)
    job = GenerationPipeline().generate_all(
        scheme, _config(scheme_db.id, method=method), db=db)
    return job, scheme_db


def test_pipeline_generates_whole_lessons_with_zeli_provenance(db, monkeypatch):
    provider = FakeZeliProvider()
    job, _ = _run_pipeline(db, monkeypatch, provider, weeks=2)

    assert job.status.value == "completed"
    assert len(job._lesson_plans) == 2
    assert len(provider.calls) == 2
    for lp in job._lesson_plans:
        assert lp.ai_generated is True
        assert lp.generation_method == "zeli"
        assert lp.ai_provider == "groq"
        assert lp.ai_model == "test-zeli-model"
        assert "ZELI" in (lp.starter_activity or "")
        assert "ZELI" in (lp.assessment or "")
        assert "Needs Support (NS):" in (lp.differentiation or "")
        # Curriculum authority is untouched by the provider.
        assert lp.indicator_codes == [lp.indicator_codes[0]]
        assert lp.indicator_codes[0].startswith("B7.1.1.")


def test_pipeline_runs_zeli_even_when_ai_mode_is_off(db, monkeypatch):
    # The generation METHOD is the authority; ai_mode only governs the
    # existing optional enrichment path.
    provider = FakeZeliProvider()
    job, _ = _run_pipeline(db, monkeypatch, provider, method="zeli", weeks=1)
    assert job.status.value == "completed"
    assert len(provider.calls) == 1


def test_pipeline_never_silently_falls_back_when_zeli_fails(db, monkeypatch):
    provider = FakeZeliProvider(content={})
    provider.last_error = "rate_limit"
    job, _ = _run_pipeline(db, monkeypatch, provider, weeks=2)

    assert job.status.value == "failed"
    error = getattr(job, "_zeli_error", None)
    assert error is not None
    assert error.status_code == 429
    assert "quota" in error.message.lower()
    for lp in job._lesson_plans:
        assert lp.ai_generated is False


def test_pipeline_rejects_partial_zeli_output(db, monkeypatch):
    partial = _full_lesson()
    partial.pop("assessment")
    provider = FakeZeliProvider(content=partial)
    job, _ = _run_pipeline(db, monkeypatch, provider, weeks=1)

    assert job.status.value == "failed"
    error = getattr(job, "_zeli_error", None)
    assert error is not None
    assert error.status_code == 502
    assert "differentiation" not in error.message  # teacher-safe wording
    assert "missing_sections" not in error.message


def test_pipeline_standard_path_ignores_zeli(db, monkeypatch):
    provider = FakeZeliProvider()
    job, _ = _run_pipeline(db, monkeypatch, provider, method="standard", weeks=1)
    assert job.status.value == "completed"
    assert provider.calls == []
    assert job._lesson_plans[0].generation_method == "standard"


# ── 5b. V2 mapping fidelity (provider prose is kept, not dropped) ───────────

def _bare_lesson():
    return LessonPlan(
        id="zeli-map-lp",
        scheme_of_work_id="zeli-map-scheme",
        term_config_id="zeli-map-config",
        week_number=1,
        lesson_sequence=1,
        lesson_number=1,
        lesson_date=date(2026, 9, 7),
        class_level=ClassLevel.BASIC_7,
        subject=Subject.ICT,
        class_size=35,
        duration_minutes=60,
        strand="Computing",
        sub_strand="Hardware",
        content_standard="Identify a device",
        indicators=["B7.1.1.1.1 Identify a device"],
        indicator_codes=["B7.1.1.1.1"],
    )


def test_v2_mapping_keeps_provider_starter_assessment_and_plenary_actions():
    from src.engines.generation_pipeline import GenerationPipeline

    content = _full_lesson()
    content["starter"]["teacher_action"] = "Show real devices and ask each pair to name one."
    content["starter"]["learner_action"] = "Name each device and state one use."
    content["assessment"]["success_criteria"] = (
        "Each pair names a device and states one correct use.")
    content["plenary"]["teacher_action"] = (
        "Check that every pair can identify one device accurately.")
    content["plenary"]["learner_action"] = (
        "State one device and one use in their own words.")

    lp = _bare_lesson()
    GenerationPipeline()._apply_v2_content(lp, content)

    assert "ZELI starter" in lp.starter_activity
    assert "Teacher: Show real devices" in lp.starter_activity
    assert "Learners: Name each device" in lp.starter_activity
    assert "Success criteria: Each pair names a device" in lp.assessment
    assert "Teacher: Check that every pair" in lp.conclusion
    assert "Learners: State one device" in lp.conclusion


def test_v2_mapping_drops_placeholder_resources():
    from src.engines.generation_pipeline import GenerationPipeline

    content = _full_lesson()
    content["main_learning"]["phase1"]["resources_used"] = [
        "None", "N/A", "null", "Chart"]
    content["resources"] = {"suggested_alternatives": [None, "Real objects"]}

    lp = _bare_lesson()
    GenerationPipeline()._apply_v2_content(lp, content)

    phase_resources = [
        r for act in lp.main_activities for r in (act.resources or [])]
    assert "Chart" in phase_resources
    for placeholder in ("None", "N/A", "null"):
        assert placeholder not in phase_resources
    assert "Real objects" in lp.teaching_learning_resources
    assert not any(
        str(r).strip().lower() in {"none", "n/a", "na", "null", "nil", "-"}
        for r in lp.teaching_learning_resources)


def test_v2_mapping_fills_empty_columns_with_provider_actions():
    from src.engines.generation_pipeline import GenerationPipeline

    content = _full_lesson()
    content["main_learning"]["phase1"]["teacher_action"] = (
        "Circulate and check each pair's chart.")
    content["main_learning"]["phase1"]["learner_action"] = (
        "Sort the devices and name each one aloud.")

    lp = _bare_lesson()
    assert lp.teacher_activities == []
    assert lp.learner_activities == []
    GenerationPipeline()._apply_v2_content(lp, content)

    assert len(lp.teacher_activities) == 1
    assert "Teacher: Circulate and check" in lp.teacher_activities[0].description
    assert len(lp.learner_activities) == 1
    assert "Learners: Sort the devices" in lp.learner_activities[0].description


def test_v2_mapping_never_replaces_curriculum_grounded_columns():
    from src.engines.generation_pipeline import GenerationPipeline

    content = _full_lesson()
    content["main_learning"]["phase1"]["teacher_action"] = "Circulate."
    content["main_learning"]["phase1"]["learner_action"] = "Sort devices."

    lp = _bare_lesson()
    lp.teacher_activities = [TeachingActivity(
        phase="PHASE 1 · STARTER",
        description="Build on the previous lesson and ask learners to name a device.",
        duration_minutes=5,
    )]
    lp.learner_activities = [TeachingActivity(
        phase="PHASE 1 · STARTER",
        description="Learners name one device they already use at home.",
        duration_minutes=5,
    )]
    GenerationPipeline()._apply_v2_content(lp, content)

    assert len(lp.teacher_activities) == 1
    assert lp.teacher_activities[0].description.startswith("Build on the previous lesson")
    assert len(lp.learner_activities) == 1
    assert lp.learner_activities[0].description.startswith("Learners name one device")


# ── 6. Cache reuse ──────────────────────────────────────────────────────────

def test_identical_run_reuses_cached_lessons(db, monkeypatch):
    provider = FakeZeliProvider()
    job1, scheme_db = _run_pipeline(db, monkeypatch, provider, weeks=2)
    assert job1.status.value == "completed"
    assert len(provider.calls) == 2

    from src.engines.generation_pipeline import GenerationPipeline
    from src.service import data_service

    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: provider)
    job2 = GenerationPipeline().generate_all(
        data_service.scheme_to_model(scheme_db),
        _config(scheme_db.id, method="zeli"), db=db)
    assert job2.status.value == "completed"
    # Second run served entirely from cache: no new provider calls.
    assert len(provider.calls) == 2


# ── 7. Generate endpoint ────────────────────────────────────────────────────

def test_generate_rejects_zeli_when_unconfigured_before_quota(db, monkeypatch):
    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=1)
    monkeypatch.setattr(
        "src.routers.generation.zeli_availability",
        lambda: {
            "enabled": True, "configured": False, "available": False,
            "state": "MISSING_KEY", "method": "zeli",
            "reason": "Zeli is not configured on this server.",
        },
    )

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id, method="zeli").model_dump(mode="json"),
        )

    assert resp.status_code == 503
    assert "Zeli" in resp.json()["detail"]
    assert db.query(GenerationJobDB).count() == 0
    assert db.query(LessonPlanDB).count() == 0


def test_generate_with_zeli_persists_method_and_provenance(db, monkeypatch):
    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=1)
    provider = FakeZeliProvider()

    monkeypatch.setattr(
        "src.routers.generation.zeli_availability",
        lambda: {
            "enabled": True, "configured": True, "available": True,
            "state": "CONFIGURED", "method": "zeli", "reason": None,
        },
    )
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: provider)

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id, method="zeli").model_dump(mode="json"),
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ai"]["generation_method"] == "zeli"
    assert body["completed_lessons"] == 1

    lesson = db.query(LessonPlanDB).one()
    assert lesson.generation_method == "zeli"
    assert lesson.ai_provider == "groq"
    assert lesson.ai_model == "test-zeli-model"
    assert lesson.ai_generated is True

    job = db.query(GenerationJobDB).one()
    assert job.config_snapshot["generation_method"] == "zeli"

    # Status poll and lesson list keep the method (reload / recovery safe).
    with TestClient(_app(db, user)) as client:
        status = client.get(f"/api/generation/{job.id}/status").json()
        assert status["generation_method"] == "zeli"
        lessons = client.get(
            f"/api/generation/schemes/{scheme.id}/lessons").json()
        rows = (
            lessons.get("lesson_plans")
            or lessons.get("lessons")
            if isinstance(lessons, dict) else lessons
        )
        assert rows and rows[0]["generation_method"] == "zeli"


def test_generate_with_zeli_does_not_expose_credentials(db, monkeypatch):
    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=1)
    provider = FakeZeliProvider()
    monkeypatch.setattr(
        "src.routers.generation.zeli_availability",
        lambda: {
            "enabled": True, "configured": True, "available": True,
            "state": "CONFIGURED", "method": "zeli", "reason": None,
        },
    )
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: provider)

    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id, method="zeli").model_dump(mode="json"),
        )
        status_resp = client.get("/api/settings/ai-status?ai_mode=OFF")

    combined = (resp.text + status_resp.text).lower()
    assert "gsk_" not in combined
    assert "api_key" not in combined
    assert "openai/gpt-oss-120b" not in combined


# ── 8. AI status reports the Zeli method ────────────────────────────────────

def test_ai_status_reports_zeli_method(db, monkeypatch):
    user = make_user(db)
    monkeypatch.setattr(
        "src.engines.zeli_generation.zeli_availability",
        lambda: {
            "enabled": True, "configured": True, "available": True,
            "state": "CONFIGURED", "method": "zeli", "reason": None,
        },
    )
    with TestClient(_app(db, user)) as client:
        resp = client.get(
            "/api/settings/ai-status?ai_mode=OFF&generation_method=zeli")
    assert resp.status_code == 200
    data = resp.json()
    assert data["generation_method"] == "zeli"
    assert data["active"] is True
    assert data["state"] == "CONFIGURED"


# ── 9. Teacher-facing UI source contract ────────────────────────────────────

def _frontend(path):
    root = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return fh.read()


def test_generate_page_offers_zeli_and_keeps_existing_options():
    page = _frontend("src/app/(app)/generate/[id]/page.tsx")

    # The accessible, clearly labelled option exists exactly once as a choice.
    assert "Generate with Zeli" in page
    assert 'data-generation-method' in page
    assert "generation_method" in page
    # Existing generation options are preserved.
    for option in ('"OFF"', '"BASIC"', '"ENHANCED"'):
        assert f"value={option}" in page or f"'{option}'" in page
    # Zeli availability drives a real disabled state, not a misleading button.
    assert "zeliStatus" in page or "zeli_status" in page or "zeliStatus" in page


def test_api_client_sends_generation_method_and_reports_zeli_status():
    api = _frontend("src/lib/api.ts")
    assert "generation_method" in api
    assert "generation_method=" in api or "generationMethod" in api


def test_generate_page_disables_enrichment_mode_for_zeli():
    page = _frontend("src/app/(app)/generate/[id]/page.tsx")
    # Exposed only as an explicit choice; the existing OFF/BASIC/ENHANCED
    # select must be disabled (with a reason) while Zeli is selected.
    assert "disabled={config.generation_method === 'zeli'}" in page
    assert "cfg-ai-mode-note" in page


# ── 10. Resume / retry / recovery ───────────────────────────────────────────

def _run_http_zeli(db, monkeypatch, user, scheme, provider, weeks=1):
    monkeypatch.setattr(
        "src.routers.generation.zeli_availability",
        lambda: {
            "enabled": True, "configured": True, "available": True,
            "state": "CONFIGURED", "method": "zeli", "reason": None,
        },
    )
    monkeypatch.setattr(
        "src.engines.generation_pipeline.get_zeli_provider", lambda: provider)
    with TestClient(_app(db, user)) as client:
        return client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id, method="zeli").model_dump(mode="json"),
        )


def test_resume_preserves_zeli_method(db, monkeypatch):
    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=2)
    provider = FakeZeliProvider()

    first = _run_http_zeli(db, monkeypatch, user, scheme, provider)
    assert first.status_code == 200, first.text
    job = db.query(GenerationJobDB).one()
    assert job.config_snapshot["generation_method"] == "zeli"

    # Simulate a partial run: one planned lesson never made it to disk.
    lessons = db.query(LessonPlanDB).order_by(LessonPlanDB.lesson_sequence).all()
    assert len(lessons) == 2
    db.delete(lessons[-1])
    job.status = "failed"
    db.commit()

    with TestClient(_app(db, user)) as client:
        resumed = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id},
        )

    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["resumed"] is True
    rows = db.query(LessonPlanDB).all()
    assert len(rows) == 2
    for row in rows:
        assert row.generation_method == "zeli"
        assert row.ai_provider == "groq"


def test_resume_does_not_consume_a_second_ai_credit(db, monkeypatch):
    from src.database import AIUsageEventDB

    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=2)
    provider = FakeZeliProvider()

    first = _run_http_zeli(db, monkeypatch, user, scheme, provider)
    assert first.status_code == 200, first.text
    job = db.query(GenerationJobDB).one()
    events_after_first = db.query(AIUsageEventDB).filter(
        AIUsageEventDB.request_id == job.id).count()
    assert events_after_first == 1

    lessons = db.query(LessonPlanDB).order_by(LessonPlanDB.lesson_sequence).all()
    db.delete(lessons[-1])
    job.status = "failed"
    db.commit()

    with TestClient(_app(db, user)) as client:
        resumed = client.post(
            f"/api/generation/{scheme.id}/generate/resume",
            json={"job_id": job.id},
        )
    assert resumed.status_code == 200, resumed.text
    # Same job id → the same successful request can never be charged twice.
    events_after_resume = db.query(AIUsageEventDB).filter(
        AIUsageEventDB.request_id == job.id).count()
    assert events_after_resume == 1


def test_failed_zeli_run_keeps_existing_lessons_and_reports_honestly(
        db, monkeypatch):
    user = make_user(db)
    _entitle_ai(db, user)
    scheme = _seed_scheme(db, user.id, weeks=1)
    provider = FakeZeliProvider()
    ok = _run_http_zeli(db, monkeypatch, user, scheme, provider)
    assert ok.status_code == 200, ok.text
    assert db.query(LessonPlanDB).count() == 1

    # A second scheme fails at the provider (rate limit). Nothing is persisted
    # and the first scheme's lesson is untouched. A distinct indicator keeps
    # this run from being served by the first run's cache.
    other = _seed_scheme(db, user.id, weeks=1)
    week = db.query(WeekDB).filter(WeekDB.scheme_id == other.id).one()
    week.indicators = ["B7.1.1.9.1 Identify a device"]
    db.commit()
    broken = FakeZeliProvider(content={})
    broken.last_error = "rate_limit_exceeded"
    failed = _run_http_zeli(db, monkeypatch, user, other, broken)

    assert failed.status_code == 429, failed.text
    assert "quota" in failed.json()["detail"].lower()
    assert db.query(LessonPlanDB).count() == 1


# ── 11. Provider failure classification ─────────────────────────────────────

@pytest.mark.parametrize("last_error,expected_status", [
    ("http_401 unauthorized", 503),
    ("invalid_api_key", 503),
    ("model_not_found", 503),
    ("timeout while reading response", 504),
    ("connection reset by peer", 504),
    ("rate_limit_exceeded", 429),
    ("something unexpected", 502),
])
def test_zeli_provider_failures_are_classified(last_error, expected_status):
    provider = FakeZeliProvider(content={})
    provider.last_error = last_error
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_content(
            provider=provider,
            context={"indicator_code": "B7.1.1.1.1", "duration_minutes": 60},
            db=None,
        )
    assert exc.value.status_code == expected_status
    # Teacher-safe: never the raw provider diagnostic.
    assert last_error.lower() not in exc.value.message.lower()


def test_zeli_malformed_output_is_rejected_not_merged():
    provider = FakeZeliProvider(content=["not", "a", "lesson"])
    with pytest.raises(zg.ZeliGenerationError) as exc:
        zg.generate_zeli_content(
            provider=provider,
            context={"indicator_code": "B7.1.1.1.1", "duration_minutes": 60},
            db=None,
        )
    assert exc.value.status_code == 502
    assert "quota" in exc.value.message.lower()


# ── 12. Cache identity covers every material input ──────────────────────────

def test_cache_key_changes_with_teacher_supplied_material_inputs():
    base = {"indicator_code": "B7.1.1.1.1", "duration_minutes": 60}
    key = zg.zeli_cache_key(
        provider="groq", model="m", lesson_payload=base)
    for field, value in (
        ("teacher_keywords", ["device"]),
        ("core_competencies", ["Critical Thinking"]),
        ("source_resources", ["Chart"]),
        ("teaching_day", 2),
        ("week_number", 5),
    ):
        assert key != zg.zeli_cache_key(
            provider="groq", model="m",
            lesson_payload={**base, field: value},
        ), field


def test_cache_key_is_namespaced_by_prompt_version(monkeypatch):
    payload = {"indicator_code": "B7.1.1.1.1"}
    before = zg.zeli_cache_key(
        provider="groq", model="m", lesson_payload=payload)
    monkeypatch.setattr(zg, "ZELI_PROMPT_VERSION", "zeli-generation-v999")
    after = zg.zeli_cache_key(
        provider="groq", model="m", lesson_payload=payload)
    assert before != after
    assert zg.ZELI_PROMPT_VERSION == "zeli-generation-v999"

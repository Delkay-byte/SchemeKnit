"""
Phase 2 remediation tests: editable + AI-suggestible Main Learning, teacher-safe
AI failure UX, and no AI quota consumed on failure (PART AC).

MAIN LEARNING
  1. edit main_activities
  2. add activity
  3. remove activity
  4. change duration
  5. save/reload round trip
  6. AI structured main_learning -> main_activities mapping
  7. successful AI replacement
  8. AI failure preserves the existing activities

AI FAILURE UX SUPPORT
  9.  429/rate-limit  -> user-safe failure contract
  10. 503 unavailable -> user-safe failure contract
  11. malformed JSON  -> user-safe failure contract
  12. empty output    -> user-safe failure contract
  13. no AI quota consumed on failure
"""
import os
import sys

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routers import ai_regeneration as air
from src.routers.ai_regeneration import _normalize_main_activities


# ── PART AC 6: provider payload -> canonical structured activities ───────────

class TestNormalizeMainActivities:
    def test_v2_phase_object_is_structured_not_flattened(self):
        res = {"main_learning": {
            "phase1": {"name": "Explore", "activity": "Sort counters into sets.",
                       "duration_minutes": 12, "resources_used": ["counters"]},
            "phase2": {"name": "Practice", "activity": "Match numbers to sets.",
                       "duration_minutes": 15},
        }}
        out = _normalize_main_activities(res)
        assert out[0]["description"] == "Sort counters into sets."
        assert out[0]["duration_minutes"] == 12
        assert out[0]["resources"] == ["counters"]
        assert out[1]["phase"] == "PRACTICE"

    def test_list_form_is_supported(self):
        res = {"main_learning": [
            {"activity": "First task", "duration_minutes": 5},
            {"description": "Second task", "duration_minutes": 10},
        ]}
        out = _normalize_main_activities(res)
        assert [a["description"] for a in out] == ["First task", "Second task"]

    def test_bare_string_is_supported(self):
        out = _normalize_main_activities({"main_learning": "Do the thing."})
        assert out == [{"phase": "MAIN", "description": "Do the thing.",
                        "duration_minutes": None, "resources": []}]

    def test_legacy_main_activities_key_is_supported(self):
        res = {"main_activities": [{"description": "Legacy task"}]}
        assert _normalize_main_activities(res)[0]["description"] == "Legacy task"

    def test_empty_payload_returns_empty(self):
        assert _normalize_main_activities({}) == []
        assert _normalize_main_activities(None) == []
        assert _normalize_main_activities({"main_learning": {}}) == []

    def test_blank_descriptions_are_dropped(self):
        res = {"main_learning": {"p1": {"activity": "   "},
                                 "p2": {"activity": "Real activity"}}}
        out = _normalize_main_activities(res)
        assert [a["description"] for a in out] == ["Real activity"]

    def test_out_of_range_duration_is_dropped_not_written(self):
        res = {"main_learning": {"p1": {"activity": "Task", "duration_minutes": 0}}}
        assert _normalize_main_activities(res)[0]["duration_minutes"] is None
        res = {"main_learning": {"p1": {"activity": "Task", "duration_minutes": 999}}}
        assert _normalize_main_activities(res)[0]["duration_minutes"] is None


def _objective_service():
    from src.service import data_service
    return data_service


class _LessonMixin:
    def _lesson(self, db, owner_id, **cols):
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        scheme = SchemeDB(id=generate_id(), owner_id=owner_id, filename="s.docx",
                          subject="Numeracy", class_level="KG 1")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=owner_id,
                              scheme_id=scheme.id, status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(
            id=generate_id(), job_id=job.id, owner_id=owner_id, scheme_id=scheme.id,
            week_number=1, lesson_sequence=1, class_level="KG 1", subject="Numeracy",
            main_activities=[{"phase": "MAIN", "description": "Original activity",
                              "duration_minutes": 10, "resources": []}],
            assessment="Original assessment", strand="Counting",
            **cols)
        db.add(lp)
        db.commit()
        db.refresh(lp)
        return lp

    def _entitled_free_user(self, db, email):
        """A free-tier user with a monthly AI allowance (ai_credits>0)."""
        from tests.conftest import make_user
        from src.database import EntitlementDB, generate_id
        u = make_user(db, role="teacher", school_id=None, email=email)
        db.add(EntitlementDB(id=generate_id(), user_id=u.id, edition="free",
                             ai_enabled=True, ai_credits=5, generation_limit=5))
        db.commit()
        return u


# ── PART AC 1-5: manual edit / add / remove / duration / round trip ──────────

class TestMainLearningPersistence(_LessonMixin):
    def test_edit_save_reload_returns_exact_activities(self, db):
        from tests.conftest import make_user
        from src.routers.generation import _serialize_lesson
        u = make_user(db, role="teacher", email="ml-persist@t.test")
        lp = self._lesson(db, u.id)

        edited = [
            {"phase": "MAIN", "description": "Activity one", "duration_minutes": 12,
             "resources": []},
            {"phase": "MAIN", "description": "Activity two", "duration_minutes": 15,
             "resources": []},
        ]
        updated = _objective_service().update_lesson_plan(
            db, lp.id, u.id, {"main_activities": edited})
        got = _serialize_lesson(updated)["main_activities"]
        assert [a["description"] for a in got] == ["Activity one", "Activity two"]
        assert got[0]["duration_minutes"] == 12

        # Add a third, change a duration, remove the second (PART AC 2-4).
        edited = [edited[0], edited[1],
                  {"phase": "MAIN", "description": "Activity three",
                   "duration_minutes": 8, "resources": []}]
        edited[0]["duration_minutes"] = 20
        del edited[1]
        updated = _objective_service().update_lesson_plan(
            db, lp.id, u.id, {"main_activities": edited})
        got = _serialize_lesson(updated)["main_activities"]
        assert [a["description"] for a in got] == ["Activity one", "Activity three"]
        assert got[0]["duration_minutes"] == 20

    def test_editing_main_learning_leaves_every_other_field_untouched(self, db):
        """PART Z: a Main Learning edit must not modify assessment, strand, etc."""
        from tests.conftest import make_user
        u = make_user(db, role="teacher", email="ml-isolation@t.test")
        lp = self._lesson(db, u.id)
        _objective_service().update_lesson_plan(db, lp.id, u.id, {
            "main_activities": [{"phase": "MAIN", "description": "Only this",
                                 "duration_minutes": 7, "resources": []}],
        })
        db.refresh(lp)
        assert lp.assessment == "Original assessment"
        assert lp.strand == "Counting"

    def test_edit_does_not_touch_another_lesson(self, db):
        """PART Z: Lesson 1's Main Learning edit never modifies Lesson 2."""
        from tests.conftest import make_user
        from src.routers.generation import _serialize_lesson
        u = make_user(db, role="teacher", email="ml-cross@t.test")
        lp1 = self._lesson(db, u.id)
        lp2 = self._lesson(db, u.id)
        _objective_service().update_lesson_plan(db, lp1.id, u.id, {
            "main_activities": [{"phase": "MAIN", "description": "Changed L1",
                                 "duration_minutes": 3, "resources": []}],
        })
        db.refresh(lp1)
        db.refresh(lp2)
        assert _serialize_lesson(lp1)["main_activities"][0]["description"] == "Changed L1"
        assert _serialize_lesson(lp2)["main_activities"][0]["description"] == "Original activity"


# ── PART AC 7-13: AI suggestion + teacher-safe failure contract ──────────────

class TestMainLearningAI(_LessonMixin):
    def _provider(self, payload, name="gemini", last_error=None):
        p = MagicMock()
        p.get_name.return_value = name
        p.model = "test-model"
        p.last_error = last_error
        p.is_available.return_value = True
        p.generate_lesson_content.return_value = payload
        return p

    @pytest.mark.asyncio
    async def test_successful_ai_main_learning_is_structured(self, db):
        """PART AC 6/7: a valid provider response becomes structured activities
        and the successful generation consumes exactly one AI unit."""
        from src.ai_quota import get_ai_units_used
        u = self._entitled_free_user(db, "ml-ai-ok@t.test")
        lp = self._lesson(db, u.id)
        provider = self._provider({"main_learning": {
            "phase1": {"name": "Explore", "activity": "Sort shapes by colour.",
                       "duration_minutes": 12},
        }})
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="main_activities",
                    ai_mode="gemini"),
                u, db)
        assert res.new_activities and res.new_activities[0]["description"] == "Sort shapes by colour."
        assert res.new_activities[0]["duration_minutes"] == 12
        assert res.new_content == "Sort shapes by colour."
        assert get_ai_units_used(db, u.id) == 1
        # The lesson row itself is NOT written by a section regeneration.
        db.refresh(lp)
        assert lp.main_activities[0]["description"] == "Original activity"

    @pytest.mark.asyncio
    async def test_empty_ai_output_preserves_activities_and_consumes_nothing(self, db):
        """PART AC 8/12/13."""
        from src.ai_quota import get_ai_units_used
        u = self._entitled_free_user(db, "ml-ai-empty@t.test")
        lp = self._lesson(db, u.id)
        provider = self._provider({})
        with patch.object(air, "get_provider", return_value=provider):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="main_activities",
                        ai_mode="gemini"),
                    u, db)
        assert e.value.status_code == 502
        assert _code(e.value) == "AI_NO_SUGGESTION"
        assert get_ai_units_used(db, u.id) == 0
        db.refresh(lp)
        assert lp.main_activities[0]["description"] == "Original activity"

    @pytest.mark.asyncio
    async def test_rate_limit_is_teacher_safe(self, db):
        """PART AC 9: 429/rate-limit maps to the user-safe contract."""
        from src.ai_quota import get_ai_units_used
        u = self._entitled_free_user(db, "ml-ai-429@t.test")
        lp = self._lesson(db, u.id)
        provider = self._provider({}, last_error="rate_limit")
        with patch.object(air, "get_provider", return_value=provider):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="main_activities",
                        ai_mode="gemini"),
                    u, db)
        assert e.value.status_code == 502
        assert _code(e.value) == "AI_RATE_LIMITED"
        assert get_ai_units_used(db, u.id) == 0

    @pytest.mark.asyncio
    async def test_malformed_json_is_teacher_safe(self, db):
        """PART AC 11."""
        u = self._entitled_free_user(db, "ml-ai-malformed@t.test")
        lp = self._lesson(db, u.id)
        provider = self._provider({}, last_error="malformed_json")
        with patch.object(air, "get_provider", return_value=provider):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="main_activities",
                        ai_mode="gemini"),
                    u, db)
        assert _code(e.value) == "AI_NO_SUGGESTION"

    @pytest.mark.asyncio
    async def test_unavailable_provider_is_teacher_safe(self, db):
        """PART AC 10: 503 provider unavailable -> user-safe contract, and the
        raw provider state stays only in the diagnostic field."""
        from src.ai_quota import get_ai_units_used
        u = self._entitled_free_user(db, "ml-ai-503@t.test")
        lp = self._lesson(db, u.id)
        with patch.object(air, "get_provider", return_value=None):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="main_activities",
                        ai_mode="gemini"),
                    u, db)
        assert e.value.status_code == 503
        assert _code(e.value) == "AI_UNAVAILABLE"
        assert get_ai_units_used(db, u.id) == 0
        db.refresh(lp)
        assert lp.main_activities[0]["description"] == "Original activity"


def _code(exc: HTTPException) -> str:
    detail = exc.detail
    assert isinstance(detail, dict), f"expected structured detail, got {detail!r}"
    return detail["code"]


class TestTeacherFacingMessageContract:
    """PART H/J/AD: no internal provider diagnostic may be the teacher message."""

    def _detail(self, exc):
        return exc.detail

    def test_safe_message_never_contains_internal_tokens(self):
        u = MagicMock()
        for code, msg in [
            ("AI_UNAVAILABLE",
             "AI suggestion is currently unavailable. Your existing content was preserved."),
            ("AI_RATE_LIMITED",
             "AI is busy right now. Your existing content was preserved. "
             "Please try again in a moment, or edit it manually."),
            ("AI_NO_SUGGESTION",
             "AI suggestion unavailable right now. Your existing content was "
             "preserved. You can edit it manually or try again later."),
        ]:
            lowered = msg.lower()
            assert "live_error" not in lowered
            assert "provider returned no usable content" not in lowered
            assert "http" not in lowered
            assert "exception" not in lowered

    def test_structured_error_keeps_raw_diagnostic_out_of_message(self):
        exc = air._ai_error(
            502, "AI_NO_SUGGESTION",
            "AI suggestion unavailable right now. Your existing content was preserved.",
            diagnostic="AI provider 'gemini' returned no usable content "
                       "(state: LIVE_ERROR).",
        )
        assert exc.detail["code"] == "AI_NO_SUGGESTION"
        assert "LIVE_ERROR" not in exc.detail["message"]
        assert "LIVE_ERROR" in exc.detail["diagnostic"]

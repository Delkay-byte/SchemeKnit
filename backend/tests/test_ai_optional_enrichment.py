"""
PART 19/20 — Gemini is OPTIONAL enrichment, never the source of a lesson.

The contract these tests defend, for EVERY suggestible section (starter, main
learning, assessment, reflection):

  * when the provider succeeds, the section is enriched and exactly one AI
    generation is consumed;
  * when the provider fails — unavailable, empty, malformed, rate-limited — the
    deterministic content the teacher already has is left untouched, the
    response is a teacher-safe message with no provider diagnostics, and ZERO
    AI generations are consumed.

That last point is what makes AI genuinely optional: a provider outage costs the
teacher nothing and the lesson stays classroom-usable.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routers import ai_regeneration as air  # noqa: E402

#: (requested section, the lesson column it would replace, provider payload key)
SECTION_CASES = [
    ("introduction", "introduction", "starter"),
    ("main_activities", "main_activities", "main_learning"),
    ("assessment", "assessment", "assessment"),
    ("conclusion", "conclusion", "plenary"),
]


def _code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return detail.get("code", "")
    return ""


def _provider(payload, *, name="gemini", last_error=None, available=True):
    p = MagicMock()
    p.get_name.return_value = name
    p.model = "test-model"
    p.last_error = last_error
    p.is_available.return_value = available
    p.generate_lesson_content.return_value = payload
    return p


class _Mixin:
    def _lesson(self, db, owner_id, **cols):
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id

        scheme = SchemeDB(id=generate_id(), owner_id=owner_id, filename="s.docx",
                          subject="ICT", class_level="Basic 7")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=owner_id,
                              scheme_id=scheme.id, status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(
            id=generate_id(), job_id=job.id, owner_id=owner_id, scheme_id=scheme.id,
            week_number=1, lesson_sequence=1, class_level="Basic 7", subject="ICT",
            lesson_topic="Input devices",
            introduction="Deterministic starter: show a keyboard, a mouse and a "
                         "touchscreen, then ask which ones the class has used.",
            main_activities=[{"phase": "TEACHING AND DEMONSTRATION",
                              "description": "Deterministic main: demonstrate a "
                                             "keyboard and a barcode scanner.",
                              "duration_minutes": 10, "resources": []}],
            learner_activities=[{"phase": "GUIDED LEARNER TASK",
                                 "description": "Deterministic learner task.",
                                 "duration_minutes": 10, "resources": []}],
            assessment="Deterministic assessment: sort four device cards.",
            conclusion="Deterministic reflection: name one manual and one "
                       "automatic device.",
            **cols,
        )
        db.add(lp)
        db.commit()
        db.refresh(lp)
        return lp

    def _entitled_user(self, db, email):
        from src.database import EntitlementDB, generate_id
        from tests.conftest import make_user

        u = make_user(db, role="teacher", school_id=None, email=email)
        db.add(EntitlementDB(id=generate_id(), user_id=u.id, edition="free",
                             ai_enabled=True, ai_credits=5, generation_limit=5))
        db.commit()
        return u


class TestAiIsOptional(_Mixin):
    @pytest.mark.asyncio
    @pytest.mark.parametrize("section,column,key", SECTION_CASES)
    async def test_success_enriches_and_consumes_exactly_one(self, db, section,
                                                            column, key):
        from src.ai_quota import get_ai_units_used

        user = self._entitled_user(db, f"opt-ok-{section}@t.test")
        lp = self._lesson(db, user.id)
        provider = _provider({key: "Enriched by the provider."})
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section=section, ai_mode="gemini"),
                user, db)
        assert res.provider == "gemini"
        assert get_ai_units_used(db, user.id) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("section,column,key", SECTION_CASES)
    async def test_provider_failure_preserves_the_deterministic_lesson(
            self, db, section, column, key):
        from src.ai_quota import get_ai_units_used

        user = self._entitled_user(db, f"opt-fail-{section}@t.test")
        lp = self._lesson(db, user.id)
        before = {c: getattr(lp, c) for c in
                  ("introduction", "main_activities", "assessment", "conclusion")}

        provider = _provider({}, last_error="provider_unavailable", available=False)
        with patch.object(air, "get_provider", return_value=provider):
            with pytest.raises(HTTPException) as exc:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section=section, ai_mode="gemini"),
                    user, db)

        assert exc.value.status_code in (502, 503)
        message = str(exc.value.detail)
        # Teacher-safe: names the situation, promises the content survived.
        assert "AI" in message
        assert "preserved" in message.lower() or "unavailable" in message.lower()
        # No provider diagnostics leak to the teacher.
        for leak in ("Traceback", "api_key", "API key", "gemini-", "stack",
                     "Exception", "NoneType"):
            assert leak not in message, message
        # The deterministic lesson is byte-identical, in the database.
        db.refresh(lp)
        assert {c: getattr(lp, c) for c in before} == before
        # And the failure cost the teacher NOTHING.
        assert get_ai_units_used(db, user.id) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("section,column,key", SECTION_CASES)
    async def test_an_empty_provider_answer_is_never_a_lesson(
            self, db, section, column, key):
        from src.ai_quota import get_ai_units_used

        user = self._entitled_user(db, f"opt-empty-{section}@t.test")
        lp = self._lesson(db, user.id)
        provider = _provider({})
        with patch.object(air, "get_provider", return_value=provider):
            with pytest.raises(HTTPException) as exc:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section=section, ai_mode="gemini"),
                    user, db)
        assert _code(exc.value) == "AI_NO_SUGGESTION"
        assert get_ai_units_used(db, user.id) == 0

    @pytest.mark.asyncio
    async def test_ai_off_never_touches_the_lesson(self, db):
        from src.ai_quota import get_ai_units_used

        user = self._entitled_user(db, "opt-off@t.test")
        lp = self._lesson(db, user.id)
        before = lp.assessment
        with pytest.raises(HTTPException):
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="OFF"),
                user, db)
        db.refresh(lp)
        assert lp.assessment == before
        assert get_ai_units_used(db, user.id) == 0


class TestDeterministicLessonNeedsNoAi:
    """A generated lesson is already classroom-usable with the provider off."""

    def test_every_phase_and_both_assignments_exist_without_ai(self):
        from datetime import date

        from src.curriculum.lesson_builder import build_lesson
        from src.models import (AllocatedIndicator, AIMode, ClassLevel, Subject,
                                TermConfig)

        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=2, lesson_duration_minutes=60,
            teaching_days=[0, 2], holidays=[], ai_mode=AIMode.OFF,
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.2",
            indicator_description="B7.1.1.1.2",
            content_standard_code="B7.1.1.1",
            content_standard_description="B7.1.1.1",
            strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            week_number=1, source_resources=["Keyboard"],
            lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
            teaching_week=1,
        )
        lp = build_lesson(alloc, config, "s")
        assert lp.ai_generated is False
        assert lp.starter_activity and len(lp.starter_activity.split()) >= 12
        assert len(lp.main_activities) >= 3
        assert lp.assessment and len(lp.assessment.split()) >= 8
        assert lp.conclusion
        assert lp.class_assignment and lp.home_assignment
        assert lp.learning_objectives[0].description.startswith("Learners can ")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Backlog item 4 — enrichment cache read-path + double-submit guards.

The AI enrichment cache was write-only and the generate endpoint had no
in-flight guard: a double-click reserved a second quota and started a
competing run. These tests pin the fixes:

  * regenerate-section / enrich-lesson return the cached generation for an
    identical input (or a replayed request_id) without a second provider
    call and without a second quota consumption;
  * /generate 409s while a job for the scheme is still in flight;
  * scheme/status reports which occurrences already carry a lesson.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routers import ai_regeneration as air  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _provider(payload, *, name="gemini", available=True):
    p = MagicMock()
    p.get_name.return_value = name
    p.model = "test-model"
    p.last_error = None
    p.is_available.return_value = available
    p.generate_lesson_content.return_value = payload
    p.generate_structured.return_value = payload
    return p


def _lesson(db, owner_id):
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
        introduction="Deterministic starter: show a keyboard.",
        main_activities=[{"phase": "TEACHING", "description": "Deterministic main.",
                          "duration_minutes": 10, "resources": []}],
        learner_activities=[{"phase": "LEARNER", "description": "Practice.",
                             "duration_minutes": 10, "resources": []}],
        assessment="Sort four device cards.",
        conclusion="Name one manual and one automatic device.",
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return lp


def _entitled_user(db, email):
    from src.database import EntitlementDB, generate_id

    u = make_user(db, role="teacher", school_id=None, email=email)
    db.add(EntitlementDB(id=generate_id(), user_id=u.id, edition="free",
                         ai_enabled=True, ai_credits=5, generation_limit=5))
    db.commit()
    return u


class TestRegenerateCache:
    @pytest.mark.asyncio
    async def test_identical_input_hits_cache_and_skips_provider(self, db):
        from src.ai_quota import get_ai_units_used

        user = _entitled_user(db, "cache-a@t.test")
        lp = _lesson(db, user.id)
        original = lp.introduction
        provider = _provider({"starter": "Enriched starter."})
        with patch.object(air, "get_provider", return_value=provider):
            first = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini"),
                user, db)
            # A concurrent duplicate (or any resubmit that still sees the
            # SAME pre-generation input) must resolve to the cache row.
            lp.introduction = original
            db.commit()
            provider.generate_lesson_content.reset_mock()
            second = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini"),
                user, db)
        assert first.already_generated is False
        assert second.already_generated is True
        assert second.new_content == "Enriched starter."
        provider.generate_lesson_content.assert_not_called()
        # ONE provider success = ONE AI generation, not two.
        assert get_ai_units_used(db, user.id) == 1

    @pytest.mark.asyncio
    async def test_request_id_replay_returns_without_second_consumption(
            self, db):
        from src.ai_quota import get_ai_units_used

        user = _entitled_user(db, "cache-b@t.test")
        lp = _lesson(db, user.id)
        provider = _provider({"starter": "Enriched starter."})
        with patch.object(air, "get_provider", return_value=provider):
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini", request_id="dup-1"),
                user, db)
            provider.generate_lesson_content.reset_mock()
            replay = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini", request_id="dup-1"),
                user, db)
        assert replay.already_generated is True
        provider.generate_lesson_content.assert_not_called()
        assert get_ai_units_used(db, user.id) == 1

    @pytest.mark.asyncio
    async def test_changed_input_misses_cache_and_regenerates(self, db):
        from src.ai_quota import get_ai_units_used

        user = _entitled_user(db, "cache-c@t.test")
        lp = _lesson(db, user.id)
        provider = _provider({"starter": "Enriched A."},
                             name="gemini")
        with patch.object(air, "get_provider", return_value=provider):
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini"),
                user, db)
            # A teacher edit changes the section content → new input hash →
            # the cache must miss and a genuine regeneration must happen.
            lp.introduction = "Teacher rewrote this starter by hand."
            db.commit()
            provider.generate_lesson_content.return_value = {"starter": "Enriched B."}
            provider.generate_lesson_content.reset_mock()
            second = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="introduction",
                    ai_mode="gemini"),
                user, db)
        assert second.already_generated is False
        provider.generate_lesson_content.assert_called_once()
        assert get_ai_units_used(db, user.id) == 2


class TestGenerateDoubleSubmit:
    def _scheme(self, db, owner_id):
        from src.database import SchemeDB, WeekDB, generate_id

        scheme = SchemeDB(id=generate_id(), owner_id=owner_id,
                          filename="s.docx", subject="ICT",
                          class_level="Basic 7")
        db.add(scheme)
        db.flush()
        for n in (1, 2, 3):
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

    def _app(self, db, user):
        from fastapi import FastAPI
        from src.auth import get_current_user, require_teacher_workflow
        from src.database import get_db
        from src.routers import generation as gen_router

        app = FastAPI()
        app.include_router(gen_router.router, prefix="/api/generation")
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[require_teacher_workflow] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        return app

    def _config(self, scheme_id):
        from src.models import TermConfig

        return TermConfig(
            scheme_of_work_id=scheme_id,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
            teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
            include_special_weeks=False, class_level="Basic 7", subject="ICT",
        )

    def test_inflight_job_blocks_a_second_generate(self, db):
        from fastapi.testclient import TestClient
        from src.database import GenerationJobDB, generate_id

        user = make_user(db)
        scheme = self._scheme(db, user.id)
        # A sibling run is still processing.
        db.add(GenerationJobDB(id=generate_id(), owner_id=user.id,
                               scheme_id=scheme.id, status="processing"))
        db.commit()

        with TestClient(self._app(db, user)) as client:
            resp = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=self._config(scheme.id).model_dump(mode="json"),
            )
        assert resp.status_code == 409, resp.text
        assert "already running" in resp.text.lower()

    def test_scheme_status_reports_already_generated_occurrences(self, db):
        from fastapi.testclient import TestClient
        from src.database import (
            GenerationJobDB, LessonPlanDB, generate_id,
        )

        user = make_user(db)
        scheme = self._scheme(db, user.id)
        job = GenerationJobDB(id=generate_id(), owner_id=user.id,
                              scheme_id=scheme.id, status="completed")
        db.add(job)
        db.commit()
        for occ in ("week1:0:B7.1.1.1.1", "week2:0:B7.1.1.2.1"):
            db.add(LessonPlanDB(
                id=generate_id(), job_id=job.id, owner_id=user.id,
                scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                class_level="Basic 7", subject="ICT",
                source_occurrence_id=occ, indicator_codes=[occ.split(":")[-1]],
            ))
        db.commit()

        with TestClient(self._app(db, user)) as client:
            resp = client.get(
                f"/api/generation/scheme/{scheme.id}/status")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["already_generated_occurrence_ids"] == [
            "week1:0:B7.1.1.1.1", "week2:0:B7.1.1.2.1",
        ]

    def test_generate_response_carries_already_generated_info(self, db):
        from fastapi.testclient import TestClient
        from src.database import (
            GenerationJobDB, LessonPlanDB, generate_id,
        )

        user = make_user(db)
        scheme = self._scheme(db, user.id)
        job = GenerationJobDB(id=generate_id(), owner_id=user.id,
                              scheme_id=scheme.id, status="completed")
        db.add(job)
        db.commit()
        db.add(LessonPlanDB(
            id=generate_id(), job_id=job.id, owner_id=user.id,
            scheme_id=scheme.id, week_number=1, lesson_sequence=1,
            class_level="Basic 7", subject="ICT",
            source_occurrence_id="week1:0:B7.1.1.1.1",
            indicator_codes=["B7.1.1.1.1"],
        ))
        db.commit()

        config = self._config(scheme.id)
        config.selected_occurrence_ids = ["week1:0:B7.1.1.1.1"]
        with TestClient(self._app(db, user)) as client:
            resp = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["already_generated_occurrence_ids"] == [
            "week1:0:B7.1.1.1.1",
        ]

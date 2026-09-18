"""
AI production tests: payload robustness, failure contracts, secret safety,
deterministic-off behavior.
"""

import os
import sys

import pytest
from fastapi import HTTPException
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.routers.ai_regeneration import _flatten_text, _extract_section_text
from src.engines.ai_provider import _strip_fences, get_provider


class TestPayloadRobustness:
    def test_strip_fences(self):
        assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
        assert _strip_fences('{"a": 1}') == '{"a": 1}'
        assert _strip_fences('') == ''

    def test_flatten_dict_fragment(self):
        out = _flatten_text({"title": "T", "description": "D"})
        assert "T" in out and "D" in out

    def test_flatten_strips_fences(self):
        out = _flatten_text('```json\n{"x": 1}\n```')
        assert "```" not in out

    def test_extract_nested_lesson_content(self):
        res = {"lesson_content": {"assessment": "Do X now."}}
        assert _extract_section_text(res, "assessment") == "Do X now."

    def test_extract_falls_back_to_introduction(self):
        res = {"introduction": "Welcome."}
        assert _extract_section_text(res, "assessment") == "Welcome."

    def test_extract_empty(self):
        assert _extract_section_text({}, "assessment") == ""
        assert _extract_section_text(None, "assessment") == ""


class TestFailureContracts:
    @pytest.mark.asyncio
    async def test_unavailable_provider_503(self, db):
        from tests.conftest import make_entitled_teacher
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        u, _school, _lic = make_entitled_teacher(db, email="ai503@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          assessment="Old assessment text here.")
        db.add(lp)
        db.commit()
        with patch.object(air, "get_provider") as gp:
            gp.return_value = None
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                    u, db)
        assert e.value.status_code == 503
        # previous content preserved
        db.refresh(lp)
        assert lp.assessment == "Old assessment text here."

    @pytest.mark.asyncio
    async def test_empty_result_retries_once_then_succeeds(self, db):
        from tests.conftest import make_entitled_teacher
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        from unittest.mock import MagicMock
        u, _school, _lic = make_entitled_teacher(db, email="airetry@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          assessment="Old text here.")
        db.add(lp)
        db.commit()
        provider = MagicMock()
        provider.get_name.return_value = "ollama"
        provider.model = "test-model"
        provider.generate_lesson_content.side_effect = [
            {}, {"assessment": "Retried content wins."},
        ]
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                u, db)
        assert res.new_content == "Retried content wins."
        assert provider.generate_lesson_content.call_count == 2

    @pytest.mark.asyncio
    async def test_bad_section_400(self, db):
        from tests.conftest import make_user
        from src.routers import ai_regeneration as air
        u = make_user(db, role="teacher", email="ai400@t.test")
        with pytest.raises(HTTPException) as e:
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id="x", section="nope", ai_mode="ollama"),
                u, db)
        assert e.value.status_code == 400

    @pytest.mark.asyncio
    async def test_cross_owner_lesson_404(self, db):
        from tests.conftest import make_user
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        a = make_user(db, role="teacher", email="a404@t.test")
        b = make_user(db, role="teacher", email="b404@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=b.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=b.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=b.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science")
        db.add(lp)
        db.commit()
        with pytest.raises(HTTPException) as e:
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                a, db)
        assert e.value.status_code == 404


class TestEntitlement:
    def _setup(self, db, school_status="active", expiry=None, school_id="SET"):
        from tests.conftest import make_user, make_school, make_product_plan, make_license
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        from datetime import date
        school = make_school(db)
        plan = make_product_plan(db)
        lic = make_license(db, school.id, plan.id)
        lic.status = school_status
        lic.expiry_date = expiry or (date.today().replace(year=date.today().year + 1))
        db.commit()
        u = make_user(db, role="teacher", school_id=school.id,
                      email=f"ent-{school_status}-{generate_id()[:6]}@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, school_id=school.id,
                          filename="s.docx", subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          assessment="Old assessment text here.")
        db.add(lp)
        db.commit()
        return u, lp

    @pytest.mark.asyncio
    async def test_active_license_allowed(self, db):
        from src.routers import ai_regeneration as air
        from unittest.mock import MagicMock
        u, lp = self._setup(db, "active")
        provider = MagicMock()
        provider.get_name.return_value = "ollama"
        provider.model = "test"
        provider.generate_lesson_content.return_value = {
            "assessment": "Fresh AI assessment content here."}
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                u, db)
        assert res.new_content == "Fresh AI assessment content here."

    @pytest.mark.asyncio
    async def test_suspended_license_blocked(self, db):
        from src.routers import ai_regeneration as air
        u, lp = self._setup(db, "suspended")
        with pytest.raises(HTTPException) as e:
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                u, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_license_blocked(self, db):
        from datetime import date, timedelta
        from src.routers import ai_regeneration as air
        u, lp = self._setup(db, "active", expiry=date.today() - timedelta(days=1))
        with pytest.raises(HTTPException) as e:
            await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                u, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_school_membership_blocked(self, db):
        """Free tier: the lesson workflow is free, AI is not. An installed
        provider must not grant access on its own."""
        from tests.conftest import make_user
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        from unittest.mock import MagicMock
        u = make_user(db, role="teacher", school_id=None, email="free-ai@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          assessment="Old assessment text here.")
        db.add(lp)
        db.commit()
        provider = MagicMock()
        provider.is_available.return_value = True
        provider.get_name.return_value = "ollama"
        provider.model = "test"
        with patch.object(air, "get_provider", return_value=provider) as gp:
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                    u, db)
        assert e.value.status_code == 403
        # Entitlement is decided before any provider is constructed, so an
        # installed local provider can never be reached without entitlement.
        assert gp.call_count == 0
        db.refresh(lp)
        assert lp.assessment == "Old assessment text here."

    @pytest.mark.asyncio
    async def test_paid_entitlement_allows_without_school(self, db):
        """A paid AI entitlement row is an alternative route to AI."""
        from tests.conftest import make_user, make_paid_entitlement
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        from unittest.mock import MagicMock
        u = make_user(db, role="teacher", school_id=None, email="paid-ai@t.test")
        make_paid_entitlement(db, u.id)
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science")
        db.add(lp)
        db.commit()
        provider = MagicMock()
        provider.get_name.return_value = "ollama"
        provider.model = "test"
        provider.generate_lesson_content.return_value = {
            "assessment": "Paid entitlement content."}
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="assessment", ai_mode="ollama"),
                u, db)
        assert res.new_content == "Paid entitlement content."

    @pytest.mark.asyncio
    async def test_expired_paid_entitlement_blocked(self, db):
        from datetime import datetime, timedelta
        from tests.conftest import make_user, make_paid_entitlement
        from src.entitlements import ai_entitlement, AI_ENTITLEMENT_REQUIRED
        u = make_user(db, role="teacher", school_id=None, email="paid-exp@t.test")
        make_paid_entitlement(db, u.id,
                              expires_at=datetime.utcnow() - timedelta(days=1))
        entitled, reason = ai_entitlement(u, db)
        assert entitled is False and reason == "no_entitlement"
        with pytest.raises(HTTPException) as e:
            from src.entitlements import require_ai_entitlement
            require_ai_entitlement(u, db)
        assert e.value.status_code == 403
        assert AI_ENTITLEMENT_REQUIRED == e.value.detail


class TestGenerationEntitlement:
    """AI at generation time must be gated before any provider is reached.

    AI OFF has to keep working for everyone: entitlement gates AI, never the
    deterministic lesson plan.
    """

    def _term_config(self, ai_mode):
        from src.models import (
            AIMode, ClassLevel, Subject, TemplateType, TermConfig,
        )
        return TermConfig(
            scheme_of_work_id="s", term_start_date="2026-09-11",
            term_end_date="2026-12-18", lessons_per_week=1,
            lesson_duration_minutes=60, class_size=11, teaching_days=[0],
            holidays=[], ai_mode=ai_mode, template_type=TemplateType.GES_STYLE,
            include_special_weeks=False, subject=Subject.SCIENCE,
            class_level=ClassLevel.BASIC_9, school_name="S", teacher_name="T",
        )

    @pytest.mark.asyncio
    async def test_ai_mode_without_entitlement_is_403(self, db):
        from src.models import AIMode
        from tests.conftest import make_user
        from src.routers import generation as gen
        from src.database import SchemeDB, generate_id
        u = make_user(db, role="teacher", school_id=None, email="gen-free@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        with pytest.raises(HTTPException) as e:
            await gen.generate_lesson_plans(
                scheme.id, self._term_config(AIMode.BASIC), u, db)
        assert e.value.status_code == 403
        assert "active school license or a paid AI entitlement" in e.value.detail

    @pytest.mark.asyncio
    async def test_ai_off_still_generates_for_free_tier(self, db):
        """AI OFF must never be blocked by the AI commercial gate."""
        from src.models import AIMode
        from src.routers import generation as gen
        from src.entitlements import ai_entitlement
        from tests.conftest import make_user
        from src.database import SchemeDB, generate_id
        u = make_user(db, role="teacher", school_id=None, email="gen-off@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()

        # The teacher is genuinely NOT entitled to AI...
        assert ai_entitlement(u, db) == (False, "no_entitlement")

        # ...yet AI OFF never consults the entitlement gate at all.
        with patch.object(gen, "require_ai_entitlement") as gate:
            try:
                await gen.generate_lesson_plans(
                    scheme.id, self._term_config(AIMode.OFF), u, db)
            except HTTPException as e:
                # Deterministic generation may fail for unrelated reasons on an
                # empty scheme; what matters is that the AI gate was not it.
                assert e.status_code != 403
        assert gate.call_count == 0

    @pytest.mark.asyncio
    async def test_ai_mode_with_active_license_passes_the_gate(self, db):
        from src.models import AIMode
        from tests.conftest import make_entitled_teacher
        from src.routers import generation as gen
        from src.database import SchemeDB, generate_id
        u, _school, _lic = make_entitled_teacher(db, email="gen-ok@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, school_id=u.school_id,
                          filename="s.docx", subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        with patch.object(gen, "require_ai_entitlement") as gate:
            try:
                await gen.generate_lesson_plans(
                    scheme.id, self._term_config(AIMode.BASIC), u, db)
            except HTTPException:
                pass
        assert gate.call_count == 1


class TestEntitlementReasons:
    """The gate must distinguish *why* AI was denied, for operators."""

    def test_reason_matrix(self, db):
        from datetime import date, timedelta
        from tests.conftest import (
            make_user, make_school, make_product_plan, make_license,
        )
        from src.entitlements import ai_entitlement

        # no school, no entitlement
        free = make_user(db, role="teacher", email="ent-free@t.test")
        assert ai_entitlement(free, db) == (False, "no_entitlement")

        # school, no license row
        bare_school = make_school(db, name="Bare")
        bare = make_user(db, role="teacher", school_id=bare_school.id,
                         email="ent-bare@t.test")
        assert ai_entitlement(bare, db) == (False, "no_active_license")

        # school, suspended license
        suspended_school = make_school(db, name="Suspended")
        sp = make_product_plan(db)
        make_license(db, suspended_school.id, sp.id, status="suspended")
        sus = make_user(db, role="teacher", school_id=suspended_school.id,
                        email="ent-sus@t.test")
        assert ai_entitlement(sus, db) == (False, "no_active_license")

        # school, active license
        ok_school = make_school(db, name="OK")
        op = make_product_plan(db)
        make_license(db, ok_school.id, op.id, status="active")
        ok = make_user(db, role="teacher", school_id=ok_school.id,
                       email="ent-ok@t.test")
        assert ai_entitlement(ok, db) == (True, "school_license")

        # school, active-but-lapsed license
        old_school = make_school(db, name="Old")
        lp2 = make_product_plan(db)
        old = make_license(db, old_school.id, lp2.id, status="active")
        old.expiry_date = date.today() - timedelta(days=1)
        db.commit()
        ou = make_user(db, role="teacher", school_id=old_school.id,
                       email="ent-old@t.test")
        assert ai_entitlement(ou, db) == (False, "license_expired")


class TestSecretSafety:
    def test_no_keys_in_frontend_bundle_surface(self):
        # Provider secrets live server-side (env); the API client sends none.
        import re
        api = open(os.path.join(os.path.dirname(__file__), "..", "..",
                                "frontend", "src", "lib", "api.ts")).read()
        assert "GEMINI_API_KEY" not in api
        assert "OPENAI_API_KEY" not in api
        assert "OLLAMA_MODEL" not in api

    def test_mock_modes_need_no_provider(self):
        for mode in ("OFF", "BASIC", "ENHANCED"):
            p = get_provider(mode)
            assert p.get_name() == "mock"

    def test_ollama_reads_env_not_frontend(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "test-model-xyz"}):
            from src.engines.ai_provider import OllamaProvider
            assert OllamaProvider().model == "test-model-xyz"


class TestEnrichLessonEntitlement:
    """Item 13: enrich-lesson must enforce commercial entitlement server-side,
    before any provider is constructed — an installed Ollama never bypasses it."""

    @staticmethod
    def _make_lesson(db, u):
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          strand="Diversity of Matter",
                          introduction="Deterministic starter.",
                          main_activities='[{"phase": "MAIN", "description": "Present binary compounds."}]')
        db.add(lp)
        db.commit()
        return lp

    @pytest.mark.asyncio
    async def test_no_school_membership_blocked_before_provider(self, db):
        from unittest.mock import MagicMock

        from src.database import generate_id
        from src.routers import ai_regeneration as air

        from tests.conftest import make_user

        u = make_user(db, role="teacher", school_id=None, email="enrich-free@t.test")
        lp = self._make_lesson(db, u)
        provider = MagicMock()
        provider.is_available.return_value = True  # Ollama IS installed & reachable
        with patch.object(air, "get_provider", return_value=provider) as gp:
            with pytest.raises(HTTPException) as e:
                await air.enrich_lesson(
                    air.EnrichLessonRequest(lesson_plan_id=lp.id, ai_mode="ollama"),
                    u, db)
        assert e.value.status_code == 403
        assert gp.call_count == 0  # provider never constructed/reached
        db.refresh(lp)
        assert lp.introduction == "Deterministic starter."  # untouched

    @pytest.mark.asyncio
    async def test_suspended_license_blocked(self, db):
        from src.routers import ai_regeneration as air

        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, license_status="suspended",
                                                 email="enrich-susp@t.test")
        lp = self._make_lesson(db, u)
        with pytest.raises(HTTPException) as e:
            await air.enrich_lesson(
                air.EnrichLessonRequest(lesson_plan_id=lp.id, ai_mode="ollama"),
                u, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_expired_license_blocked(self, db):
        from datetime import date, timedelta

        from src.routers import ai_regeneration as air

        from tests.conftest import make_entitled_teacher

        u, _school, lic = make_entitled_teacher(db, license_status="active",
                                                email="enrich-exp@t.test")
        lic.expiry_date = date.today() - timedelta(days=1)
        db.commit()
        lp = self._make_lesson(db, u)
        with pytest.raises(HTTPException) as e:
            await air.enrich_lesson(
                air.EnrichLessonRequest(lesson_plan_id=lp.id, ai_mode="ollama"),
                u, db)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_active_license_enriches_structured_fields(self, db):
        """Happy path: structured response merged, curriculum columns untouched."""
        import json as _json
        from unittest.mock import MagicMock

        from src.routers import ai_regeneration as air

        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, email="enrich-ok@t.test")
        lp = self._make_lesson(db, u)
        provider = MagicMock()
        provider.get_name.return_value = "ollama"
        provider.model = "test"
        provider.generate_structured.return_value = {
            "phases": [
                {"name": "PHASE 1: STARTER", "teacher_activities": ["Ask learners to name compounds around them."],
                 "learner_activities": ["Discuss in pairs."], "resources": []},
            ],
            "assessment": ["Oral questions on binary compounds."],
            "reflection": "Recall uses of acids and bases.",
            # Curriculum overwrite attempts — must be ignored:
            "strand": "INVENTED STRAND", "indicators": ["B9.9.9.9.9"],
        }
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.enrich_lesson(
                air.EnrichLessonRequest(lesson_plan_id=lp.id, ai_mode="ollama"),
                u, db)
        assert res["written"]
        db.refresh(lp)
        # Activity-family columns received the structured AI content…
        assert "name compounds around them" in str(lp.teacher_activities)
        assert "Discuss in pairs." in str(lp.learner_activities)
        assert "Oral questions" in (lp.assessment or "")
        # …while curriculum columns are untouched by the same payload.
        assert lp.strand == "Diversity of Matter"       # unchanged
        assert "B9.9.9.9.9" not in str(lp.indicators)   # unchanged
        assert lp.introduction == "Deterministic starter."

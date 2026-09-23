"""
Final web UX milestone — security-critical behaviours (PART 14/15/27/28/32).

Two properties had no direct coverage, and both are load-bearing for the
milestone's security claims:

  1. Server-derived identity. School and teacher names on a generated plan come
     from the authenticated user's real school relationship and profile, never
     from the request body. A client must not be able to generate another
     school's plan or impersonate a teacher by submitting a crafted config.

  2. One-time authenticated download URLs. The token path is what lets a
     download manager (IDM) take over the transfer cleanly: the browser
     navigates to the URL instead of the page reading a fetch body. The token
     must be single-use, user-bound and short-lived, and genuine failures must
     still surface on the issuing request.
"""

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import TermConfig
from src.database import EntitlementDB, generate_id
from src.routers import generation as gen_router
from src.routers.generation import X_FILENAME_HEADER
from tests.conftest import make_school, make_user
from tests.test_export_download import make_job_with_lessons

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _term_config(scheme_id: str, *, school="Spoofed School", teacher="Imposter") -> TermConfig:
    """A config carrying deliberately false identity, to prove it is ignored."""
    return TermConfig(
        scheme_of_work_id=scheme_id,
        academic_year="2026/2027",
        term="First Term",
        class_level="Basic 9",
        subject="Science",
        term_start_date="2026-09-11",
        term_end_date="2026-12-18",
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=24,
        teaching_days=[0, 2, 4],
        holidays=[],
        ai_mode="OFF",
        template_type="GES-style",
        template_id="",
        include_special_weeks=False,
        school_name=school,
        teacher_name=teacher,
    )


class TestServerDerivedIdentity:
    """PART 14/15/32: identity is server-authoritative."""

    def test_school_name_comes_from_the_users_school_relationship(self, db):
        school = make_school(db, name="Awasive M/A JHS")
        u = make_user(db, role="teacher", school_id=school.id,
                      email="t@awasive.edu.gh")
        assert gen_router._resolve_school_name(db, u) == "Awasive M/A JHS"

    def test_school_name_is_none_without_a_school_membership(self, db):
        u = make_user(db, role="teacher", email="nomad@t.test")
        # None — never a generic/demo school — so the header renders blank
        # rather than inventing an institution.
        assert gen_router._resolve_school_name(db, u) is None

    def test_teacher_name_comes_from_the_profile(self, db):
        u = make_user(db, role="teacher", email="s@t.test")
        u.full_name = "Saviour Amegayie"
        db.commit()
        assert gen_router._resolve_teacher_name(db, u) == "Saviour Amegayie"

    def test_teacher_name_falls_back_to_email_local_part(self, db):
        """PART 18: a profile with no name yet still yields a usable label
        (the UI separately prompts for the full name), never a generic
        'Teacher' placeholder."""
        u = make_user(db, role="teacher", email="kwame.bonsu@t.test")
        u.full_name = ""
        db.commit()
        resolved = gen_router._resolve_teacher_name(db, u)
        # The local part is used verbatim (title-cased), so a dotted handle
        # keeps its dot. It is the account's own identifier, not a placeholder.
        assert resolved == "Kwame.Bonsu"
        assert resolved.lower() != "teacher"

    @pytest.mark.asyncio
    async def test_generate_overwrites_client_supplied_identity(self, db, monkeypatch):
        """The security property end to end: a crafted config must not survive.

        The client submits a false school and teacher; the endpoint resolves
        both from the authenticated user before any lesson is generated.
        """
        school = make_school(db, name="Awasive M/A JHS")
        u = make_user(db, role="teacher", school_id=school.id,
                      email="t@awasive.edu.gh")
        u.full_name = "Saviour Amegayie"
        db.commit()
        _scheme, job = make_job_with_lessons(db, u, lessons=1, school_id=school.id)

        captured = {}

        def _stub_generate_all(scheme, config, template_id=None):
            captured["school_name"] = config.school_name
            captured["teacher_name"] = config.teacher_name
            return SimpleNamespace(
                status=SimpleNamespace(value="completed"),
                total_lessons=0, completed_lessons=0,
            )

        # Avoid the real (heavy) parse + render; this test is about identity,
        # not document generation. The stub still carries one real instruction
        # week so the indicator/quota pre-check has something to allocate.
        from datetime import date as _date
        from src.models import Week as _Week, WeekType as _WeekType

        def _stub_scheme_to_model(db_scheme):
            return SimpleNamespace(weeks=[_Week(
                week_number=1,
                start_date=_date(2026, 9, 11), end_date=_date(2026, 9, 18),
                week_type=_WeekType.INSTRUCTION,
                strand="Numbers", sub_strand="Counting",
                content_standards=[], indicators=["B7.1.1.1.1 Test indicator"],
                resources=[], scheme_of_work_id=_scheme.id,
            )])

        monkeypatch.setattr(gen_router.data_service, "scheme_to_model",
                            _stub_scheme_to_model)
        monkeypatch.setattr(gen_router.pipeline, "generate_all", _stub_generate_all)

        config = _term_config(_scheme.id)
        await gen_router.generate_lesson_plans(_scheme.id, config, u, db)

        assert captured["school_name"] == "Awasive M/A JHS"
        assert captured["teacher_name"] == "Saviour Amegayie"
        # The submitted values were discarded, not merged.
        assert captured["school_name"] != "Spoofed School"
        assert captured["teacher_name"] != "Imposter"

    @pytest.mark.asyncio
    async def test_a_teacher_cannot_generate_from_another_users_scheme(self, db):
        u = make_user(db, role="teacher", email="owner@t.test")
        other = make_user(db, role="teacher", email="snooper@t.test")
        scheme, _job = make_job_with_lessons(db, u, lessons=1)

        with pytest.raises(HTTPException) as e:
            await gen_router.generate_lesson_plans(
                scheme.id, _term_config(scheme.id), other, db)
        assert e.value.status_code == 404


class TestOneTimeDownloadUrl:
    """PART 27/28: pre-validated, single-use, user-bound download tokens."""

    def _stub_render(self, monkeypatch, tmp_path):
        """Skip the real DOCX render; the token contract is what's under test."""
        def _fake_combined(label, lessons, tt, out_path, template_id=None):
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"PK\x03\x04stub docx body")
            return out_path
        monkeypatch.setattr(gen_router.pipeline, "export_docx_combined",
                            _fake_combined)
        monkeypatch.chdir(tmp_path)

    @pytest.mark.asyncio
    async def test_issuing_returns_a_token_url_and_filename(self, db, tmp_path, monkeypatch):
        self._stub_render(monkeypatch, tmp_path)
        u = make_user(db, role="teacher", email="dl-issue@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "docx", "GES-style", None, u, db)

        assert res["download_url"].startswith("/api/generation/downloads/")
        assert res["filename"].endswith(".docx")
        assert res["media_type"] == DOCX_MIME
        # The token is an opaque, unguessable value, never the file path.
        token = res["download_url"].rsplit("/", 1)[-1]
        assert len(token) >= 32
        assert job.id not in token and "exports" not in token

    @pytest.mark.asyncio
    async def test_issuing_xlsx_returns_a_token_url(self, db, tmp_path, monkeypatch):
        """The register (XLSX) must be reachable through the same one-time
        download path as DOCX/PDF/ZIP, otherwise the export button 400s."""
        def _fake_xlsx(lessons, out_path):
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"PK\x03\x04stub xlsx body")
            return out_path
        monkeypatch.setattr(gen_router.pipeline, "export_xlsx", _fake_xlsx)
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="dl-xlsx@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "xlsx", "GES-style", None, u, db)

        assert res["download_url"].startswith("/api/generation/downloads/")
        assert res["filename"].endswith(".xlsx")
        assert res["media_type"] == \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @pytest.mark.asyncio
    async def test_zip_download_url_is_pro_gated_for_free_tier(self, db, tmp_path, monkeypatch):
        """The UI's export buttons all go through /download-url, so the ZIP
        entitlement gate must live here too: Free Tier gets the controlled 403
        and the zip is never rendered (the gate fires before any pipeline work).
        """
        def _fail_render(*args, **kwargs):
            raise AssertionError("zip render must not run when the gate denies")
        monkeypatch.setattr(gen_router.pipeline, "export_zip", _fail_render)
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="dl-zip-free@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        with pytest.raises(HTTPException) as e:
            await gen_router.issue_download_url(job.id, "zip", "GES-style", None, u, db)

        assert e.value.status_code == 403
        assert e.value.detail == "ZIP export is available with Teacher Pro."

    @pytest.mark.asyncio
    async def test_zip_download_url_issues_token_for_pro_tier(self, db, tmp_path, monkeypatch):
        """Pro/teacher edition passes the same gate and receives a normal
        one-time token — the gate narrows entitlement, it doesn't break zip."""
        def _fake_zip(lessons, tt, out_path, template_id=None,
                      structure=None, context=None):
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"PK\x03\x04stub zip body")
            return out_path
        monkeypatch.setattr(gen_router.pipeline, "export_zip", _fake_zip)
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="dl-zip-pro@t.test")
        u.school_id = None
        u.subscription_type = "individual"
        db.commit()
        ent = EntitlementDB(
            id=generate_id(),
            user_id=u.id,
            edition="teacher",
            subscription_type="individual",
            generation_limit=0,
            generations_used=0,
            batch_generation=True,
            zip_export=True,
            pdf_export=True,
            custom_template_limit=10,
            history_limit=100,
            ai_enabled=True,
            ai_credits=50,
            ai_credits_used=0,
        )
        db.add(ent)
        db.commit()
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "zip", "GES-style", None, u, db)

        assert res["download_url"].startswith("/api/generation/downloads/")
        assert res["filename"].endswith(".zip")
        assert res["media_type"] == "application/zip"

    @pytest.mark.asyncio
    async def test_token_delivers_an_attachment_download_once(self, db, tmp_path, monkeypatch):
        self._stub_render(monkeypatch, tmp_path)
        u = make_user(db, role="teacher", email="dl-once@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "docx", "GES-style", None, u, db)
        token = res["download_url"].rsplit("/", 1)[-1]

        first = await gen_router.download_by_token(token, u)
        assert isinstance(first, FileResponse)
        assert first.media_type == DOCX_MIME
        # The token endpoint uses attachment (it is a navigation, not a fetch),
        # which is what lets the browser/IDM own the transfer.
        assert first.headers["content-disposition"].startswith("attachment;")
        assert unquote(first.headers[X_FILENAME_HEADER]) == res["filename"]

        # Single use: the same token is dead now.
        with pytest.raises(HTTPException) as e:
            await gen_router.download_by_token(token, u)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_token_is_user_bound(self, db, tmp_path, monkeypatch):
        self._stub_render(monkeypatch, tmp_path)
        u = make_user(db, role="teacher", email="dl-mine@t.test")
        other = make_user(db, role="teacher", email="dl-theirs@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "docx", "GES-style", None, u, db)
        token = res["download_url"].rsplit("/", 1)[-1]

        with pytest.raises(HTTPException) as e:
            await gen_router.download_by_token(token, other)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_browser_navigation_downloads_without_a_bearer_header(self, db, tmp_path, monkeypatch):
        """The browser reaches this URL by navigation, which cannot carry an
        Authorization header. The single-use token itself must therefore
        authorize the transfer (a presigned URL), or every export 401s as soon
        as the frontend and API are not the same origin (the web build).
        """
        self._stub_render(monkeypatch, tmp_path)
        u = make_user(db, role="teacher", email="dl-nav@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "docx", "GES-style", None, u, db)
        token = res["download_url"].rsplit("/", 1)[-1]

        # No authenticated user (browser navigation) still delivers once...
        delivered = await gen_router.download_by_token(token, None)
        assert isinstance(delivered, FileResponse)
        assert delivered.headers["content-disposition"].startswith("attachment;")
        # ...and only once.
        with pytest.raises(HTTPException) as e:
            await gen_router.download_by_token(token, None)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_expired_token_is_rejected(self, db, tmp_path, monkeypatch):
        self._stub_render(monkeypatch, tmp_path)
        u = make_user(db, role="teacher", email="dl-ttl@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        res = await gen_router.issue_download_url(job.id, "docx", "GES-style", None, u, db)
        token = res["download_url"].rsplit("/", 1)[-1]

        # Rewind the issued token past its TTL.
        gen_router._DOWNLOAD_TOKENS[token]["expires_at"] = time.time() - 1
        with pytest.raises(HTTPException) as e:
            await gen_router.download_by_token(token, u)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_genuine_failures_surface_on_the_issuing_request(self, db, monkeypatch):
        """PART 27 acceptance, case A: a real failure must not be hidden.

        A missing job is reported now, on the POST — not deferred to a dead
        token link that the user clicks later.
        """
        u = make_user(db, role="teacher", email="dl-missing@t.test")
        with pytest.raises(HTTPException) as e:
            await gen_router.issue_download_url("no-such-job", "docx", "GES-style", None, u, db)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unsupported_format_is_rejected(self, db, monkeypatch):
        u = make_user(db, role="teacher", email="dl-fmt@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        with pytest.raises(HTTPException) as e:
            await gen_router.issue_download_url(job.id, "exe", "GES-style", None, u, db)
        assert e.value.status_code == 400

    @pytest.mark.asyncio
    async def test_pdf_unavailable_is_a_real_503_on_issue(self, db, tmp_path, monkeypatch):
        """No converter: the failure is reported up front, never deferred."""
        from src.engines.pdf_export import PDFExportEngine
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="dl-pdf503@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        with patch.object(PDFExportEngine, "is_available", return_value=False):
            with pytest.raises(HTTPException) as e:
                await gen_router.issue_download_url(job.id, "pdf", "GES-style", None, u, db)
        assert e.value.status_code == 503


# ── Performance indicator phrasing (approved GES format) ──────────────────────


class TestPerformanceIndicatorPhrasing:
    """Performance indicators must use the approved GES voice:

    ``Learners can <verb phrase>`` — no code prefix, no legacy
    'By the end of the lesson, learners should be able to:' prefix.
    """

    def test_simple_indicator_is_rephrased(self):
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        objectives = engine._generate_objectives(
            "Demonstrate the conversion of energy into useable forms.",
            "B7.4.3.1.2",
        )
        assert len(objectives) == 1
        desc = objectives[0].description
        assert desc == "Learners can Demonstrate the conversion of energy into useable forms."
        assert "By the end" not in desc
        assert "B7.4.3.1.2" not in desc

    def test_indicator_with_code_prefix_is_stripped(self):
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        objectives = engine._generate_objectives(
            "B9.1.1.1.1 Explore available manual and digital tools.",
            "B9.1.1.1.1",
        )
        desc = objectives[0].description
        assert desc == "Learners can Explore available manual and digital tools."
        assert "B9.1.1.1.1" not in desc

    def test_legacy_by_the_end_prefix_is_normalised(self):
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        objectives = engine._generate_objectives(
            "By the end of the lesson, learners should be able to: Identify hardware.",
            "B7.1.1.1",
        )
        desc = objectives[0].description
        assert desc == "Learners can Identify hardware."
        assert "By the end" not in desc

    def test_learners_should_be_able_to_is_normalised(self):
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        objectives = engine._generate_objectives(
            "Learners should be able to explain the water cycle.",
            "B7.2.1.1",
        )
        desc = objectives[0].description
        assert desc == "Learners can explain the water cycle."
        assert "should be able to" not in desc

    def test_multiple_indicators_each_rephrased(self):
        """In the per-lesson model each indicator gets its own objective via
        its own _generate_objectives call (one lesson per indicator)."""
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        obj1 = engine._generate_objectives(
            "B7.1.1.1 Identify hardware components.", "B7.1.1.1",
        )
        obj2 = engine._generate_objectives(
            "B7.1.1.2 Install an operating system.", "B7.1.1.2",
        )
        assert obj1[0].description == "Learners can Identify hardware components."
        assert obj2[0].description == "Learners can Install an operating system."

    def test_indicator_code_stored_separately(self):
        from src.engines.allocation_engine import AllocationEngine
        engine = AllocationEngine()
        objectives = engine._generate_objectives(
            "B7.1.1.1 Identify hardware.",
            "B7.1.1.1",
        )
        assert objectives[0].indicator_code == "B7.1.1.1"
        assert "B7.1.1.1" not in objectives[0].description


class TestIndicatorCellNoCodeDuplication:
    """The Indicator cell must show each code once, prefixing its description."""

    def test_code_already_in_text_not_duplicated(self):
        from src.engines.official_ges_template import _code_and_text_list
        result = _code_and_text_list(
            ["B7.4.3.1.2"],
            ["B7.4.3.1.2 Demonstrate the conversion of energy into useable forms."],
        )
        assert result == ["B7.4.3.1.2 Demonstrate the conversion of energy into useable forms."]

    def test_code_prepended_when_text_has_no_code(self):
        from src.engines.official_ges_template import _code_and_text_list
        result = _code_and_text_list(
            ["B7.1.1.1"],
            ["Identify hardware components."],
        )
        assert result == ["B7.1.1.1 Identify hardware components."]

    def test_multiple_indicators_mixed(self):
        from src.engines.official_ges_template import _code_and_text_list
        result = _code_and_text_list(
            ["B7.1.1.1", "B7.1.1.2"],
            ["B7.1.1.1 Identify hardware.",
             "Install an operating system."],
        )
        assert result == [
            "B7.1.1.1 Identify hardware.",
            "B7.1.1.2 Install an operating system.",
        ]

    def test_empty_codes_list_graceful(self):
        from src.engines.official_ges_template import _code_and_text_list
        result = _code_and_text_list([], ["Describe something."])
        assert result == ["Describe something."]

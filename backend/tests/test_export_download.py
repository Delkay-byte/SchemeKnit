"""
Export/download layer tests.

Two failure layers are covered separately, because conflating them is what made
the reported bug hard to diagnose:

  * PDF layer 1 — no converter toolchain on the server (503, explicit message).
  * PDF layer 2 — converter present but no usable PDF produced (controlled 500).
  * DOCX — served with the correct MIME type, server-chosen filename, and the
    approved organizational table topology (not the legacy Label|Value grid).
  * Browser transport — Chrome aborts a blob download whose object URL is
    revoked synchronously after the click.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (
    GenerationJobDB, LessonPlanDB, SchemeDB, generate_id, EntitlementDB,
)
from src.engines.pdf_export import (
    PDF_CONVERSION_FAILED, PDF_CONVERTER_REQUIREMENT, PDFConversionError,
    PDFExportEngine, _is_real_pdf,
)
from urllib.parse import unquote

from src.routers.generation import X_FILENAME_HEADER
from src.routers import generation as gen_router
from tests.conftest import make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _grant_pro_entitlement(db, user):
    """Grant Pro entitlement to a test user (ZIP/batch/PDF access)."""
    ent = EntitlementDB(
        id=generate_id(),
        user_id=user.id,
        edition="teacher",
        subscription_type="individual",
        batch_generation=True,
        zip_export=True,
        pdf_export=True,
        custom_template_limit=10,
        history_limit=100,
        ai_enabled=True,
        ai_credits=50,
        ai_credits_used=0,
        generation_limit=0,
        generations_used=0,
    )
    db.add(ent)
    db.commit()


def make_job_with_lessons(db, user, lessons=2, school_id=None):
    """A completed generation job with real lesson rows, ready to export."""
    scheme = SchemeDB(
        id=generate_id(), owner_id=user.id, school_id=school_id,
        filename="Basic 9 Science - Scheme.docx", subject="Science",
        class_level="Basic 9", term="First Term",
    )
    db.add(scheme)
    db.commit()
    job = GenerationJobDB(
        id=generate_id(), owner_id=user.id, scheme_id=scheme.id,
        status="completed", completed_lessons=lessons,
    )
    db.add(job)
    db.flush()
    for i in range(1, lessons + 1):
        db.add(LessonPlanDB(
            id=generate_id(), job_id=job.id, owner_id=user.id, scheme_id=scheme.id,
            week_number=i, lesson_sequence=1, lesson_number=i,
            lesson_date=date(2026, 9, 11) + timedelta(days=7 * (i - 1)),
            class_level="Basic 9", subject="Science", class_size=24,
            duration_minutes=60, school_name="Test School", teacher_name="T",
            strand="Diversity of Matter", sub_strand="Materials",
            content_standard="B9.1.1.1 Show understanding of matter",
            indicators=["B9.1.1.1.1 Identify materials"],
            lesson_topic=f"Topic {i}",
            introduction="Begin with a review of the previous lesson.",
            main_activities=[{"phase": "MAIN", "description": "Present the concept."}],
            learner_activities=[{"phase": "LEARNER", "description": "Discuss in pairs."}],
            assessment="Assess learners orally.",
            conclusion="Summarise the lesson.",
            references=["Science Curriculum Pg. 33"],
            core_competencies=["CC"],
            teaching_learning_resources=["Charts"],
        ))
    db.commit()
    return scheme, job


class TestPdfIntegrityGuard:
    """A body that isn't a PDF must never be treated as one."""

    def test_rejects_docx_renamed_as_pdf(self, tmp_path):
        f = tmp_path / "looks.pdf"
        f.write_bytes(b"PK\x03\x04this-is-really-a-docx")
        assert _is_real_pdf(f) is False

    def test_rejects_empty_and_missing(self, tmp_path):
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        assert _is_real_pdf(empty) is False
        assert _is_real_pdf(tmp_path / "nope.pdf") is False

    def test_accepts_real_pdf(self, tmp_path):
        f = tmp_path / "real.pdf"
        f.write_bytes(b"%PDF-1.4\n%rest of a pdf\n")
        assert _is_real_pdf(f) is True


class TestPdfEngineContract:
    """The engine must fail loudly rather than hand back the intermediate DOCX."""

    def test_convert_raises_when_no_backend_works(self, tmp_path):
        eng = PDFExportEngine()
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"PK\x03\x04")
        with patch.object(eng, "_try_docx2pdf", side_effect=RuntimeError("no Word")), \
             patch.object(eng, "_try_libreoffice", side_effect=RuntimeError("no LO")):
            with pytest.raises(PDFConversionError):
                eng._convert_docx_to_pdf(docx, tmp_path / "a.pdf")
        assert not (tmp_path / "a.pdf").exists()

    def test_converter_writing_non_pdf_is_rejected(self, tmp_path):
        """A converter that "succeeds" but emits a DOCX must not be accepted."""
        eng = PDFExportEngine()
        docx = tmp_path / "b.docx"
        docx.write_bytes(b"PK\x03\x04")
        pdf = tmp_path / "b.pdf"

        def bogus(docx_path, pdf_path):
            pdf_path.write_bytes(b"PK\x03\x04still a docx")
            return pdf_path

        with patch.object(eng, "_try_docx2pdf", side_effect=bogus), \
             patch.object(eng, "_try_libreoffice", side_effect=RuntimeError("no LO")):
            with pytest.raises(PDFConversionError):
                eng._convert_docx_to_pdf(docx, pdf)

    def test_batch_raises_when_every_conversion_fails(self, tmp_path):
        eng = PDFExportEngine()
        stub = SimpleNamespace(subject="Science", class_level="Basic 9",
                               lesson_date=None, week_number=1, lesson_sequence=1)
        with patch.object(eng, "export_single",
                          side_effect=PDFConversionError("Word not installed")):
            with pytest.raises(PDFConversionError):
                eng.export_batch([stub], None, tmp_path)

    def test_batch_returns_only_successes(self, tmp_path):
        eng = PDFExportEngine()
        stubs = [
            SimpleNamespace(subject="Science", class_level="Basic 9",
                            lesson_date=None, week_number=w, lesson_sequence=1)
            for w in (1, 2)
        ]
        calls = {"n": 0}

        def flaky(lp, template, path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PDFConversionError("bad lesson")
            path.write_bytes(b"%PDF-1.4 ok")
            return path

        with patch.object(eng, "export_single", side_effect=flaky):
            out = eng.export_batch(stubs, None, tmp_path)
        assert len(out) == 1 and out[0].suffix == ".pdf"


class TestPdfEndpointLayers:
    @pytest.mark.asyncio
    async def test_layer1_missing_converter_is_503(self, db):
        u = make_user(db, role="teacher", email="pdf-l1@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        with patch.object(PDFExportEngine, "is_available", return_value=False):
            with pytest.raises(HTTPException) as e:
                await gen_router.export_pdf(job.id, "GES-style", None, u, db)
        assert e.value.status_code == 503
        assert "LibreOffice" in e.value.detail

    @pytest.mark.asyncio
    async def test_layer2_conversion_failure_is_controlled_500(self, db, monkeypatch):
        u = make_user(db, role="teacher", email="pdf-l2@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        def _boom(pipeline, docx_path, pdf_path):
            raise PDFConversionError("C:/secret/path crashed")

        monkeypatch.setattr(gen_router, "_convert_only", _boom)
        with patch.object(PDFExportEngine, "is_available", return_value=True):
            with pytest.raises(HTTPException) as e:
                await gen_router.export_pdf(job.id, "GES-style", None, u, db)
        assert e.value.status_code == 500
        assert e.value.detail == PDF_CONVERSION_FAILED
        # Controlled: no internal path, no traceback, no stack detail leaks out.
        assert "secret" not in e.value.detail
        assert "Traceback" not in e.value.detail

    @pytest.mark.asyncio
    async def test_non_pdf_output_is_never_served(self, db, tmp_path, monkeypatch):
        """Defence in depth: even a misbehaving converter can't yield a fake PDF."""
        u = make_user(db, role="teacher", email="pdf-l3@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        fake = tmp_path / "lesson_plans.pdf"
        fake.write_bytes(b"PK\x03\x04a docx, not a pdf")

        def _fake_convert(pipeline, docx_path, pdf_path):
            fake.write_bytes(fake.read_bytes())
            return pdf_path

        monkeypatch.setattr(gen_router, "_convert_only", _fake_convert)
        with patch.object(PDFExportEngine, "is_available", return_value=True):
            with pytest.raises(HTTPException) as e:
                await gen_router.export_pdf(job.id, "GES-style", None, u, db)
        assert e.value.status_code == 500
        assert e.value.detail == PDF_CONVERSION_FAILED

    @pytest.mark.asyncio
    async def test_valid_pdf_is_served_with_pdf_headers(self, db, tmp_path, monkeypatch):
        u = make_user(db, role="teacher", email="pdf-ok@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        def _fake_convert(pipeline, docx_path, pdf_path):
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            return pdf_path

        monkeypatch.setattr(gen_router, "_convert_only", _fake_convert)
        with patch.object(PDFExportEngine, "is_available", return_value=True):
            res = await gen_router.export_pdf(job.id, "GES-style", None, u, db)
        assert isinstance(res, FileResponse)
        assert res.media_type == "application/pdf"
        assert unquote(res.headers[X_FILENAME_HEADER]) == \
            "Lesson_Plans_Basic_9_Science_Scheme.pdf"


class TestDocxEndpointContract:
    @pytest.mark.asyncio
    async def test_docx_headers_and_approved_topology(self, db, tmp_path, monkeypatch):
        """End-to-end: export endpoint -> approved template -> real DOCX.

        This is the acceptance path for "the generated DOCX structurally matches
        the approved source", exercised through the actual download endpoint
        rather than the renderer in isolation. It compares the served document
        against the SOURCE document, not against our own IR.
        """
        from docx import Document

        from src.engines.approved_template import TEMPLATE_ID
        from src.validators.docx_structure_compare import (
            golden_master_source_path, validate_generated,
        )

        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="docx-e2e@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=2)

        res = await gen_router.export_docx(job.id, "GES-style", TEMPLATE_ID, u, db)

        assert isinstance(res, FileResponse)
        assert res.media_type == DOCX_MIME
        assert unquote(res.headers[X_FILENAME_HEADER]) == \
            "Lesson_Plans_Basic_9_Science_Scheme.docx"

        doc = Document(res.path)
        # The approved topology is repeated once per lesson in a combined export:
        # metadata (4x4), curriculum alignment (4x2), pedagogy (4x2), delivery
        # grid (4x3) — the source document's measured fingerprint.
        assert [(len(t.rows), len(t.columns)) for t in doc.tables] == \
            [(4, 4), (4, 2), (4, 2), (4, 3)] * 2

        # Not the legacy generic template: no 2-column Label|Value metadata grid.
        assert not [t for t in doc.tables
                    if len(t.columns) == 2 and len(t.rows) == 6]

        report = validate_generated(
            res.path,
            expected_values=["Diversity of Matter", "B9.1.1.1",
                             "Begin with a review of the previous lesson."],
            # "LESSON PLAN" is NOT forbidden here: it is part of the approved
            # source's own printed title, which the in-place renderer preserves.
            # A Basic 7 indicator would be foreign content for a Basic 9 lesson.
            forbidden_values=["Forces & Energy", "B7.4.3.1",
                             "Introduction to Node.js"],
            source_path=golden_master_source_path(),
        )
        assert report["pass"], [
            (g, c["name"], c["detail"])
            for g in ("structure", "content")
            for c in report[g]["checks"] if not c["pass"]]

    @pytest.mark.asyncio
    async def test_docx_filename_comes_from_scheme(self, db, tmp_path, monkeypatch):
        from src.engines.approved_template import TEMPLATE_ID

        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="docx-name@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        res = await gen_router.export_docx(job.id, "GES-style", TEMPLATE_ID, u, db)
        assert unquote(res.headers[X_FILENAME_HEADER]) == \
            "Lesson_Plans_Basic_9_Science_Scheme.docx"
        assert ".docx" in res.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_builtin_export_names_include_week_and_lesson(self, db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="docx-builtin@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        res = await gen_router.export_docx(job.id, "GES-style", None, u, db)
        assert unquote(res.headers[X_FILENAME_HEADER]).endswith(".docx")
        assert res.media_type == DOCX_MIME

    @pytest.mark.asyncio
    async def test_export_requires_ownership(self, db):
        u = make_user(db, role="teacher", email="docx-owner@t.test")
        other = make_user(db, role="teacher", email="docx-other@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        with pytest.raises(HTTPException) as e:
            await gen_router.export_docx(job.id, "GES-style", None, other, db)
        assert e.value.status_code == 404


class TestZipBatchOutput:
    @pytest.mark.asyncio
    async def test_zip_honours_the_selected_template(self, db, tmp_path, monkeypatch):
        """Every lesson DOCX in the ZIP must use the approved topology.

        Regression: the client omitted `template_id` for ZIP while sending it for
        DOCX, so the same export produced two different layouts.
        """
        import io
        import zipfile

        from docx import Document

        from src.engines.approved_template import TEMPLATE_ID

        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="zip-tpl@t.test")
        _grant_pro_entitlement(db, u)
        _scheme, job = make_job_with_lessons(db, u, lessons=3)

        res = await gen_router.export_zip(job.id, "GES-style", TEMPLATE_ID, u, db)
        assert res.media_type == "application/zip"
        assert unquote(res.headers[X_FILENAME_HEADER]).endswith(".zip")

        with zipfile.ZipFile(res.path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".docx")]
            assert len(names) == 3
            for name in names:
                doc = Document(io.BytesIO(zf.read(name)))
                # Each member renders the approved source form in place, so its
                # topology is the source's measured fingerprint.
                assert [(len(t.rows), len(t.columns)) for t in doc.tables] == \
                    [(4, 4), (4, 2), (4, 2), (4, 3)], name

    @pytest.mark.asyncio
    async def test_zip_without_template_still_works(self, db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="zip-plain@t.test")
        _grant_pro_entitlement(db, u)
        _scheme, job = make_job_with_lessons(db, u, lessons=2)
        res = await gen_router.export_zip(job.id, "GES-style", None, u, db)
        assert res.media_type == "application/zip"

    @pytest.mark.asyncio
    async def test_zip_requires_ownership(self, db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="zip-own@t.test")
        other = make_user(db, role="teacher", email="zip-other@t.test")
        _scheme, job = make_job_with_lessons(db, u, lessons=1)
        with pytest.raises(HTTPException) as e:
            await gen_router.export_zip(job.id, "GES-style", None, other, db)
        assert e.value.status_code == 404


class TestDownloadHeaderContract:
    """The download-filename transport, and why it is a custom header.

    Regression: exports answered 200 with a perfectly valid body, but the
    browser refused the response and no file was ever saved. `Content-Disposition:
    attachment` makes Chrome/Edge classify an `application/zip` response as a
    download, and a download cannot be delivered to `fetch()`. Verified in real
    Chrome and Edge against the running app.
    """

    def test_download_response_never_uses_attachment(self, tmp_path):
        target = tmp_path / "archive.zip"
        target.write_bytes(b"PK\x03\x04")
        res = gen_router._download_response(target, "application/zip", "My Plans.zip")
        disposition = res.headers["content-disposition"]
        assert disposition.startswith("inline;")
        assert "attachment" not in disposition
        assert unquote(res.headers[X_FILENAME_HEADER]) == "My Plans.zip"

    def test_unsafe_filename_is_stripped_to_its_basename(self, tmp_path):
        target = tmp_path / "x.docx"
        target.write_bytes(b"PK\x03\x04")
        res = gen_router._download_response(
            target, DOCX_MIME, "../../etc/passwd.docx")
        assert unquote(res.headers[X_FILENAME_HEADER]) == "passwd.docx"

    def test_filename_header_is_url_encoded_and_exposed(self):
        from src.main import app
        from starlette.middleware.cors import CORSMiddleware

        # Percent-encoded so non-ASCII scheme/subject names survive the header.
        assert unquote(gen_router.quote("Lesson Plans (B9).docx", safe="")) == \
            "Lesson Plans (B9).docx"
        assert gen_router.quote("Lesson Plans (B9).docx", safe="") != \
            "Lesson Plans (B9).docx"

        exposed = [
            m for m in app.user_middleware
            if getattr(m, "cls", None) is CORSMiddleware
        ]
        assert exposed, "CORS middleware missing"
        assert X_FILENAME_HEADER in str(exposed[0].kwargs.get("expose_headers", []))

    @pytest.mark.asyncio
    async def test_every_export_carries_the_filename_header(self, db, tmp_path, monkeypatch):
        from src.engines.approved_template import TEMPLATE_ID
        from src.engines.pdf_export import PDFExportEngine

        monkeypatch.chdir(tmp_path)
        u = make_user(db, role="teacher", email="dl-headers@t.test")
        _grant_pro_entitlement(db, u)
        _scheme, job = make_job_with_lessons(db, u, lessons=1)

        responses = [
            await gen_router.export_docx(job.id, "GES-style", TEMPLATE_ID, u, db),
            await gen_router.export_zip(job.id, "GES-style", TEMPLATE_ID, u, db),
            await gen_router.export_xlsx(job.id, u, db),
        ]
        real_pdf = tmp_path / "out.pdf"
        real_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        with patch.object(PDFExportEngine, "is_available", return_value=True), \
             patch.object(gen_router.pipeline, "export_pdf_batch", return_value=[real_pdf]):
            responses.append(
                await gen_router.export_pdf(job.id, "GES-style", None, u, db))

        for res in responses:
            assert X_FILENAME_HEADER in res.headers, res.media_type
            assert unquote(res.headers[X_FILENAME_HEADER])
            assert res.headers["content-disposition"].startswith("inline;")
            assert "attachment" not in res.headers["content-disposition"]


class TestBrowserDownloadTransport:
    """Source contracts for the browser download path.

    The PDF/DOCX generation can be perfectly correct and the download still fail
    in the browser; these assertions pin the transport behaviour that fixed the
    Chrome-only failure (Edge tolerated the synchronous revoke, Chrome did not).
    """

    def _api_source(self) -> str:
        return (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")

    def _generate_page_source(self) -> str:
        return (FRONTEND / "app" / "generate" / "[id]" / "page.tsx").read_text(
            encoding="utf-8")

    def test_object_url_is_revoked_only_after_a_deferral(self):
        src = self._api_source()
        # The revoke must exist exactly once, and only inside a timer callback.
        # A synchronous revoke in the click's task is what Chrome aborted.
        assert src.count("revokeObjectURL") == 1
        assert "setTimeout(() => URL.revokeObjectURL(url)" in src
        click_at = src.index("a.click()")
        between = src[click_at:src.index("setTimeout", click_at)]
        assert "revokeObjectURL" not in between

    def test_download_uses_shared_helper_and_server_filename(self):
        src = self._api_source()
        assert "Content-Disposition" in src
        assert "filename*=UTF-8''" in src     # RFC 5987 form is preferred
        assert "sanitizeDownloadName" in src

    def test_generate_page_no_longer_hand_rolls_the_anchor(self):
        """The page uses the one-time download URL: the POST pre-validates and
        then the browser navigates, so no JS body read can race with a download
        manager (the IDM "Failed to fetch" false error — PART 27)."""
        src = self._generate_page_source()
        assert "api.getDownloadUrl(" in src
        assert "api.navigateToDownload(" in src
        # The blob/anchor path is gone from the page.
        assert "api.downloadFile(" not in src
        assert "createObjectURL" not in src

    def test_every_export_passes_the_selected_template(self):
        """DOCX, PDF and ZIP must all carry template_id, or they diverge."""
        api_src = self._api_source()
        for fn in ("exportDocx", "exportPdf", "exportZip"):
            start = api_src.index(f"async {fn}(")
            body = api_src[start:start + 700]
            assert "templateId" in body, fn
            assert "template_id" in body, fn
        # The one-time URL path also forwards the selected template.
        start = api_src.index("getDownloadUrl(")
        body = api_src[start:start + 700]
        assert "template_id" in body
        page = self._generate_page_source()
        assert "api.getDownloadUrl(" in page
        assert "config.template_type, config.template_id" in page

    def test_export_failures_are_visible_when_a_scheme_is_loaded(self):
        """A failed export must not be silent: the error banner has to render
        even though the scheme loaded correctly."""
        src = self._generate_page_source()
        assert "{error && scheme && (" in src
        assert 'role="alert"' in src

    def test_export_errors_surface_as_messages(self):
        """A 403/500/503 export must show the server message, not crash."""
        src = self._api_source()
        assert "Export failed" in src
        assert "err.detail" in src


class TestPdfMessagesAreOperatorSafe:
    def test_messages_have_no_paths_or_status_codes(self):
        for msg in (PDF_CONVERTER_REQUIREMENT, PDF_CONVERSION_FAILED):
            assert "\\" not in msg and ":/" not in msg
            assert "Traceback" not in msg
            assert "500" not in msg and "503" not in msg

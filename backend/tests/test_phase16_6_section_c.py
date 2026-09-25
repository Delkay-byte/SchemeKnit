"""
Phase 16.6 Section C — evidence-based class-level detection.

Never silent Basic 6→9; never unknown→Basic 9. Evidence is combined from
title zone, body frequency, and filename — not `_LEVEL_SIGNALS` list order.
"""
import asyncio
from pathlib import Path

import pytest
from docx import Document

from src.models import ClassLevel
from src.parsers.docx_parser import DOCXParser
from src.parsers.pdf_parser import PDFParser

REAL = Path(__file__).resolve().parent.parent / "real_documents"
BACKEND = Path(__file__).resolve().parent.parent

B6 = REAL / "BASIC 6 TERM 1.docx"
B6_FRENCH = REAL / "BASIC 6 FRENCH SCHEME OF LEARNING.docx"
B7 = REAL / "BASIC 7 TERM 1.docx"
B7_PDF = REAL / "BASIC 7 TERM 1.pdf"
B9_PDF = REAL / "BASIC 9 TERM 1.pdf"
B8_CAPTURE = BACKEND / "repro_multi.docx"


class TestRealDocumentsClass:
    @pytest.mark.skipif(not B6.exists(), reason="b6 missing")
    def test_basic6_all_in_one(self):
        info = DOCXParser().analyze(B6, original_filename=B6.name)
        assert info["metadata"]["class_level"] == "Basic 6"

    @pytest.mark.skipif(not B6_FRENCH.exists(), reason="b6 french missing")
    def test_basic6_french_not_basic9(self):
        info = DOCXParser().analyze(
            B6_FRENCH, original_filename=B6_FRENCH.name
        )
        assert info["metadata"]["class_level"] == "Basic 6"
        assert info["metadata"]["class_signals"]["conflict"] is False

    @pytest.mark.skipif(not B7.exists(), reason="b7 missing")
    def test_basic7_preserved(self):
        info = DOCXParser().analyze(B7, original_filename=B7.name)
        assert info["metadata"]["class_level"] == "Basic 7"

    @pytest.mark.skipif(not B7_PDF.exists(), reason="b7 pdf missing")
    def test_basic7_pdf_preserved(self):
        info = PDFParser().analyze(B7_PDF, original_filename=B7_PDF.name)
        assert info["metadata"]["class_level"] == "Basic 7"

    @pytest.mark.skipif(not B8_CAPTURE.exists(), reason="b8 capture missing")
    def test_basic8_preserved(self):
        info = DOCXParser().analyze(
            B8_CAPTURE, original_filename=B8_CAPTURE.name
        )
        assert info["metadata"]["class_level"] == "Basic 8"

    @pytest.mark.skipif(not B9_PDF.exists(), reason="b9 pdf missing")
    def test_basic9_preserved(self):
        info = PDFParser().analyze(B9_PDF, original_filename=B9_PDF.name)
        assert info["metadata"]["class_level"] == "Basic 9"


class TestEvidenceCombination:
    def setup_method(self):
        self.parser = DOCXParser()

    def test_title_zone_beats_later_body_mention(self):
        """Earliest title-zone evidence wins over a later stray mention."""
        text = (
            "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - FRENCH LANGUAGE\n"
            "Progression note: learners will meet Basic 9 content later."
        )
        signals = self.parser.class_level_signals(text, "")
        assert signals["resolved"] == "Basic 6"
        assert signals["conflict"] is False

    def test_list_order_does_not_prefer_basic9(self):
        # Basic 9 sits before Basic 6 in _LEVEL_SIGNALS — list order must not win.
        text = "Basic 6 Scheme of Learning for the academic year"
        assert self.parser._first_signal(text) == "Basic 6"
        text2 = "Basic 6 title ... Basic 9 reference later"
        assert self.parser._first_signal(text2) == "Basic 6"

    def test_filename_secondary_signal(self):
        signals = self.parser.class_level_signals(
            "Scheme of Learning for the year", "BASIC_8_TERM_1.pdf"
        )
        assert signals["resolved"] == "Basic 8"
        assert signals["document"] is None
        assert signals["filename"] == "Basic 8"

    def test_conflict_resolves_to_none_never_basic9(self):
        signals = self.parser.class_level_signals(
            "Basic 9 Scheme of Learning", "BASIC 6 TERM 1.docx"
        )
        assert signals["conflict"] is True
        assert signals["resolved"] is None

    def test_no_evidence_returns_none_not_basic9(self):
        signals = self.parser.class_level_signals(
            "Notes about the academic year and reopening", "plan.docx"
        )
        assert signals["resolved"] is None
        assert signals["document"] is None
        assert signals["filename"] is None

    def test_detect_class_level_returns_none_without_evidence(self):
        assert self.parser._detect_class_level(None, "no level here", "x.docx") is None

    def test_indicator_codes_are_not_level_signals(self):
        # B9.1.1.1 in a Basic 8 document must not flip the class.
        text = "Basic 8 Scheme. Content: B9.1.1.1 Discuss rocks"
        assert self.parser._first_signal(text) == "Basic 8"

    def test_body_majority_wins_outside_title_zone(self):
        # No title-zone hit (first 500 chars clear); repeated Basic 7 wins.
        pad = "x" * 600
        text = pad + " Basic 7 notes. " + pad + " Basic 7 again. " + pad + " Basic 9 once."
        assert self.parser._first_signal(text) == "Basic 7"


class TestParseClassLevel:
    @pytest.mark.skipif(not B6_FRENCH.exists(), reason="missing")
    def test_parse_french_scheme_class(self):
        scheme = asyncio.run(DOCXParser().parse(
            B6_FRENCH, original_filename=B6_FRENCH.name
        ))
        assert scheme.class_level == ClassLevel.BASIC_6

    @pytest.mark.skipif(not B6.exists(), reason="missing")
    def test_parse_b6_class(self):
        scheme = asyncio.run(DOCXParser().parse(
            B6, original_filename=B6.name
        ))
        assert scheme.class_level == ClassLevel.BASIC_6


class TestDefaultsNeverStampCurriculum:
    def test_default_class_level_not_used_as_scheme_fallback(self):
        """UserPreferences.default_class_level must not stamp schemes."""
        service_src = (BACKEND / "src" / "service.py").read_text(encoding="utf-8")
        gen_src = (BACKEND / "src" / "routers" / "generation.py").read_text(
            encoding="utf-8"
        )
        doc_src = (BACKEND / "src" / "routers" / "documents.py").read_text(
            encoding="utf-8"
        )
        for src in (service_src, gen_src, doc_src):
            assert "default_class_level" not in src

    def test_settings_default_is_preferences_only(self):
        settings_src = (
            BACKEND / "src" / "routers" / "settings.py"
        ).read_text(encoding="utf-8")
        # Appears only as a preferences payload key / column default — never
        # written into SchemeDB.class_level.
        assert "default_class_level" in settings_src
        assert 'SchemeDB(' not in settings_src or "default_class_level" not in settings_src.split("SchemeDB(")[0]

    def test_frontend_generate_form_has_no_basic9_seed(self):
        page = (
            BACKEND.parent / "frontend" / "src" / "app" / "(app)" / "generate" / "[id]" / "page.tsx"
        ).read_text(encoding="utf-8")
        assert "class_level: 'Basic 9'" not in page
        assert "subject: 'Science'" not in page.split("loadData")[0]

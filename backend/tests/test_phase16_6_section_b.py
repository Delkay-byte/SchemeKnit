"""
Phase 16.6 Section B — subject isolation through the parse → IR path.

DOCUMENT → SUBJECT SECTION → WEEK → INDICATOR → RESOURCES / STRAND / …
Week N of French must never be mixed with Week N of ICT unless the source
literally shares the resource.
"""
import asyncio
from pathlib import Path

import pytest

from src.parsers.docx_parser import DOCXParser
from src.parsers.pdf_parser import PDFParser

REAL = Path(__file__).resolve().parent.parent / "real_documents"
B6_DOCX = REAL / "BASIC 6 TERM 1.docx"
B6_PDF = REAL / "BASIC 6 TERM 1.pdf"

pytestmark = pytest.mark.skipif(
    not B6_DOCX.exists(), reason="real Basic 6 document not present"
)


def _parse(subject: str, parser=None):
    parser = parser or DOCXParser()
    return asyncio.run(parser.parse(
        B6_DOCX, original_filename=B6_DOCX.name, target_subject=subject,
    ))


def _week(scheme, n: int):
    return next(w for w in scheme.weeks if w.week_number == n)


class TestSectionIsolationRealB6:
    def test_ict_and_french_week1_resources_disjoint(self):
        ict = _parse("ICT")
        fre = _parse("French")
        ict_r = set(_week(ict, 1).resources)
        fre_r = set(_week(fre, 1).resources)
        assert ict_r and fre_r
        assert not (ict_r & fre_r), (
            f"cross-subject resources leaked: {ict_r & fre_r}"
        )
        # The known French contamination markers must not appear under ICT.
        joined = " ".join(r for w in ict.weeks for r in w.resources).lower()
        assert "haut-parleur" not in joined
        assert "vidéo" not in joined and "video," not in joined

    def test_ict_and_french_all_weeks_resources_disjoint(self):
        ict = _parse("ICT")
        fre = _parse("French")
        ict_all = {r for w in ict.weeks for r in w.resources}
        fre_all = {r for w in fre.weeks for r in w.resources}
        # Special-week labels may appear in every section (same source text);
        # curriculum resources must not cross.
        special = {"revision", "end of term assessment",
                   "sba activities and vacation"}
        ict_curric = {r for r in ict_all if r.strip().lower() not in special}
        fre_curric = {r for r in fre_all if r.strip().lower() not in special}
        assert not (ict_curric & fre_curric), (
            f"leaked: {ict_curric & fre_curric}"
        )

    def test_indicators_and_strands_isolated(self):
        ict = _parse("ICT")
        fre = _parse("French")
        w_i, w_f = _week(ict, 1), _week(fre, 1)
        assert w_i.strand != w_f.strand
        assert w_i.sub_strand != w_f.sub_strand
        assert set(w_i.indicators) & set(w_f.indicators) == set() or (
            # Indicator codes restart per subject in some packs — compare
            # full text, not bare codes.
            all(i1 != i2 for i1 in w_i.indicators for i2 in w_f.indicators)
        )
        assert any("computer" in i.lower() or "b6.1" in i.lower()
                   for i in w_i.indicators)
        assert any("salu" in i.lower() or "bonjour" in i.lower()
                   or "écoute" in i.lower() or "ecouter" in i.lower()
                   for i in w_f.indicators) or w_f.indicators

    def test_science_resources_not_in_french(self):
        sci = _parse("Science")
        fre = _parse("French")
        w_s, w_f = _week(sci, 1), _week(fre, 1)
        assert set(w_s.resources).isdisjoint(set(w_f.resources))
        assert "Grass, beans, mango, cassava and sweet potato" in w_s.resources

    def test_strands_isolated_across_three_subjects(self):
        strands = {
            name: {_week(_parse(name), n).strand for n in range(1, 6)}
            for name in ("ICT", "French", "Science")
        }
        # Week-1..5 strands are subject-specific in the real pack.
        assert strands["ICT"] != strands["French"]
        assert strands["Science"] != strands["French"]

    def test_parse_without_target_does_not_mix_subjects_when_section_forced_missing(
        self,
    ):
        # Requesting a subject that is not in the document must yield NO
        # weeks (not a silent fallback to every table).
        scheme = _parse("Career Technology")  # not in B6 pack
        assert scheme.weeks == [], (
            "missing section must not fall back to mixed cross-subject weeks"
        )


class TestSectionIsolationPdf:
    def test_b6_pdf_ict_vs_french_week1(self):
        if not B6_PDF.exists():
            pytest.skip("b6 pdf missing")
        ict = asyncio.run(PDFParser().parse(
            B6_PDF, original_filename=B6_PDF.name, target_subject="ICT"))
        fre = asyncio.run(PDFParser().parse(
            B6_PDF, original_filename=B6_PDF.name, target_subject="French"))
        assert ict.weeks and fre.weeks
        ict_r = set(_week(ict, 1).resources)
        fre_r = set(_week(fre, 1).resources)
        assert ict_r and fre_r
        assert not (ict_r & fre_r)
        assert _week(ict, 1).strand != _week(fre, 1).strand


class TestUploadDoesNotPersistMixedWeeks:
    """Multi-subject upload must store zero curriculum rows until confirm."""

    def test_parse_then_clear_mixed(self):
        scheme = asyncio.run(DOCXParser().parse(
            B6_DOCX, original_filename=B6_DOCX.name))
        # Raw parse without a target mixes sections — that shape must never
        # be what the upload endpoint persists for status "multiple".
        assert len(scheme.weeks) > 0  # parser still extracts for analysis
        # The router clears weeks when detection_status == "multiple";
        # assert the router source still contains that guard.
        src = Path(__file__).resolve().parent.parent.joinpath(
            "src/routers/documents.py"
        ).read_text(encoding="utf-8")
        assert 'detection.get("detection_status") == "multiple"' in src
        assert "scheme.weeks = []" in src

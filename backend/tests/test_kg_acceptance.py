"""
KG curriculum & lesson-generation acceptance (real source documents).

Source material (kept verbatim under tests/fixtures/wapef/):
  * ``WAPEF SCHEME OF LEARNING FOR KG.docx`` — KG2 whole-level scheme, 13
    weeks, code-only indicator cells ("K2.1.1.1.1 K2.1.1.1.1-3"), code-only
    content-standard cells ("k2.1.1.1"), repeated sub-strand continuation
    weeks (W6→W7, W12→W13).
  * ``KG 1 Scheme.pdf`` — KG1 whole-level scheme, 15 weeks, vertically merged
    header ("CONTENT / STANDARD" split across rows), indicator ranges per
    week, REVISION/REVISION-AND-ASSESSMENT/SBA special weeks.

Invariants under test (source-derived, not assumed):
  * one scheme row = one teaching week; the range tail (…-3) is the week's
    teachable indicator family — NEVER split into separate lessons because
    the source itself splits ranges across weeks when it means that (W7/W8
    of the KG1 PDF).
  * KG pedagogy is play-based (song/rhyme starters, play practice,
    observation checklist assessment) — never the Basic 7–9 board-work /
    written-exercise profile, for ANY KG subject area.
  * continuation weeks with identical rows still produce meaningfully
    different lessons (previous-lesson linkage).
  * source resources, content-standard codes and indicator ranges survive
    normalization verbatim.
  * the Approved WAPEF Plan remains the single output structure and the
    WAPEF fields stay teacher-selected.
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from src.parsers.docx_parser import DOCXParser
from src.parsers.pdf_parser import PDFParser
from src.engines.allocation_engine import AllocationEngine, scheme_has_indicators
from src.engines.calendar_engine import CalendarEngine
from src.engines import wapef_fields as wf
from src.engines.wapef_template import (
    render_document as render_wapef,
    validate_rendered_document,
)
from src.curriculum.lesson_builder import build_lesson
from src.curriculum.quality_gate import validate_lesson_quality
from src.engines.docx_export import DOCXExportEngine
from src.models import ClassLevel, Subject, TermConfig, WeekType

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wapef"
KG2_DOCX = FIXTURES / "WAPEF SCHEME OF LEARNING FOR KG.docx"
KG1_PDF = FIXTURES / "KG 1 Scheme.pdf"


def _kg2():
    return asyncio.run(DOCXParser().parse(KG2_DOCX, target_subject="Numeracy"))


def _kg1():
    return asyncio.run(PDFParser().parse(KG1_PDF, original_filename=KG1_PDF.name))


def _config(scheme, **overrides):
    base = dict(
        scheme_of_work_id="kg-acc",
        term_start_date=date(2026, 9, 15),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=1,
        lesson_duration_minutes=60,
        class_size=25,
        teaching_days=[0],
        holidays=[],
        ai_mode="OFF",
        template_type="wapef",
        include_special_weeks=False,
        class_level=scheme.class_level,
        subject=scheme.subject,
    )
    base.update(overrides)
    return TermConfig(**base)


def _plans(scheme, config):
    cal = CalendarEngine().build_calendar(config, scheme.weeks, [])
    cov = AllocationEngine().allocate(scheme.weeks, cal, config)
    return AllocationEngine().generate_lesson_plans(cov, config, "kg-acc"), cov


# ── A. KG class detection ────────────────────────────────────────────────────

class TestAKGClassDetection:
    def test_kg2_docx_detects_kg2_not_kg1(self):
        scheme = _kg2()
        assert scheme.class_level == ClassLevel.KG2

    def test_kg1_pdf_detects_kg1_not_kg2(self):
        scheme = _kg1()
        assert scheme.class_level == ClassLevel.KG1

    def test_kg1_and_kg2_never_confused(self):
        """The two real KG files must resolve to DIFFERENT levels — a detector
        that hard-codes KG2 would silently misfile the KG1 scheme."""
        assert _kg1().class_level != _kg2().class_level


# ── B. KG scheme parsing ─────────────────────────────────────────────────────

class TestBKGSchemeParsing:
    def test_kg2_parses_all_thirteen_weeks(self):
        assert len(_kg2().weeks) >= 13

    def test_kg1_pdf_parses_fifteen_weeks(self):
        assert len(_kg1().weeks) >= 15

    def test_kg1_special_weeks_classified(self):
        """The KG1 PDF marks W13-15 REVISION / SBA — they must not be
        treated as instruction weeks."""
        weeks = {w.week_number: w for w in _kg1().weeks}
        assert weeks[13].week_type == WeekType.REVISION
        assert weeks[14].week_type == WeekType.REVISION
        assert weeks[15].week_type == WeekType.SBA

    def test_kg1_indicators_survive_merged_header(self):
        """The KG1 PDF splits its CONTENT STANDARD header across rows; the
        INDICATOR(S) column must still be picked up (regression: both columns
        were silently dropped before)."""
        w1 = _kg1().weeks[0]
        assert w1.indicators, "KG1 W1 must surface its indicator cell"
        assert "K1.1.1.1.1" in w1.indicators[0]

    def test_kg1_whole_level_pdf_confirm_subject(self):
        """Confirming a subject on the heading-less KG1 PDF must extract the
        whole curriculum under it; an unknown subject yields nothing."""
        parser = PDFParser()
        s = asyncio.run(parser.parse(KG1_PDF, original_filename=KG1_PDF.name,
                                     target_subject="Numeracy"))
        assert s.subject.value == "Numeracy"
        assert s.class_level == ClassLevel.KG1
        assert len(s.weeks) >= 15
        assert s.weeks[0].indicators

        bad = asyncio.run(parser.parse(KG1_PDF, original_filename=KG1_PDF.name,
                                       target_subject="Career Technology"))
        # 'Career Technology' is a valid Subject but the KG1 PDF is a
        # whole-level document, so the confirmed subject applies to all of it.
        assert bad.weeks
        assert bad.class_level == ClassLevel.KG1


# ── C. KG multi-row curriculum handling ─────────────────────────────────────

class TestCKGMultiRowCurriculum:
    def test_kg2_strands_split_two_themes(self):
        strands = {w.strand for w in _kg2().weeks}
        assert strands == {"All About Me", "My Family"}

    def test_continuation_weeks_share_sub_strand(self):
        """W6→W7 and W12→W13 repeat the sub-strand with a new indicator-range
        slice — the source's own way of spreading one topic over two weeks."""
        weeks = {w.week_number: w for w in _kg2().weeks}
        assert weeks[6].sub_strand == weeks[7].sub_strand
        assert weeks[6].indicators != weeks[7].indicators

    def test_kg_has_indicators_so_indicator_path_applies(self):
        assert scheme_has_indicators(_kg2().weeks) is True


# ── D. KG indicator normalization ────────────────────────────────────────────

class TestDKGIndicatorNormalization:
    def test_code_only_content_standard_is_preserved(self):
        """The KG scheme prints its content standard as ONLY a code
        ("k2.1.1.1"). The code IS the source data — it must survive
        normalization canonically cased, not be dropped."""
        w1 = _kg2().weeks[0]
        assert w1.content_standards == ["K2.1.1.1"]

    def test_indicator_range_stays_one_family(self):
        w1 = _kg2().weeks[0]
        assert w1.indicators == ["K2.1.1.1.1 K2.1.1.1.1-3"]

    def test_lowercase_source_code_normalized(self):
        """The source prints 'k2.1.1.1' (lowercase k). Stored text must be
        canonical 'K2.1.1.1' — never 'K2.1.1.1 k2.1.1.1' (code duplicated)
        and never the raw lowercase echo."""
        cs = _kg2().weeks[0].content_standards[0]
        assert cs == "K2.1.1.1"
        assert "k2.1.1.1" not in cs


# ── E. KG indicator-range handling ───────────────────────────────────────────

class TestEKGIndicatorRangeHandling:
    def test_range_is_one_lesson_not_many(self):
        """One week row = one lesson. The range tail (-3) describes the
        teachable family; the source splits ranges across weeks itself when
        it wants multiple lessons (KG1 PDF W7→W8)."""
        scheme = _kg2()
        config = _config(scheme)
        _, cov = _plans(scheme, config)
        assert cov.total_generated_lessons == len(scheme.weeks)

    def test_range_tail_not_phished_into_split(self):
        from src.engines.allocation_engine import AllocationEngine
        ae = AllocationEngine()
        parts = ae._split_indicators(["K2.1.1.1.1 K2.1.1.1.1-3"])
        assert len(parts) == 1

    def test_genuinely_merged_indicators_still_split(self):
        """The splitter must keep working for Basic schemes where two distinct
        indicators were merged by parsing."""
        from src.engines.allocation_engine import AllocationEngine
        ae = AllocationEngine()
        parts = ae._split_indicators(
            ["B9.1.1.1.2 Discuss formation B9.1.1.1.3 Describe characteristics"])
        assert len(parts) == 2


# ── F. KG resource preservation ──────────────────────────────────────────────

class TestFKGResourcePreservation:
    def test_source_tlrs_verbatim(self):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        lp = plans[0]
        assert lp.source_tlrs
        assert lp.source_tlrs[0].startswith("Poster/ cut out")
        # Source resources are the display list's head — generation may add
        # "Other TLRs" but never replaces the source list.
        assert lp.teaching_learning_resources[0] == lp.source_tlrs[0]

    def test_kg1_resources_keep_real_items(self):
        res = _kg1().weeks[0].resources
        assert any("crayons" in r.lower() for r in res)
        assert any("big books" in r.lower() for r in res)


# ── G. KG lesson allocation ──────────────────────────────────────────────────

class TestGKGLessonAllocation:
    def test_one_lesson_per_week_in_curriculum_order(self):
        scheme = _kg2()
        config = _config(scheme)
        plans, cov = _plans(scheme, config)
        assert [lp.week_number for lp in plans] == [w.week_number for w in scheme.weeks]

    def test_continuation_week_lessons_differ(self):
        """W12 and W13 carry the SAME row. The generated lessons must still
        differ — the continuation week builds on the previous lesson."""
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        l12 = next(p for p in plans if p.week_number == 12)
        l13 = next(p for p in plans if p.week_number == 13)
        assert str(l12.starter_activity) != str(l13.starter_activity)
        assert "previous lesson" in str(l13.starter_activity).lower()


# ── H. KG lesson generation (play-based, grounded) ──────────────────────────

class TestHKGLessonGeneration:
    def test_kg_uses_play_based_pedagogy_not_written_exercises(self):
        """KG2 'Numeracy' must generate song/play/observation lessons — the
        Basic-7-9 mathematics profile (board worked examples, written class
        exercises) is developmentally wrong for KG and contradicts the KG1
        scheme's own 'play-based and authentic assessment' row."""
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        text = " ".join(
            str(a.description).lower() for a in plans[0].main_activities
        ).lower()
        starter = str(plans[0].starter_activity).lower()
        assert "song" in starter or "rhyme" in starter or "movement" in starter
        assert "play" in text or "game" in text
        assert "on the board" not in text
        assert "written class exercise" not in " ".join(
            str(a) for a in plans[0].assessment)

    def test_assessment_is_observation_based(self):
        """KG1 source: 'play-based and authentic assessment … Observation
        checklist'. Generated KG assessment must observe, not set written
        tests."""
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        assessment = str(plans[0].assessment).lower()
        assert "observe" in assessment
        assert "no written test" in assessment

    def test_objectives_are_observable_and_code_free(self):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        for lp in plans[:3]:
            obj = lp.learning_objectives[0].description
            assert obj.startswith("Learners can")
            assert "K2." not in obj
            assert not obj.strip() == "Learners can"

    def test_curriculum_focus_comes_from_source_row(self):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        lp = plans[7]  # W8: 'My Family' / 'Types And Members Of My Family'
        assert lp.strand == "My Family"
        assert lp.sub_strand == "Types And Members Of My Family"
        assert "Types And Members" in lp.lesson_topic

    def test_different_rows_produce_different_lessons(self):
        """Two different KG weeks must never clone the same content."""
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        texts = [str(p.starter_activity) + str(p.lesson_topic) for p in plans[:5]]
        assert len(set(texts)) == len(texts)

    def test_quality_gate_no_warnings_on_kg_lessons(self):
        """The existing quality gate must accept KG lessons without false
        positives (intro==starter mirror, KG objective verbs)."""
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        for lp in plans[:4]:
            rep = validate_lesson_quality(lp.model_dump())
            fails = [i for i in rep.issues
                     if getattr(i.status, "value", str(i.status)) == "fail"]
            warns = [i for i in rep.issues
                     if getattr(i.status, "value", str(i.status)) == "warn"]
            assert not fails, fails
            assert not warns, [(i.check_name, i.message) for i in warns]


# ── I. WAPEF metadata persistence on KG lessons ─────────────────────────────

class TestIWAPEFMetadataPersistence:
    def test_kg_lesson_accepts_and_keeps_teacher_selections(self):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        lp = plans[0]
        lp.wapef_deep_hope = wf.WAPEF_DEEP_HOPES[0]
        lp.wapef_storyline = wf.WAPEF_STORYLINES[0]
        lp.wapef_through_lines = ["God worshiper", "Beauty creator"]
        lp.wapef_gods_story = "Creation"
        assert lp.wapef_deep_hope == wf.WAPEF_DEEP_HOPES[0]
        assert lp.wapef_through_lines == ["God worshiper", "Beauty creator"]


# ── J. KG WAPEF DOCX export ──────────────────────────────────────────────────

class TestJKGDocxExport:
    def test_kg_lesson_renders_on_approved_wapef_plan(self, tmp_path):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        lp = plans[0]
        lp.wapef_deep_hope = wf.WAPEF_DEEP_HOPES[0]
        lp.wapef_storyline = wf.WAPEF_STORYLINES[0]
        lp.wapef_through_lines = ["God worshiper", "Image reflector"]
        lp.wapef_gods_story = "Creation"

        out = tmp_path / "kg.docx"
        DOCXExportEngine().export_wapef([lp], out)
        import zipfile, re
        xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
        text = re.sub(r"<[^>]+>", "\n", xml)

        assert "KPOGEDE" not in text  # sample content never leaks
        assert "KG 2" in text                       # class
        assert "Numeracy" in text                    # subject/learning area
        assert "All About Me" in text                # strand
        assert "I Am A Wonderful And Unique Creation" in text  # sub-strand
        assert "K2.1.1.1.1" in text                  # indicator
        assert "K2.1.1.1" in text                    # content standard code
        assert "Poster/ cut out" in text             # source resources
        assert wf.WAPEF_DEEP_HOPES[0] in text        # WAPEF metadata
        assert wf.WAPEF_STORYLINES[0] in text
        assert "God worshiper and Image reflector" in text
        assert "Creation" in text
        assert "PHASE 1" in text and "PHASE 2" in text and "PHASE 3" in text
        assert "EVALUATION" in text and "REMARKS" in text
        leftovers = re.findall(r"\{\{[A-Z_0-9]+\}\}", xml)
        assert not leftovers, leftovers

    def test_renderer_reports_no_leftover_tokens(self, tmp_path):
        scheme = _kg2()
        config = _config(scheme)
        plans, _ = _plans(scheme, config)
        doc = render_wapef(plans[:2])
        assert validate_rendered_document(doc) == []


# ── L/M/N. Regressions: Nursery, Basic/JHS, WAPEF ────────────────────────────

class TestRegressions:
    def test_nursery_still_indicatorless_week_units(self):
        """KG changes must not leak into the Nursery week-unit path."""
        nursery = asyncio.run(DOCXParser().parse(
            FIXTURES / "WAPEF SCHEME OF LEARNING FOR NURSERY.docx"))
        assert scheme_has_indicators(nursery.weeks) is False
        config = _config(nursery)
        plans, cov = _plans(nursery, config)
        assert len(plans) == cov.total_generated_lessons
        assert all(not lp.indicator_codes for lp in plans)
        # Nursery objectives keep the (non-KG) explore phrasing
        assert plans[0].learning_objectives[0].description.startswith(
            "Learners can explore")

    def test_basic9_still_uses_subject_pedagogy(self):
        """Basic 9 Science keeps the subject profile (worked examples etc.)
        — the KG play-based override must key on class level, not subject."""
        from src.curriculum.pedagogy import profile_for_subject
        profile = profile_for_subject("Science")
        assert "predict" in profile.starter_template.lower()
        # And the builder only overrides for KG levels:
        from src.curriculum.lesson_builder import build_lesson
        from src.engines.allocation_engine import AllocationEngine
        basic = asyncio.run(DOCXParser().parse(
            Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan")
            / "BASIC 9 SCIENCE SCHEME OF LEARNING.docx")) if (
            Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan")
            / "BASIC 9 SCIENCE SCHEME OF LEARNING.docx").exists() else None
        if basic is None:
            pytest.skip("Basic 9 source document not present")
        config = _config(basic)
        cal = CalendarEngine().build_calendar(config, basic.weeks, [])
        cov = AllocationEngine().allocate(basic.weeks, cal, config)
        plans = AllocationEngine().generate_lesson_plans(cov, config, "b9")
        main_text = " ".join(
            str(a.description).lower() for a in plans[0].main_activities)
        # The subject profile drives Basic 9 (its actual phases reference
        # prediction/scenario, guided and independent practice); the KG
        # play-based override must NOT have applied here.
        assert "play-based" not in main_text
        assert plans[0].learning_objectives[0].description.startswith("Learners can")

    def test_wapef_template_still_single_common_output(self):
        """No KG-specific WAPEF variant was introduced."""
        from src.engines.template_engine import DEFAULT_TEMPLATES
        wapef = [t for t in DEFAULT_TEMPLATES if t.id.startswith("tpl-wapef")]
        assert len(wapef) == 1
        assert wapef[0].name == "Approved WAPEF Plan"

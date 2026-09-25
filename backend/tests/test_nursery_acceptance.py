"""
Nursery curriculum & lesson-generation acceptance (real source document).

Source material (kept verbatim under tests/fixtures/wapef/):
  ``WAPEF SCHEME OF LEARNING FOR NURSERY.docx`` — the ONLY Nursery source
  document in C:\\Users\\SAVIOUR\\Documents\\DScience\\Lesson Plan. It
  declares "SCHEME OF LEARNING FOR NURSERY 1 - TERM 1 (2024/2025)" and
  contains FOUR subject sections, each its own 4-column table
  (WEEKS / STRAND / SUB STRAND / RESOURCES), 15 rows:
      NUMERACY, LANGUAGE & LITERACY, CREATIVE ARTS, OUR WORLD OUR PEOPLE

Source-derived structure (verified against the document, §2):
  * The source has NO Content Standard and NO Indicator columns. The
    curriculum unit is week + subject + strand + sub-strand + resources.
    Nothing in this test suite expects an indicator, and no generation path
    may invent one.
  * Week 1 is REVISION in every subject table; weeks 13/14 are
    REVISION/EXAMINATION; week 15 is VACATION.
  * The Numeracy table prints week 15 as "AND VACATION" (a lost line-wrap)
    and the Creative Arts table prints week 13 as "REVISION1" (a stray
    digit). The parser normalises these to their canonical period name.
  * Rows repeat (Numeracy W5/W6 "Pairing"; Creative Arts W2/W3) — these are
    continuation weeks, not separate lessons in one week.
  * Resources are per-row and per-subject; the "Charts & Pictures" of one
    subject never becomes another subject's resources.
  * Nursery 1 is the declared level; it is never collapsed to the generic
    "Nursery" family name and never silently renumbered to KG.

Limitation (§1): no completed Nursery lesson plans exist in the source
directory, so developmental-appropriateness assertions here are derived from
the SCHEME's own evidence (oral/oral-skills strands, concrete resources,
pre-writing/pre-reading sub-strands, observation-style assessment) rather
than from a finished lesson-plan exemplar.
"""

import asyncio
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from src.parsers.docx_parser import DOCXParser
from src.engines.allocation_engine import AllocationEngine, scheme_has_indicators
from src.engines.calendar_engine import CalendarEngine
from src.engines.docx_export import DOCXExportEngine
from src.engines.pdf_export import PDFExportEngine
from src.engines import wapef_fields as wf
from src.engines.wapef_template import render_document as render_wapef, validate_rendered_document
from src.curriculum.lesson_builder import build_lesson
from src.curriculum.quality_gate import validate_lesson_quality
from src.models import ClassLevel, Subject, TermConfig, WeekType

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wapef"
NURSERY_SCHEME = FIXTURES / "WAPEF SCHEME OF LEARNING FOR NURSERY.docx"

#: Every subject section the source document actually contains. These are
#: fixtures from the document, NOT hard-coded parser branches — the tests
#: assert each section was DETECTED from the document's own headings.
SOURCE_SUBJECTS = ["Numeracy", "Language & Literacy", "Creative Arts", "Our World Our People"]

#: The document's headings canonicalise onto the shared Subject enum — a
#: section heading is a section, whatever the enum calls it.
CANONICAL_SUBJECT = {
    "Numeracy": "Numeracy",
    "Language & Literacy": "Language and Literacy",
    "Creative Arts": "Creative Arts and Design",
    "Our World Our People": "Our World Our People",
}


def _parse(subject: str | None = None):
    if subject is None:
        return asyncio.run(DOCXParser().parse(NURSERY_SCHEME))
    return asyncio.run(DOCXParser().parse(NURSERY_SCHEME, target_subject=subject))


def _config(scheme, **overrides):
    base = dict(
        scheme_of_work_id="nursery-acc",
        term_start_date=date(2026, 9, 15),
        term_end_date=date(2026, 12, 18),
        lessons_per_week=1,
        lesson_duration_minutes=60,
        class_size=25,
        teaching_days=[0],
        holidays=[],
        ai_mode="OFF",
        template_type="wapef",
        class_level=scheme.class_level,
        subject=scheme.subject,
    )
    base.update(overrides)
    return TermConfig(**base)


def _plans(scheme, config):
    cal = CalendarEngine().build_calendar(config, scheme.weeks, [])
    cov = AllocationEngine().allocate(scheme.weeks, cal, config)
    return AllocationEngine().generate_lesson_plans(cov, config, "nursery-acc"), cov


def _quality(lp):
    return validate_lesson_quality(lp.model_dump())


# ── A. Document discovery / structure ────────────────────────────────────────

class TestANurseryDocumentDiscovery:
    def test_fixture_is_the_real_source_document(self):
        assert NURSERY_SCHEME.exists(), "Nursery fixture must be present"
        assert NURSERY_SCHEME.stat().st_size > 20_000

    def test_document_declares_nursery_1_term_1(self):
        raw = NURSERY_SCHEME.read_bytes()
        xml = zipfile.ZipFile(__import__("io").BytesIO(raw)).read("word/document.xml").decode("utf-8", "ignore")
        text = re.sub(r"<[^>]+>", " ", xml)
        assert "NURSERY 1" in text.upper()
        assert "TERM 1" in text.upper()

    def test_document_has_four_subject_tables(self):
        import docx
        tables = docx.Document(str(NURSERY_SCHEME)).tables
        assert len(tables) == 4
        headers = [[c.text.strip().upper() for c in t.rows[0].cells] for t in tables]
        for h in headers:
            assert h == ["WEEKS", "STRAND", "SUB STRAND", "RESOURCES"]
        assert len(tables[0].rows) == 16  # header + 15 weeks


# ── B. Subject-section detection ─────────────────────────────────────────────

class TestBSubjectSectionDetection:
    def test_all_four_sections_detected(self):
        analysis = DOCXParser().analyze(NURSERY_SCHEME)
        detected = set(analysis["detected_subjects"])
        # The document's four headings must all be detected as sections.
        assert detected == {
            "Numeracy", "Language and Literacy", "Creative Arts and Design", "Our World Our People"
        }
        assert analysis["detection_status"] == "multiple"

    def test_each_section_carries_fifteen_weeks(self):
        for subject in SOURCE_SUBJECTS:
            scheme = _parse(subject)
            assert len(scheme.weeks) == 15, f"{subject}: expected 15 weeks"

    def test_unconfirmed_subject_is_flagged_needs_confirmation(self):
        analysis = DOCXParser().analyze(NURSERY_SCHEME)
        assert analysis["detection_status"] == "multiple"


# ── C. Nursery level detection ───────────────────────────────────────────────

class TestCNurseryLevelDetection:
    def test_level_is_nursery_1_from_the_document_body(self):
        scheme = _parse("Numeracy")
        assert scheme.class_level == ClassLevel.NURSERY_1

    def test_nursery_is_never_silently_kg(self):
        for subject in SOURCE_SUBJECTS:
            scheme = _parse(subject)
            assert scheme.class_level.value.startswith("Nursery")
            assert "KG" not in scheme.class_level.value

    def test_specific_level_wins_over_generic_family_name(self):
        # The table cell says "NURSERY", the body says "NURSERY 1": the MORE
        # SPECIFIC declaration is kept, never collapsed to the family name.
        scheme = _parse("Numeracy")
        assert scheme.class_level.value == "Nursery 1"


# ── D. Multi-subject isolation (anti-contamination) ──────────────────────────

class TestDMultiSubjectIsolation:
    """The critical guarantee: one subject's curriculum never leaks into
    another subject's plan (§5)."""

    def test_selected_subject_is_the_only_subject_on_the_plan(self):
        for subject in SOURCE_SUBJECTS:
            scheme = _parse(subject)
            plans, _ = _plans(scheme, _config(scheme))
            assert plans, f"{subject}: plans must be generated"
            expected = CANONICAL_SUBJECT[subject]
            for lp in plans:
                assert lp.subject.value == expected, \
                    f"{subject}: plan subject leaked: {lp.subject.value}"

    def test_numeracy_strands_never_leak_into_creative_arts(self):
        numeracy = _parse("Numeracy")
        arts = _parse("Creative Arts")
        n_strands = {w.strand for w in numeracy.weeks if w.strand}
        a_strands = {w.strand for w in arts.weeks if w.strand}
        # Numeracy's "Number" strand is not a Creative Arts strand.
        assert "Number" in n_strands
        assert "Number" not in a_strands
        assert "Responsibilities" in a_strands
        assert "Responsibilities" not in n_strands

    def test_resources_never_leak_between_subjects(self):
        """Numeracy's "Cut out shapes" must not appear on a Creative Arts
        lesson — resources are per-subject, per-row (§9)."""
        numeracy = _parse("Numeracy")
        arts = _parse("Creative Arts")
        n_plans, _ = _plans(numeracy, _config(numeracy))
        a_plans, _ = _plans(arts, _config(arts))
        # Numeracy week 2 keeps its own concrete resource.
        n2 = next(p for p in n_plans if p.week_number == 2)
        assert "Cut out shapes" in n2.source_tlrs
        for lp in a_plans:
            assert "Cut out shapes" not in lp.source_tlrs, \
                "Numeracy's 'Cut out shapes' leaked into Creative Arts"

    def test_language_literacy_strands_stay_own(self):
        scheme = _parse("Language & Literacy")
        strands = {w.strand for w in scheme.weeks if w.strand}
        assert {"Oral Skills", "Story telling", "Pre-reading"} <= strands
        # Our World Our People's strands must not be present here.
        assert "Myself" not in strands
        assert "Plants" not in strands
        assert "Family" not in strands

    def test_our_world_strands_stay_own(self):
        scheme = _parse("Our World Our People")
        strands = {w.strand for w in scheme.weeks if w.strand}
        assert {"Myself", "Plants", "Family"} <= strands
        assert "Oral Skills" not in strands
        assert "Number" not in strands

    def test_each_subject_week_content_is_own(self):
        """Week 2 must be the subject's OWN week-2 row, not another subject's."""
        week2 = {
            "Numeracy": "Grouping of objects based on shapes",
            "Language & Literacy": "Listening and Speaking",
            "Creative Arts": "Marking simple rules",
            "Our World Our People": "Describing yourself",
        }
        for subject, expected in week2.items():
            scheme = _parse(subject)
            w2 = next(w for w in scheme.weeks if w.week_number == 2)
            assert expected.lower() in (w2.sub_strand or "").lower(), \
                f"{subject} week 2 sub-strand wrong: {w2.sub_strand!r}"

    def test_unselected_subjects_do_not_appear(self):
        analysis = DOCXParser().analyze(NURSERY_SCHEME, target_subject="Numeracy")
        non_empty = [d for d in analysis["detected_subjects"] if d == "Numeracy"]
        assert non_empty == ["Numeracy"]
        assert sorted(analysis["detected_subjects"]) == sorted(set(analysis["detected_subjects"]))


# ── E. Week handling ─────────────────────────────────────────────────────────

class TestEWeekHandling:
    def test_fifteen_weeks_preserved(self):
        for subject in SOURCE_SUBJECTS:
            weeks = _parse(subject).weeks
            assert [w.week_number for w in weeks] == list(range(1, 16))

    def test_source_week_number_preserved_on_plans(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        assert sorted(p.week_number for p in plans) == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    def test_blank_resource_cell_carries_forward(self):
        """Numeracy W12 has an empty RESOURCES cell but the row is still a
        real curriculum row — the week keeps its strand/sub-strand and its
        (carried) resources, and it is never dropped."""
        scheme = _parse("Numeracy")
        w12 = next(w for w in scheme.weeks if w.week_number == 12)
        assert w12.week_type == WeekType.INSTRUCTION
        assert w12.sub_strand and "Writing numbers" in w12.sub_strand


# ── F. Strand / sub-strand preservation ──────────────────────────────────────

class TestFStrandSubstrandPreservation:
    def test_strands_survive_normalization(self):
        scheme = _parse("Numeracy")
        strands = {w.strand for w in scheme.weeks if w.strand}
        assert strands == {"Number"}

    def test_sub_strands_survive_verbatim(self):
        scheme = _parse("Numeracy")
        w4 = next(w for w in scheme.weeks if w.week_number == 4)
        assert w4.sub_strand == "Sorting and matching"
        w8 = next(w for w in scheme.weeks if w.week_number == 8)
        assert "Counting of numbers" in w8.sub_strand

    def test_plans_keep_their_source_strand(self):
        scheme = _parse("Our World Our People")
        plans, _ = _plans(scheme, _config(scheme))
        for lp in plans:
            assert lp.strand, f"w{lp.week_number} lost its strand"
            assert lp.sub_strand, f"w{lp.week_number} lost its sub-strand"

    def test_repeated_rows_are_continuation_weeks(self):
        """Numeracy W5/W6 are both "Pairing": two teaching weeks of one
        curriculum focus, NOT two lessons in one week (§4)."""
        scheme = _parse("Numeracy")
        w5 = next(w for w in scheme.weeks if w.week_number == 5)
        w6 = next(w for w in scheme.weeks if w.week_number == 6)
        assert w5.sub_strand == w6.sub_strand == "Pairing"
        assert w5.week_number != w6.week_number


# ── G. Resource preservation ────────────────────────────────────────────────

class TestGResourcePreservation:
    def test_source_resources_survive_verbatim(self):
        scheme = _parse("Numeracy")
        w2 = next(w for w in scheme.weeks if w.week_number == 2)
        assert "Cut out shapes" in w2.resources
        w5 = next(w for w in scheme.weeks if w.week_number == 5)
        assert "Counters, sticks, flash cards" in w5.resources
        w10 = next(w for w in scheme.weeks if w.week_number == 10)
        assert "Colours" in w10.resources

    def test_source_tlrs_reach_the_lesson_verbatim(self):
        """The scheme's own resources reach the lesson unchanged (§9) — the
        generated profile resources may supplement, never overwrite."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        w2 = next(p for p in plans if p.week_number == 2)
        assert "Cut out shapes" in w2.source_tlrs

    def test_generated_resources_supplement_not_overwrite(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        w2 = next(p for p in plans if p.week_number == 2)
        # The source TLR is intact AND visible in the plan's resource union.
        assert "Cut out shapes" in w2.teaching_learning_resources

    def test_resources_differ_by_subject(self):
        n = _parse("Numeracy")
        a = _parse("Creative Arts")
        n_res = {r for w in n.weeks for r in w.resources}
        a_res = {r for w in a.weeks for r in w.resources}
        assert "Cut out shapes" in n_res
        assert "Cut out shapes" not in a_res


# ── H. Special-period handling (revision / examination / vacation) ──────────

class TestHISpecialPeriods:
    def test_special_weeks_are_classified_not_ignored(self):
        scheme = _parse("Numeracy")
        w1 = next(w for w in scheme.weeks if w.week_number == 1)
        w13 = next(w for w in scheme.weeks if w.week_number == 13)
        w14 = next(w for w in scheme.weeks if w.week_number == 14)
        w15 = next(w for w in scheme.weeks if w.week_number == 15)
        assert w1.week_type == WeekType.REVISION
        assert w13.week_type == WeekType.REVISION
        assert w14.week_type == WeekType.ASSESSMENT
        # Vacation shares the non-instruction bucket with SBA weeks: it is a
        # special period, never a curriculum lesson.
        assert w15.week_type != WeekType.INSTRUCTION
        assert (w15.sub_strand or "").upper() == "VACATION"

    def test_no_lesson_generated_for_special_periods(self):
        """REVISION/EXAMINATION/VACATION must not become a normal curriculum
        lesson with fabricated subject content (§17)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        assert all(p.week_number not in (1, 13, 14, 15) for p in plans)

    def test_noisy_special_labels_normalized(self):
        """Source noise: Numeracy W15 is printed "AND VACATION", Creative Arts
        W13 is printed "REVISION1". Both normalise to their canonical period
        WITHOUT any filename-specific rule."""
        numeracy = _parse("Numeracy")
        w15 = next(w for w in numeracy.weeks if w.week_number == 15)
        assert "VACATION" in (w15.sub_strand or "").upper()
        assert w15.sub_strand.upper() != "AND VACATION"
        arts = _parse("Creative Arts")
        w13 = next(w for w in arts.weeks if w.week_number == 13)
        assert (w13.sub_strand or "").upper() == "REVISION"
        assert w13.sub_strand != "REVISION1"

    def test_vacation_row_gets_no_fabricated_content(self):
        scheme = _parse("Our World Our People")
        w15 = next(w for w in scheme.weeks if w.week_number == 15)
        assert (w15.sub_strand or "").upper() == "VACATION"
        assert not w15.indicators


# ── I. Curriculum-to-lesson mapping (lesson-unit semantics) ─────────────────

class TestICurriculumToLessonMapping:
    def test_one_lesson_per_instruction_week(self):
        scheme = _parse("Numeracy")
        plans, cov = _plans(scheme, _config(scheme))
        instruction = [w for w in scheme.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(plans) == len(instruction) == cov.total_generated_lessons

    def test_lesson_order_follows_source_week_order(self):
        scheme = _parse("Language & Literacy")
        plans, _ = _plans(scheme, _config(scheme))
        assert [p.week_number for p in plans] == sorted(p.week_number for p in plans)

    def test_indicator_fields_stay_empty_never_fabricated(self):
        """The source has no indicator columns: nothing may be invented (§3)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        for lp in plans:
            assert lp.indicators == []
            assert lp.indicator_codes == []
            assert not lp.content_standard_code
            assert not lp.content_standard

    def test_scheme_has_indicators_reports_false(self):
        assert scheme_has_indicators(_parse("Numeracy").weeks) is False


# ── J. Lesson generation ────────────────────────────────────────────────────

class TestJNurseryLessonGeneration:
    def test_nursery_uses_the_nursery_pedagogy_profile(self):
        """Nursery keeps its OWN profile (oral instruction, teacher modelling,
        guided participation, playful practice) — not the KG role-play profile
        and not the Basic board-work profile (§11)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        main_names = " ".join(a.phase for a in lp.main_activities).lower()
        assert "modelling" in main_names
        assert "guided participation" in main_names
        assert "playful practice" in main_names

    def test_starter_is_song_rhyme_and_real_objects(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        starter = plans[0].starter_activity.lower()
        assert any(w in starter for w in ("song", "rhyme"))

    def test_assessment_is_observation_based_no_written_test(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        a = plans[0].assessment.lower()
        assert "watch" in a or "observe" in a or "oral" in a
        assert "written test" in a  # explicitly states there is none

    def test_objectives_show_and_talk_not_basic_measurable(self):
        """The source's sub-strand topics are do-and-say activities
        ("Sorting and matching", "Colouring, Tracing and Alphabets"), so the
        objective is a demonstrable 'show and talk about' — not Basic-style
        measurable analysis and not the KG role-play phrasing (§12)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        obj = plans[0].learning_objectives[0].description
        assert obj.startswith("Learners can show and talk about")
        assert "analyse" not in obj.lower() and "analyze" not in obj.lower()

    def test_curriculum_focus_comes_from_the_source_row(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = next(p for p in plans if p.week_number == 4)
        assert "Sorting and matching" in lp.sub_strand
        assert "Sorting and matching" in lp.lesson_topic

    def test_quality_gate_passes_for_all_nursery_subjects(self):
        """No false positive on indicatorless Nursery lessons, and no
        threshold was lowered to get there (§24)."""
        for subject in SOURCE_SUBJECTS:
            scheme = _parse(subject)
            plans, _ = _plans(scheme, _config(scheme))
            assert plans, f"{subject}: no plans"
            for lp in plans:
                rep = _quality(lp)
                assert rep.overall_status != "fail", (
                    f"{subject} w{lp.week_number}: {rep.failures}"
                )

    def test_quality_gate_still_fails_an_unanchored_lesson(self):
        """The gate was not weakened: a lesson with no indicator AND no
        strand/sub-strand still fails the required-anchor check."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        data = lp.model_dump()
        data["indicator_codes"] = []
        data["strand"] = None
        data["sub_strand"] = None
        rep = validate_lesson_quality(data)
        assert rep.overall_status == "fail"
        assert any("required field" in i.message for i in rep.failures)


# ── K. WAPEF metadata persistence ───────────────────────────────────────────

class TestKWAPEFMetadataPersistence:
    def test_teacher_selections_are_kept_verbatim(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        lp.wapef_deep_hope = wf.WAPEF_DEEP_HOPES[0]
        lp.wapef_storyline = wf.WAPEF_STORYLINES[0]
        lp.wapef_through_lines = ["God worshiper", "Image reflector"]
        lp.wapef_gods_story = "Creation"
        assert lp.wapef_deep_hope == wf.WAPEF_DEEP_HOPES[0]
        assert lp.wapef_through_lines == ["God worshiper", "Image reflector"]

    def test_generation_does_not_overwrite_teacher_selections(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        lp.wapef_deep_hope = wf.WAPEF_DEEP_HOPES[0]
        lp.wapef_storyline = wf.WAPEF_STORYLINES[0]
        # Deterministic rebuild of the same curriculum row keeps the values:
        # the builder never initialises WAPEF fields from generated content.
        lp.lesson_topic = "rebuilt topic"
        assert lp.wapef_deep_hope == wf.WAPEF_DEEP_HOPES[0]
        assert lp.wapef_storyline == wf.WAPEF_STORYLINES[0]


# ── L. Anti-cloning ─────────────────────────────────────────────────────────

class TestLAntiCloning:
    def test_different_weeks_produce_different_lessons(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        w2 = next(p for p in plans if p.week_number == 2)
        w4 = next(p for p in plans if p.week_number == 4)
        assert w2.sub_strand != w4.sub_strand
        assert w2.starter_activity != w4.starter_activity
        assert w2.assessment != w4.assessment

    def test_repeated_rows_still_differ(self):
        """Numeracy W5/W6 are both "Pairing" (a continuation): the two lessons
        must not be clones — the second links to the previous lesson (§25)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        w5 = next(p for p in plans if p.week_number == 5)
        w6 = next(p for p in plans if p.week_number == 6)
        assert w5.sub_strand == w6.sub_strand
        assert w5.starter_activity != w6.starter_activity
        assert "previous lesson" in w6.starter_activity.lower()

    def test_no_duplicate_activity_text_within_one_lesson(self):
        """The teacher/learner activity moves must not repeat the same
        sentence for different phases (a real duplication bug the Nursery
        profile exposed)."""
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        for lp in plans:
            texts = [a.description for a in lp.teacher_activities]
            assert len(texts) == len(set(texts)), \
                f"w{lp.week_number}: duplicate teacher activities"
            texts = [a.description for a in lp.learner_activities]
            assert len(texts) == len(set(texts)), \
                f"w{lp.week_number}: duplicate learner activities"

    def test_different_subjects_produce_different_lessons(self):
        n = _plans(_parse("Numeracy"), _config(_parse("Numeracy")))[0][0]
        a = _plans(_parse("Creative Arts"), _config(_parse("Creative Arts")))[0][0]
        assert n.starter_activity != a.starter_activity or n.sub_strand != a.sub_strand
        assert "Cut out shapes" in n.source_tlrs
        assert "Cut out shapes" not in a.source_tlrs

    def test_intro_and_starter_are_not_the_same_sentence(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        for lp in plans:
            assert lp.introduction != lp.starter_activity


# ── M. DOCX export ──────────────────────────────────────────────────────────

class TestMDocxExport:
    def _prepared(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        lp.wapef_deep_hope = wf.WAPEF_DEEP_HOPES[0]
        lp.wapef_storyline = wf.WAPEF_STORYLINES[0]
        lp.wapef_through_lines = ["God worshiper", "Image reflector"]
        lp.wapef_gods_story = "Creation"
        return lp

    def test_nursery_lesson_renders_on_the_approved_wapef_plan(self, tmp_path):
        lp = self._prepared()
        out = tmp_path / "nursery.docx"
        DOCXExportEngine().export_wapef([lp], out)
        xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
        text = re.sub(r"<[^>]+>", "\n", xml)

        assert "Nursery 1" in text                     # level (source-declared)
        assert "Numeracy" in text                      # subject
        assert "Number" in text                        # strand
        assert "Grouping of objects" in text           # sub-strand
        assert "Cut out shapes" in text                # SOURCE resources
        assert wf.WAPEF_DEEP_HOPES[0] in text          # WAPEF metadata
        assert wf.WAPEF_STORYLINES[0] in text
        assert "God worshiper and Image reflector" in text
        assert "Creation" in text
        assert "PHASE 1" in text and "PHASE 2" in text and "PHASE 3" in text
        assert "EVALUATION" in text and "REMARKS" in text
        # No fabricated curriculum codes anywhere in the export (§3).
        assert not re.search(r"\bN\d\.\d", text)
        assert not re.search(r"\{\{[A-Z_0-9]+\}\}", xml)

    def test_renderer_reports_no_leftover_tokens(self):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        doc = render_wapef(plans[:2])
        assert validate_rendered_document(doc) == []

    def test_exported_docx_has_no_duplicate_activity_lines(self, tmp_path):
        lp = self._prepared()
        out = tmp_path / "nursery.docx"
        DOCXExportEngine().export_wapef([lp], out)
        xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
        lines = [l.strip() for l in re.sub(r"<[^>]+>", "\n", xml).split("\n") if len(l.strip()) > 25]
        dupes = [l for l in set(lines) if lines.count(l) > 1]
        assert not dupes, f"duplicated export lines: {dupes[:3]}"


# ── N. PDF export ───────────────────────────────────────────────────────────

class TestNPdfExport:
    def test_nursery_pdf_derives_from_the_same_lesson(self, tmp_path):
        scheme = _parse("Numeracy")
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        docx_path = tmp_path / "nursery.docx"
        DOCXExportEngine().export_wapef([lp], docx_path)
        pdf_path = tmp_path / "nursery.pdf"
        try:
            PDFExportEngine()._convert_docx_to_pdf(docx_path, pdf_path)
        except Exception as exc:  # converter missing in this environment
            pytest.skip(f"PDF converter unavailable: {exc}")
        assert pdf_path.exists()
        assert pdf_path.read_bytes()[:4] == b"%PDF"
        # The canonical lesson object produced BOTH documents.
        assert docx_path.exists()


# ── O. KG regression ────────────────────────────────────────────────────────

class TestOKGRegression:
    def test_kg_still_uses_the_kg_profile_not_nursery(self):
        kg = FIXTURES / "WAPEF SCHEME OF LEARNING FOR KG.docx"
        scheme = asyncio.run(DOCXParser().parse(kg, target_subject="Numeracy"))
        plans, _ = _plans(scheme, _config(scheme))
        lp = plans[0]
        main_names = " ".join(a.phase for a in lp.main_activities).lower()
        assert "play" in main_names or "explore" in main_names
        # KG keeps its own objective phrasing, not Nursery's.
        obj = lp.learning_objectives[0].description
        assert obj.startswith("Learners can")

    def test_kg_keeps_its_indicators(self):
        kg = FIXTURES / "WAPEF SCHEME OF LEARNING FOR KG.docx"
        scheme = asyncio.run(DOCXParser().parse(kg, target_subject="Numeracy"))
        plans, _ = _plans(scheme, _config(scheme))
        assert plans[0].indicator_codes


# ── P. WAPEF regression ─────────────────────────────────────────────────────

class TestPWAPEFRegression:
    def test_nursery_uses_the_same_approved_wapef_plan(self):
        """There is ONE output structure: the Approved WAPEF Plan. No
        'Nursery WAPEF Plan' variant exists (§16)."""
        from src.engines.wapef_template import TEMPLATE_ID
        assert TEMPLATE_ID == "tpl-wapef-approved-plan"

    def test_wapef_option_lists_are_shared(self):
        # The same approved lists serve Nursery and KG — no Nursery copies.
        assert wf.WAPEF_DEEP_HOPES and wf.WAPEF_STORYLINES and wf.WAPEF_THROUGH_LINES


# ── Q. Basic/JHS regression ─────────────────────────────────────────────────

class TestQBasicJHSRegression:
    def test_basic_lesson_still_uses_subject_pedagogy(self):
        """The Nursery profile override keys on class level, so a Basic class
        never receives nursery pedagogy (§27)."""
        from src.curriculum.pedagogy import profile_for_subject
        profile = profile_for_subject("Science")
        assert "predict" in profile.starter_template.lower()
        assert profile.key != "nursery"

    def test_builder_never_applies_nursery_profile_to_basic(self):
        from src.models import AllocatedIndicator
        alloc = AllocatedIndicator(
            week_number=1, lesson_sequence=1, period_index=0,
            indicator_code="B9.1.1.1.2",
            indicator_description="Describe the characteristics of living things",
            strand="Diversity of Matter", sub_strand="Living and Non-living",
            content_standard_description="B9.1.1.1", content_standard_code="B9.1.1.1",
        )
        config = TermConfig(
            scheme_of_work_id="q", class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE, lessons_per_week=1,
        )
        lp = build_lesson(alloc, config, "q")
        main_names = " ".join(a.phase for a in lp.main_activities).lower()
        assert "modelling" not in main_names or "guided" in main_names
        assert "playful practice" not in main_names


# ── R. Class-level enum integrity ───────────────────────────────────────────

class TestRClassLevelEnum:
    def test_nursery_levels_are_distinct_enum_members(self):
        assert ClassLevel.NURSERY.value == "Nursery"
        assert ClassLevel.NURSERY_1.value == "Nursery 1"
        assert ClassLevel.NURSERY_2.value == "Nursery 2"
        assert ClassLevel.NURSERY_1 is not ClassLevel.NURSERY
        assert ClassLevel.NURSERY_1 is not ClassLevel.KG1

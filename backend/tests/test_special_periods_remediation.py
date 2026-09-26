"""
Special-period regression tests (PART O–S of the template/lesson remediation).

A special period (MID-TERM, REVISION, EXAMINATION, VACATION) is NOT curriculum
content. Its source label must never become a strand, sub-strand, content
standard, indicator, objective or lesson topic; it must never generate a fake
lesson or consume a lesson-generation unit. A REVISION week WITH actual teaching
content stays instructional (PART S).
"""
from datetime import date

import pytest

from src.models import (
    ClassLevel, SpecialPeriodType, Subject, TermConfig, Week, WeekType,
)
from src.engines.allocation_engine import AllocationEngine, reclassify_special_weeks
from src.engines.calendar_engine import CalendarEngine
from src.parsers.docx_parser import SPECIAL_WEEK_KEYWORDS, DOCXParser


def _config(**kw):
    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=kw.pop("class_level", ClassLevel.BASIC_8),
        subject=kw.pop("subject", Subject.SCIENCE),
        term_start_date=date(2026, 10, 26), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60,
        teaching_days=kw.pop("teaching_days", [0, 1, 2, 3, 4]),
        holidays=[], **kw,
    )


def _week(num, indicators=None, week_type=WeekType.INSTRUCTION,
          strand=None, sub_strand=None, resources=None, label="", ptype=""):
    return Week(
        week_number=num, start_date=date(2026, 10, 26), end_date=date(2026, 10, 30),
        week_type=week_type, strand=strand, sub_strand=sub_strand,
        indicators=list(indicators or []),
        content_standards=["B8.1.1.1 Standard"] if indicators else [],
        resources=list(resources or []),
        special_period_label=label, special_period_type=ptype,
        scheme_of_work_id="s",
    )


def _allocate(weeks, include_special=False):
    config = _config()
    calendar = CalendarEngine().build_calendar(config, weeks, [])
    return AllocationEngine().allocate(
        weeks, calendar, config, include_special
    ), config


# ── Parser-level classification (PART O/P) ───────────────────────────────────

class TestSpecialPeriodDetection:
    def test_midterm_keyword_is_special(self):
        assert "mid-term" in SPECIAL_WEEK_KEYWORDS
        parser = DOCXParser()
        assert parser._is_special_week_text("MID-TERM (05-11-2026 to 06-11-2026)")
        assert parser._is_special_week_text("Mid Term")
        assert parser._is_special_week_text("MIDTERM")
        assert parser._is_special_week_text("half-term")
        assert not parser._is_special_week_text("Photosynthesis and respiration")

    def test_midterm_not_matched_as_week_number(self):
        """'MID-TERM (05-11-2026 ...)' must never parse as 'Week 5' via its
        parenthesised date digits (PART O)."""
        parser = DOCXParser()
        assert parser._extract_week_info("MID-TERM (05-11-2026 to 06-11-2026)") is None
        assert parser._extract_week_info("REVISION 1") is None

    def test_normalized_label_preserves_dates(self):
        """The verbatim source label (with dates) is preserved as metadata."""
        parser = DOCXParser()
        label = parser._normalize_special_week_label(
            "MID-TERM (05-11-2026 to 06-11-2026)")
        assert label.startswith("MID-TERM")
        assert "05-11-2026" in label

    def test_classification_types(self):
        assert SpecialPeriodType.classify(
            "MID-TERM (05-11-2026 to 06-11-2026)") is SpecialPeriodType.MID_TERM
        assert SpecialPeriodType.classify("REVISION") is SpecialPeriodType.REVISION
        assert SpecialPeriodType.classify("END OF TERM EXAM") is SpecialPeriodType.EXAMINATION
        assert SpecialPeriodType.classify("VACATION") is SpecialPeriodType.VACATION


class TestReclassifyStaleWeeks:
    """Defensive net: weeks persisted before the parser fix are re-classified
    at allocation time instead of becoming fake lessons (PART O)."""

    def test_stale_instruction_midterm_week_is_reclassified(self):
        week = _week(5, indicators=["MID-TERM (05-11-2026 to 06-11-2026)"],
                     strand="MID-TERM (05-11-2026 to 06-11-2026)",
                     sub_strand="MID-TERM (05-11-2026 to 06-11-2026)")
        assert week.week_type == WeekType.INSTRUCTION
        reclassify_special_weeks([week])
        assert week.week_type != WeekType.INSTRUCTION
        assert week.special_period_label.startswith("MID-TERM")
        assert week.special_period_type == SpecialPeriodType.MID_TERM.value
        # Curriculum fields cleared — the label is metadata, never content.
        assert week.strand is None
        assert week.sub_strand is None
        assert week.indicators == []
        # Content-standard cells that genuinely carry curriculum text are
        # preserved; only label cells are cleared.
        assert all("MID-TERM" not in c for c in week.content_standards)

    def test_normal_instruction_week_untouched(self):
        week = _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                     strand="Diversity", sub_strand="Classification")
        reclassify_special_weeks([week])
        assert week.week_type == WeekType.INSTRUCTION
        assert week.strand == "Diversity"
        assert week.special_period_label == ""


# ── Allocation / generation rules (PART Q/S) ─────────────────────────────────

class TestSpecialPeriodAllocation:
    def test_midterm_generates_no_lesson(self):
        weeks = [
            _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                  strand="Diversity", sub_strand="Classification"),
            _week(2, week_type=WeekType.OTHER,
                  label="MID-TERM (05-11-2026 to 06-11-2026)",
                  ptype=SpecialPeriodType.MID_TERM.value),
            _week(3, indicators=["B8.1.1.2 Observe micro-organisms"],
                  strand="Diversity", sub_strand="Micro-organisms"),
        ]
        coverage, _ = _allocate(weeks)
        assert coverage.total_generated_lessons == 2
        assert all(
            not getattr(a, "is_special_period", False)
            or not a.indicator_code
            for a in coverage.allocations
        )
        # No MID-TERM string anywhere in the curriculum fields of allocations.
        for a in coverage.allocations:
            for field in (a.strand, a.sub_strand, a.content_standard_description,
                          a.indicator_description):
                assert "MID-TERM" not in (field or "")

    def test_midterm_metadata_row_for_review_ui(self):
        """When special weeks are included the review table still shows the
        period as metadata (PART R) — without creating a lesson unit."""
        weeks = [
            _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                  strand="Diversity", sub_strand="Classification"),
            _week(2, week_type=WeekType.OTHER,
                  label="MID-TERM (05-11-2026 to 06-11-2026)",
                  ptype=SpecialPeriodType.MID_TERM.value),
        ]
        coverage, _ = _allocate(weeks, include_special=True)
        specials = [a for a in coverage.allocations if a.is_special_period]
        assert len(specials) == 1
        assert specials[0].special_period_label.startswith("MID-TERM")
        assert specials[0].indicator_code == ""
        # The metadata row takes no lesson sequence and no lesson count.
        assert coverage.total_generated_lessons == 1

    def test_midterm_consumes_no_quota_unit(self):
        """A special period must not decrement the lesson-generation quota
        merely by appearing in the scheme (PART S)."""
        weeks_with = [
            _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                  strand="Diversity", sub_strand="Classification"),
            _week(2, week_type=WeekType.OTHER,
                  label="MID-TERM (05-11-2026 to 06-11-2026)",
                  ptype=SpecialPeriodType.MID_TERM.value),
        ]
        weeks_without = [
            _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                  strand="Diversity", sub_strand="Classification"),
        ]
        cov_with, _ = _allocate(weeks_with)
        cov_without, _ = _allocate(weeks_without)
        assert cov_with.total_generated_lessons == cov_without.total_generated_lessons

    def test_special_period_lesson_rows_carry_no_fake_content(self):
        """generate_lesson_plans skips special-period rows: no fake objective,
        no 'Learners can MID-TERM', no fake topic (PART Q)."""
        weeks = [
            _week(1, indicators=["B8.1.1.1 Classify living organisms"],
                  strand="Diversity", sub_strand="Classification"),
            _week(2, week_type=WeekType.OTHER,
                  label="MID-TERM (05-11-2026 to 06-11-2026)",
                  ptype=SpecialPeriodType.MID_TERM.value),
            _week(3, indicators=["B8.1.1.2 Observe micro-organisms"],
                  strand="Diversity", sub_strand="Micro-organisms"),
        ]
        coverage, config = _allocate(weeks)
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert len(plans) == 2
        for lp in plans:
            blob = " ".join([
                lp.lesson_topic or "", lp.assessment or "", lp.introduction or "",
                lp.starter_activity or "", lp.conclusion or "",
                *[o.description for o in (lp.learning_objectives or [])],
                *lp.indicators,
            ]).lower()
            assert "mid-term" not in blob
            assert "mid term" not in blob

    def test_revision_week_with_content_generates_when_included(self):
        """PART S: a REVISION week whose source row carries actual teaching
        content is a REAL teaching week when the teacher includes it — it
        generates a genuine lesson from its own indicators, never a fake
        period placeholder."""
        weeks = [
            _week(1, indicators=["B9.1.1.1.1 Describe matter."],
                  strand="Matter", sub_strand="Elements"),
            _week(2, indicators=["B9.1.1.2.1 Explain kinetic theory."],
                  strand="Matter", sub_strand="Kinetic theory",
                  week_type=WeekType.REVISION),
        ]
        coverage, config = _allocate(weeks, include_special=True)
        assert coverage.total_generated_lessons == 2
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert len(plans) == 2
        revision_lesson = next(lp for lp in plans if lp.week_number == 2)
        assert "kinetic" in (revision_lesson.indicators[0].lower())

    def test_revision_week_excluded_by_default(self):
        """PART S: revision weeks follow the existing product rule — excluded
        from the default allocation, included only when the teacher opts in."""
        weeks = [
            _week(1, indicators=["B9.1.1.1.1 Describe matter."],
                  strand="Matter", sub_strand="Elements"),
            _week(2, indicators=["B9.1.1.2.1 Explain kinetic theory."],
                  strand="Matter", sub_strand="Kinetic theory",
                  week_type=WeekType.REVISION),
        ]
        coverage, _ = _allocate(weeks, include_special=False)
        assert coverage.total_generated_lessons == 1

    def test_contentless_special_week_generates_nothing(self):
        """A REVISION/VACATION week with no indicator/strand content at all is
        a non-instructional period: no lesson, no quota unit."""
        for wt in (WeekType.REVISION, WeekType.SBA, WeekType.ASSESSMENT,
                   WeekType.OTHER):
            weeks = [_week(1, week_type=wt)]
            coverage, config = _allocate(weeks)
            assert coverage.total_generated_lessons == 0, wt

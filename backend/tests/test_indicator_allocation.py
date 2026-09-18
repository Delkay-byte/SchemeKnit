"""
SchemeKnit Indicator → Teaching Period → Lesson Plan Allocation Tests
=====================================================================

Tests the core organizational rule:

    ONE WEEK       = a curriculum CONTAINER
    ONE INDICATOR  = ONE TEACHING PERIOD = ONE LESSON PLAN

Covers:
  - 1 indicator → 1 lesson
  - 3 indicators → 3 lessons
  - 3 indicators / 2 available periods (conflict, no drop)
  - multiple weeks with varying indicators
  - holiday gaps (dates respect calendar)
  - indicator coverage (no drops, no duplicates)
  - period numbering within week
  - week preservation
  - special week types excluded
  - edit isolation (editing one lesson doesn't affect another)
  - entitlement counting (individual lessons)
"""

import pytest
from datetime import date, timedelta
from typing import List

from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.coverage_validator import CoverageValidator
from src.models import (
    Week, WeekType, TermConfig, TeachingCalendar, Holiday,
    LessonPlan, LessonStatus,
)


# ── Fixtures ────────────────────────────────────────────────────────────

def make_week(week_number: int, indicators: List[str],
              week_type: WeekType = WeekType.INSTRUCTION,
              content_standards: List[str] | None = None) -> Week:
    start = date(2026, 1, 5 + (week_number - 1) * 7)
    return Week(
        scheme_of_work_id="test-scheme",
        week_number=week_number,
        start_date=start,
        end_date=start + timedelta(days=6),
        week_type=week_type,
        strand="Diversity of Matter",
        sub_strand="Elements and Compounds",
        content_standards=content_standards or ["B9.1.1.1 Demonstrate understanding of matter"],
        indicators=indicators,
        resources=[],
    )


def make_config(lessons_per_week: int = 3,
                teaching_days: List[int] | None = None) -> TermConfig:
    return TermConfig(
        scheme_of_work_id="test-scheme",
        term_start_date=date(2026, 1, 5),
        term_end_date=date(2026, 4, 10),
        lessons_per_week=lessons_per_week,
        lesson_duration_minutes=60,
        class_size=24,
        teaching_days=teaching_days if teaching_days is not None else [0, 2, 4],
        holidays=[],
        ai_mode="OFF",
        template_type="GES-style",
        include_special_weeks=False,
        school_name="Test School",
        teacher_name="Test Teacher",
        class_level="Basic 9",
        subject="Science",
    )


@pytest.fixture
def engine():
    return AllocationEngine()


@pytest.fixture
def calendar_engine():
    return CalendarEngine()


@pytest.fixture
def validator():
    return CoverageValidator()


# ── 1. One indicator → one lesson ───────────────────────────────────────

class TestOneIndicatorOneLesson:
    def test_single_indicator_single_lesson(self, engine, calendar_engine):
        weeks = [make_week(1, ["B9.1.1.1.1 Describe the nature of matter."])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        assert len(plans) == 1
        assert plans[0].week_number == 1
        assert plans[0].lesson_number == 1
        assert len(plans[0].indicators) == 1
        assert "B9.1.1.1.1" in plans[0].indicator_codes[0]

    def test_coverage_100_pct(self, engine, calendar_engine, validator):
        weeks = [make_week(1, ["B9.1.1.1.1 Describe the nature of matter."])]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        issues = validator.validate(weeks, coverage)

        assert coverage.total_indicators == 1
        assert coverage.total_generated_lessons == 1
        assert coverage.coverage_percentage == 100.0
        assert not [i for i in issues if i.severity.value == "warning"]


# ── 2. Three indicators → three lessons ─────────────────────────────────

class TestThreeIndicatorsThreeLessons:
    WEEK1_INDICATORS = [
        "B9.1.1.1.1 Describe the nature of matter.",
        "B9.1.1.1.2 Classify materials as elements or compounds.",
        "B9.1.1.1.3 Explain the differences between mixtures and compounds.",
    ]

    def test_three_indicators_produce_three_lessons(self, engine, calendar_engine):
        weeks = [make_week(1, self.WEEK1_INDICATORS)]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        assert len(plans) == 3
        for i, plan in enumerate(plans):
            assert plan.week_number == 1
            assert plan.lesson_number == i + 1
            assert len(plan.indicators) == 1

    def test_each_lesson_has_distinct_indicator(self, engine, calendar_engine):
        weeks = [make_week(1, self.WEEK1_INDICATORS)]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        codes = [p.indicator_codes[0] for p in plans]
        assert len(set(codes)) == 3  # all distinct
        for i, code in enumerate(codes):
            assert code == f"B9.1.1.1.{i+1}"

    def test_each_lesson_has_distinct_objective(self, engine, calendar_engine):
        weeks = [make_week(1, self.WEEK1_INDICATORS)]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        descs = [p.learning_objectives[0].description for p in plans]
        assert len(set(descs)) == 3
        for d in descs:
            assert d.startswith("Learners can ")
            assert "nature of matter" in d or "elements" in d or "mixtures" in d

    def test_no_duplicate_primary_indicator(self, engine, calendar_engine, validator):
        weeks = [make_week(1, self.WEEK1_INDICATORS)]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        issues = validator.validate(weeks, coverage)

        assert coverage.indicators_duplicated == 0
        dup_issues = [i for i in issues if "appears" in i.message or "duplicate" in i.message.lower()]
        assert not dup_issues


# ── 3. Three indicators / two periods (conflict) ───────────────────────

class TestIndicatorPeriodConflict:
    def test_more_indicators_than_periods_still_allocates_all(self, engine, calendar_engine):
        """3 indicators, only 2 teaching days available — all 3 must still
        be allocated (conflict reported, not silently resolved)."""
        indicators = [
            "B9.1.1.1.1 Describe the nature of matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Explain mixtures.",
        ]
        weeks = [make_week(1, indicators)]
        # Only 2 teaching days → 2 available periods
        config = make_config(lessons_per_week=2, teaching_days=[0, 2])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        # All 3 indicators allocated — none dropped
        assert coverage.total_indicators == 3
        assert len(plans) == 3
        assert coverage.indicators_unallocated == 0

    def test_conflict_is_reported(self, engine, calendar_engine):
        indicators = [
            "B9.1.1.1.1 Describe the nature of matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Explain mixtures.",
        ]
        weeks = [make_week(1, indicators)]
        config = make_config(lessons_per_week=2, teaching_days=[0, 2])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        assert len(coverage.allocation_conflicts) > 0
        conflict = coverage.allocation_conflicts[0]
        assert "3 indicators" in conflict
        assert "2 teaching periods" in conflict


# ── 4. Multiple weeks ──────────────────────────────────────────────────

class TestMultipleWeeks:
    MULTI_WEEK = [
        make_week(1, [
            "B9.1.1.1.1 Describe the nature of matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Explain mixtures.",
        ]),
        make_week(2, [
            "B9.1.1.2.1 Explain kinetic theory.",
            "B9.1.1.2.2 Describe particle motion.",
        ]),
        make_week(3, [
            "B9.1.1.3.1 Describe atoms.",
            "B9.1.1.3.2 Describe molecules.",
            "B9.1.1.3.3 Explain bonding.",
            "B9.1.1.3.4 Classify bonds.",
        ]),
    ]

    def test_lesson_count_matches_indicator_count(self, engine, calendar_engine):
        config = make_config(lessons_per_week=5)
        cal = calendar_engine.build_calendar(config, self.MULTI_WEEK, [])
        coverage = engine.allocate(self.MULTI_WEEK, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        # 3 + 2 + 4 = 9 lessons
        assert len(plans) == 9
        assert coverage.total_indicators == 9

    def test_week_numbers_preserved(self, engine, calendar_engine):
        config = make_config(lessons_per_week=5)
        cal = calendar_engine.build_calendar(config, self.MULTI_WEEK, [])
        coverage = engine.allocate(self.MULTI_WEEK, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        week_1 = [p for p in plans if p.week_number == 1]
        week_2 = [p for p in plans if p.week_number == 2]
        week_3 = [p for p in plans if p.week_number == 3]

        assert len(week_1) == 3
        assert len(week_2) == 2
        assert len(week_3) == 4

    def test_lesson_number_resets_per_week(self, engine, calendar_engine):
        config = make_config(lessons_per_week=5)
        cal = calendar_engine.build_calendar(config, self.MULTI_WEEK, [])
        coverage = engine.allocate(self.MULTI_WEEK, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        week_1 = sorted([p for p in plans if p.week_number == 1], key=lambda p: p.lesson_number)
        week_2 = sorted([p for p in plans if p.week_number == 2], key=lambda p: p.lesson_number)

        # Period numbering is per-week: 1,2,3 for week 1; 1,2 for week 2
        assert [p.lesson_number for p in week_1] == [1, 2, 3]
        assert [p.lesson_number for p in week_2] == [1, 2]

    def test_global_lesson_sequence_is_contiguous(self, engine, calendar_engine):
        config = make_config(lessons_per_week=5)
        cal = calendar_engine.build_calendar(config, self.MULTI_WEEK, [])
        coverage = engine.allocate(self.MULTI_WEEK, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        sequences = sorted(p.lesson_sequence for p in plans)
        assert sequences == list(range(1, 10))  # 1..9

    def test_full_coverage_multi_week(self, engine, calendar_engine, validator):
        # 5 teaching days so Week 3 (4 indicators) has enough periods
        config = make_config(lessons_per_week=5, teaching_days=[0, 1, 2, 3, 4])
        cal = calendar_engine.build_calendar(config, self.MULTI_WEEK, [])
        coverage = engine.allocate(self.MULTI_WEEK, cal, config)
        issues = validator.validate(self.MULTI_WEEK, coverage)

        assert coverage.coverage_percentage == 100.0
        assert coverage.indicators_unallocated == 0
        assert coverage.indicators_duplicated == 0
        warnings = [i for i in issues if i.severity.value == "warning"]
        assert not warnings


# ── 5. Special week types ──────────────────────────────────────────────

class TestSpecialWeekTypes:
    def test_revision_week_excluded_from_allocation(self, engine, calendar_engine):
        weeks = [
            make_week(1, ["B9.1.1.1.1 Describe matter."]),
            make_week(2, ["B9.1.1.2.1 Explain kinetic theory."],
                      week_type=WeekType.REVISION),
        ]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config, include_special_weeks=False)

        # Only instruction week 1 contributes
        assert coverage.total_instructional_weeks == 1
        assert coverage.total_indicators == 1
        assert all(a.week_number == 1 for a in coverage.allocations)

    def test_assessment_week_excluded(self, engine, calendar_engine):
        weeks = [
            make_week(1, ["B9.1.1.1.1 Describe matter."]),
            make_week(2, [], week_type=WeekType.ASSESSMENT),
        ]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config, include_special_weeks=False)

        assert coverage.total_indicators == 1

    def test_special_weeks_included_when_flagged(self, engine, calendar_engine):
        weeks = [
            make_week(1, ["B9.1.1.1.1 Describe matter."]),
            make_week(2, ["B9.1.1.2.1 Explain kinetic theory."],
                      week_type=WeekType.REVISION),
        ]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config, include_special_weeks=True)

        assert coverage.total_indicators == 2


# ── 6. Holiday gaps ────────────────────────────────────────────────────

class TestHolidayGaps:
    def test_holiday_excludes_teaching_day(self, engine, calendar_engine):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
        ])]
        # Wednesday of week 1 is a holiday
        holidays = [Holiday(name="Test Holiday", date=date(2026, 1, 7), is_recurring=False)]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, holidays)
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        # Both indicators still allocated
        assert len(plans) == 2
        # No lesson falls on the holiday
        for p in plans:
            assert p.lesson_date != date(2026, 1, 7)


# ── 7. Edit isolation ──────────────────────────────────────────────────

class TestEditIsolation:
    def test_editing_one_lesson_does_not_affect_another(self, engine, calendar_engine):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe the nature of matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Explain mixtures.",
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        # Simulate editing lesson 1
        plans[0].assessment = "EDITED assessment for lesson 1"
        plans[0].introduction = "EDITED introduction for lesson 1"
        plans[0].teacher_edited = True

        # Lessons 2 and 3 are untouched
        assert "EDITED" not in plans[1].assessment
        assert "EDITED" not in plans[2].assessment
        assert "EDITED" not in plans[1].introduction
        assert "EDITED" not in plans[2].introduction
        assert not plans[1].teacher_edited
        assert not plans[2].teacher_edited

    def test_lessons_have_distinct_content(self, engine, calendar_engine):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe the nature of matter.",
            "B9.1.1.1.2 Classify materials as elements or compounds.",
            "B9.1.1.1.3 Explain the differences between mixtures and compounds.",
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        # Each lesson's main activity mentions its own indicator
        act1 = plans[0].main_activities[0].description
        act2 = plans[1].main_activities[0].description
        act3 = plans[2].main_activities[0].description

        assert "nature of matter" in act1
        assert "Classify materials" in act2
        assert "mixtures" in act3
        assert act1 != act2 != act3


# ── 8. Period label ────────────────────────────────────────────────────

class TestPeriodLabel:
    def test_period_label_generated_when_not_configured(self, engine, calendar_engine):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
        ])]
        config = make_config(lessons_per_week=3)
        config.period = ""  # not configured
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        assert plans[0].period == "Period 1"
        assert plans[1].period == "Period 2"

    def test_teacher_configured_period_preserved(self, engine, calendar_engine):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
        ])]
        config = make_config(lessons_per_week=3)
        config.period = "1st & 2nd"
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")

        for p in plans:
            assert p.period == "1st & 2nd"


# ── 9. Coverage validator: missing & duplicate detection ──────────────

class TestCoverageValidator:
    def test_missing_indicator_detected(self, engine, calendar_engine, validator):
        """If an indicator somehow has no allocation, the validator flags it."""
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Explain mixtures.",
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        # Simulate dropping one allocation
        coverage.allocations = coverage.allocations[:2]
        coverage.total_indicators = 2
        coverage.total_generated_lessons = 2

        issues = validator.validate(weeks, coverage)
        missing = [i for i in issues if "no lesson allocation" in i.message]
        assert len(missing) >= 1

    def test_duplicate_indicator_detected(self, engine, calendar_engine, validator):
        weeks = [make_week(1, ["B9.1.1.1.1 Describe matter."])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        # Simulate duplicating an allocation
        dup = coverage.allocations[0].model_copy(deep=True)
        coverage.allocations.append(dup)

        issues = validator.validate(weeks, coverage)
        dup_issues = [i for i in issues if "appears" in i.message or "primary indicator of" in i.message]
        assert len(dup_issues) >= 1

    def test_generate_report_has_week_summaries(self, engine, calendar_engine, validator):
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        report = validator.generate_report(weeks, coverage)

        assert "weeks" in report
        assert len(report["weeks"]) == 1
        w = report["weeks"][0]
        assert w["week_number"] == 1
        assert w["indicator_count"] == 2
        assert w["lesson_count"] == 2
        assert len(w["periods"]) == 2
        assert w["periods"][0]["period_index"] == 1
        assert w["periods"][1]["period_index"] == 2


# -- Real-world regression cases (Section 15) -----------------------------------

class TestRealWorldRegression:
    """Regression cases mirroring real classroom schemes."""

    def test_five_indicators_five_lessons(self, engine, calendar_engine, validator):
        """A real week with 5 indicators and 5 available periods ? 5 lessons."""
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Identify properties.",
            "B9.1.1.1.4 Compare states.",
            "B9.1.1.1.5 Investigate changes.",
        ])]
        config = make_config(lessons_per_week=5, teaching_days=[0, 1, 2, 3, 4])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        assert coverage.total_generated_lessons == 5
        assert coverage.indicators_unallocated == 0
        assert coverage.coverage_percentage == 100.0

        issues = validator.validate(weeks, coverage)
        warnings = [i for i in issues if i.severity.value == "warning"]
        assert not warnings

    def test_lessons_per_week_does_not_cap_allocation(self, engine, calendar_engine, validator):
        """Section 7: lessons_per_week is advisory. 3 indicators with lessons_per_week=2
        and 3 available periods must still allocate all 3 (with a conflict note)."""
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Identify properties.",
        ])]
        # 3 teaching days available, but lessons_per_week advisory = 2
        config = make_config(lessons_per_week=2, teaching_days=[0, 2, 4])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        # All 3 indicators are allocated � none dropped to satisfy the advisory cap
        assert coverage.total_generated_lessons == 3
        assert coverage.indicators_unallocated == 0

    def test_regeneration_is_deterministic(self, engine, calendar_engine, validator):
        """Section 9: regenerating the same scheme produces identical allocations."""
        weeks = [
            make_week(1, ["B9.1.1.1.1 Describe matter.", "B9.1.1.1.2 Classify materials."]),
            make_week(2, ["B9.1.1.2.1 Explain elements.", "B9.1.1.2.2 Compare compounds."]),
        ]
        config = make_config(lessons_per_week=3)

        cal = calendar_engine.build_calendar(config, weeks, [])
        first = engine.allocate(weeks, cal, config)
        second = engine.allocate(weeks, cal, config)

        assert first.total_generated_lessons == second.total_generated_lessons
        assert len(first.allocations) == len(second.allocations)
        for a, b in zip(first.allocations, second.allocations):
            assert a.week_number == b.week_number
            assert a.period_index == b.period_index
            assert a.indicator_code == b.indicator_code
            assert a.lesson_date == b.lesson_date

    def test_batch_generation_multiple_weeks(self, engine, calendar_engine, validator):
        """Section 15: batch generation across weeks keeps per-week numbering stable."""
        weeks = [
            make_week(1, ["B9.1.1.1.1 Describe matter.", "B9.1.1.1.2 Classify materials."]),
            make_week(2, ["B9.1.1.2.1 Explain elements."]),
            make_week(3, ["B9.1.1.3.1 Investigate acids.", "B9.1.1.3.2 Test bases.", "B9.1.1.3.3 Mix solutions."]),
        ]
        config = make_config(lessons_per_week=5, teaching_days=[0, 1, 2, 3, 4])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        assert coverage.total_generated_lessons == 6
        report = validator.generate_report(weeks, coverage)

        by_week = {w["week_number"]: w for w in report["weeks"]}
        assert by_week[1]["lesson_count"] == 2
        assert by_week[2]["lesson_count"] == 1
        assert by_week[3]["lesson_count"] == 3

        # period_index restarts at 1 within each week (1-based)
        assert [p["period_index"] for p in by_week[1]["periods"]] == [1, 2]
        assert [p["period_index"] for p in by_week[3]["periods"]] == [1, 2, 3]

    def test_no_compression_of_indicators(self, engine, calendar_engine, validator):
        """Section 6/Section 15: never compress multiple indicators into one lesson to succeed."""
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Identify properties.",
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        # Each allocation carries exactly one indicator � no merged lessons
        for alloc in coverage.allocations:
            assert alloc.indicator_code is not None
            assert alloc.indicator_code != ""
        assert len(coverage.allocations) == 3

    def test_dates_follow_calendar_order(self, engine, calendar_engine, validator):
        """Section 5: lesson dates are chronological within a week."""
        weeks = [make_week(1, [
            "B9.1.1.1.1 Describe matter.",
            "B9.1.1.1.2 Classify materials.",
            "B9.1.1.1.3 Identify properties.",
        ])]
        config = make_config(lessons_per_week=3, teaching_days=[0, 2, 4])
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        dates = [a.lesson_date for a in sorted(coverage.allocations, key=lambda x: x.period_index)]
        assert all(dates[i] < dates[i + 1] for i in range(len(dates) - 1))


# -- Concatenated indicator splitting (real GES scheme format) ----------

class TestConcatenatedIndicatorSplitting:
    """Real schemes store multiple indicators in ONE string. The engine must
    split them so each indicator gets its own teaching period and lesson."""

    def test_split_two_concatenated_indicators(self):
        raw = [
            "B9.1.1.1.2 Discuss the formation of binary chemical compounds "
            "B9.1.1.1.3 Describe the characteristics of common acids, bases and salts."
        ]
        split = AllocationEngine._split_indicators(raw)
        assert len(split) == 2
        assert split[0].startswith("B9.1.1.1.2")
        assert split[1].startswith("B9.1.1.1.3")

    def test_split_three_concatenated_indicators(self):
        raw = [
            "B9.2.1.1.1 Explain the nitrogen cycle. "
            "B9.2.1.1.2 Describe its importance. "
            "B9.2.1.1.3 Assess human impact."
        ]
        split = AllocationEngine._split_indicators(raw)
        assert len(split) == 3

    def test_single_indicator_unchanged(self):
        raw = ["B9.1.1.1.1 Identify by name binary chemical compounds."]
        split = AllocationEngine._split_indicators(raw)
        assert len(split) == 1
        assert split[0] == raw[0]

    def test_plain_text_indicator_unchanged(self):
        raw = ["Discuss the formation of binary chemical compounds."]
        split = AllocationEngine._split_indicators(raw)
        assert len(split) == 1

    def test_concatenated_week_produces_two_lessons(self, engine, calendar_engine, validator):
        """The real defect: a merged two-indicator week must yield 2 lessons."""
        weeks = [make_week(1, [
            "B9.1.1.1.2 Discuss the formation of binary chemical compounds "
            "B9.1.1.1.3 Describe the characteristics of common acids, bases and salts."
        ])]
        config = make_config(lessons_per_week=3)
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        assert coverage.total_generated_lessons == 2
        assert coverage.total_indicators == 2
        assert coverage.coverage_percentage == 100.0

        codes = [a.indicator_code for a in coverage.allocations]
        assert "B9.1.1.1.2" in codes
        assert "B9.1.1.1.3" in codes

        # Validator must not flag the second indicator as missing
        issues = validator.validate(weeks, coverage)
        missing = [i for i in issues if "no lesson allocation" in i.message]
        assert not missing


# -- Calendar: single-day week ranges (real extractor format) -----------

class TestSingleDayWeekExpansion:
    """The real extractor stores each week as a single date (start == end).
    The calendar must expand it to a full week so every teaching day counts."""

    def _weeks_with_single_day_ranges(self, n_weeks: int) -> List[Week]:
        out = []
        for wn in range(1, n_weeks + 1):
            d = date(2026, 9, 11 + (wn - 1) * 7)  # Fridays, like the real scheme
            out.append(Week(
                scheme_of_work_id="test-scheme", week_number=wn,
                start_date=d, end_date=d, week_type=WeekType.INSTRUCTION,
                strand="S", sub_strand="SS", content_standards=["CS"],
                indicators=[f"B9.1.1.{wn}.1 Do thing {wn}."], resources=[],
            ))
        return out

    def test_single_day_week_expands_to_three_teaching_days(self, calendar_engine):
        weeks = self._weeks_with_single_day_ranges(3)
        # Term must cover the September dates used by the helper.
        config = TermConfig(
            scheme_of_work_id="test-scheme",
            term_start_date=date(2026, 9, 1),
            term_end_date=date(2026, 12, 31),
            lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
            teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
            template_type="GES-style", include_special_weeks=False,
            school_name="S", teacher_name="T",
            class_level="Basic 9", subject="Science",
        )
        cal = calendar_engine.build_calendar(config, weeks, [])

        from collections import defaultdict
        per_week = defaultdict(list)
        for d in cal.days:
            if d.is_teaching_day and d.week_number is not None:
                per_week[d.week_number].append(d.date)

        # Each week now covers Mon/Wed/Fri of its teaching week
        assert len(per_week[2]) == 3
        assert len(per_week[3]) == 3

    def test_multi_indicator_single_day_week_no_false_conflict(
        self, engine, calendar_engine, validator
    ):
        """Before the fix a 2-indicator week reported 'only 1 period available'."""
        weeks = self._weeks_with_single_day_ranges(2)
        weeks[1] = Week(
            scheme_of_work_id="test-scheme", week_number=2,
            start_date=date(2026, 9, 18), end_date=date(2026, 9, 18),
            week_type=WeekType.INSTRUCTION, strand="S", sub_strand="SS",
            content_standards=["CS"],
            indicators=[
                "B9.1.1.2.1 First indicator. B9.1.1.2.2 Second indicator."
            ],
            resources=[],
        )
        config = TermConfig(
            scheme_of_work_id="test-scheme",
            term_start_date=date(2026, 9, 1),
            term_end_date=date(2026, 12, 31),
            lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
            teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
            template_type="GES-style", include_special_weeks=False,
            school_name="S", teacher_name="T",
            class_level="Basic 9", subject="Science",
        )
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)

        # W1 has 1 indicator, W2 splits into 2 → 3 lessons total
        assert coverage.total_generated_lessons == 3
        w2 = [a for a in coverage.allocations if a.week_number == 2]
        assert len(w2) == 2
        # No "only 1 teaching period" conflict: 2 indicators, 3 periods available
        assert not any("only 1 teaching periods" in c for c in coverage.allocation_conflicts)
        # The two lessons land on different real dates
        dates = sorted(a.lesson_date for a in w2 if a.lesson_date)
        assert len(dates) == 2 and dates[0] != dates[1]

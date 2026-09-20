"""
Indicator carry-forward allocation tests (§6-§10).

    ONE INDICATOR → ONE TEACHING PERIOD → ONE LESSON PLAN

When a source curriculum week contains more indicators than it has teaching
periods, the surplus must CARRY FORWARD to the following teaching week(s):
never dropped, never merged, never duplicated, and with BOTH the source
curriculum week and the actual teaching week preserved.
"""

from datetime import date, timedelta
from typing import List

import pytest

from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.models import Week, WeekType, TermConfig


def make_week(week_number: int, indicators: List[str]) -> Week:
    start = date(2026, 9, 7) + timedelta(days=(week_number - 1) * 7)
    return Week(
        scheme_of_work_id="test-scheme",
        week_number=week_number,
        start_date=start,
        end_date=start + timedelta(days=6),
        week_type=WeekType.INSTRUCTION,
        strand="Strand",
        sub_strand="Sub-strand",
        content_standards=[f"B9.1.{week_number}.1 Content standard"],
        indicators=indicators,
        resources=[],
    )


def make_config() -> TermConfig:
    return TermConfig(
        scheme_of_work_id="test-scheme",
        term_start_date=date(2026, 9, 1),
        term_end_date=date(2026, 12, 31),
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=24,
        teaching_days=[0, 2, 4],  # Mon / Wed / Fri → 3 periods per week
        holidays=[],
        ai_mode="OFF",
        template_type="GES-style",
        include_special_weeks=False,
        school_name="Test School",
        teacher_name="Test Teacher",
        class_level="Basic 9",
        subject="Science",
    )


def indicator(week: int, idx: int) -> str:
    return f"B9.1.{week}.{idx} Indicator {week}.{idx}"


@pytest.fixture
def engine():
    return AllocationEngine()


@pytest.fixture
def calendar_engine():
    return CalendarEngine()


class TestFiveIndicatorsThreePeriods:
    """§7 canonical example: 5 indicators / 3 teaching periods."""

    def _coverage(self, engine, calendar_engine):
        weeks = [
            make_week(1, [indicator(1, i) for i in range(1, 6)]),
            make_week(2, []),  # next teaching week receives the carry-forward
        ]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        return engine.allocate(weeks, cal, config), config

    def test_first_three_in_week_one(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        w1 = [a for a in coverage.allocations if a.teaching_week == 1]
        assert len(w1) == 3
        assert sorted(a.period_index for a in w1) == [1, 2, 3]

    def test_remaining_two_carry_to_week_two(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        w2 = [a for a in coverage.allocations if a.teaching_week == 2]
        assert len(w2) == 2
        assert sorted(a.period_index for a in w2) == [1, 2]
        assert all(a.carry_forward for a in w2)

    def test_source_week_preserved(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        # Every indicator still reports its ORIGINAL curriculum week.
        assert all(a.week_number == 1 for a in coverage.allocations)

    def test_carry_forward_from_week_recorded(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        carried = [a for a in coverage.allocations if a.carry_forward]
        assert all(a.carry_forward_from_week == 1 for a in carried)

    def test_no_indicator_dropped_or_duplicated(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        assert coverage.total_indicators == 5
        assert len(coverage.allocations) == 5
        assert coverage.indicators_unallocated == 0
        assert coverage.indicators_duplicated == 0
        codes = [a.indicator_code for a in coverage.allocations]
        assert len(set(codes)) == 5

    def test_one_indicator_one_lesson_each(self, engine, calendar_engine):
        coverage, config = self._coverage(engine, calendar_engine)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")
        assert len(plans) == 5
        for plan in plans:
            assert len(plan.indicators) == 1
            assert len(plan.indicator_codes) == 1

    def test_actual_teaching_week_on_lesson(self, engine, calendar_engine):
        coverage, config = self._coverage(engine, calendar_engine)
        plans = engine.generate_lesson_plans(coverage, config, "scheme-1")
        carried = [p for p in plans if p.carry_forward]
        assert len(carried) == 2
        assert all(p.teaching_week == 2 for p in carried)
        # ...and the curriculum origin is not overwritten by the teaching week.
        assert all(p.week_number == 1 for p in carried)

    def test_carry_forward_conflict_reported(self, engine, calendar_engine):
        coverage, _ = self._coverage(engine, calendar_engine)
        assert coverage.allocation_conflicts
        msg = coverage.allocation_conflicts[0]
        assert "5" in msg and "3" in msg


class TestEightIndicatorsThreePeriods:
    """§9: 8 indicators / 3 periods → 3, 3, 2 across three teaching weeks."""

    def _coverage(self, engine, calendar_engine):
        weeks = [
            make_week(1, [indicator(1, i) for i in range(1, 9)]),
            make_week(2, []),
            make_week(3, []),
        ]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        return engine.allocate(weeks, cal, config)

    def test_distribution(self, engine, calendar_engine):
        coverage = self._coverage(engine, calendar_engine)
        per_week = {}
        for a in coverage.allocations:
            per_week.setdefault(a.teaching_week, []).append(a)
        assert len(per_week[1]) == 3
        assert len(per_week[2]) == 3
        assert len(per_week[3]) == 2

    def test_total_and_uniqueness(self, engine, calendar_engine):
        coverage = self._coverage(engine, calendar_engine)
        assert len(coverage.allocations) == 8
        codes = [a.indicator_code for a in coverage.allocations]
        assert len(set(codes)) == 8

    def test_period_numbers_reset_each_teaching_week(self, engine, calendar_engine):
        coverage = self._coverage(engine, calendar_engine)
        w2 = sorted(
            (a.period_index for a in coverage.allocations if a.teaching_week == 2)
        )
        assert w2 == [1, 2, 3]


class TestDeterminismAndOrdering:
    def test_regeneration_is_deterministic(self, engine, calendar_engine):
        weeks = [
            make_week(1, [indicator(1, i) for i in range(1, 6)]),
            make_week(2, [indicator(2, 1)]),
        ]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        first = engine.allocate(weeks, cal, config)
        second = engine.allocate(weeks, cal, config)
        assert len(first.allocations) == len(second.allocations)
        for a, b in zip(first.allocations, second.allocations):
            assert a.indicator_code == b.indicator_code
            assert a.teaching_week == b.teaching_week
            assert a.period_index == b.period_index
            assert a.carry_forward == b.carry_forward
            assert a.lesson_date == b.lesson_date

    def test_later_indicator_never_moves_backwards(self, engine, calendar_engine):
        """A week with spare periods must not pull a later week's indicator in."""
        weeks = [
            make_week(1, [indicator(1, 1)]),   # 1 indicator, 3 periods
            make_week(2, [indicator(2, 1)]),   # belongs to week 2
        ]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        assert all(a.teaching_week == 2 for a in coverage.allocations
                   if a.week_number == 2)
        assert all(not a.carry_forward for a in coverage.allocations)

    def test_curriculum_order_preserved(self, engine, calendar_engine):
        weeks = [make_week(1, [indicator(1, i) for i in range(1, 6)])]
        config = make_config()
        cal = calendar_engine.build_calendar(config, weeks, [])
        coverage = engine.allocate(weeks, cal, config)
        ordered = sorted(coverage.allocations, key=lambda a: a.lesson_sequence)
        assert [a.indicator_code for a in ordered] == [
            a.indicator_code for a in coverage.allocations
        ]

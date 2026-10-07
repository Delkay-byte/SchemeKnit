"""
Priority 1 — weekly curriculum coverage semantics (SOURCE OCCURRENCE model).

Authoritative business rule:

    SOURCE OCCURRENCE → WEEKLY LESSON PLAN

Teaching periods are timetable metadata. They never cap, defer, move or
rebalance curriculum lesson plans. A source week with N instructional source
occurrences produces exactly N lesson plans, all in that source week.

Covers the required regression matrix (T1-T14):

  T1  2 periods / 2 indicators          → 2 lessons, both week 5
  T2  2 periods / 3 indicators          → 3 lessons, all week 5, no carry-forward
  T3  2 periods / 4 indicators          → 4 lessons, all week 5, no carry-forward
  T4  1 period  / 4 indicators          → 4 lessons, same source week
  T5  0/unspecified periods / 3         → 3 lessons, same week, generation not blocked
  T6  repeated indicator across weeks   → 2 distinct occurrences, no duplicate error
  T7  same source occurrence twice      → duplicate protection still dedupes
  T8  mixed week                        → instructional occurrences stay put
  T9  special-only week                 → no invented lesson plan
  T10 week order                        → no week N lesson under week N+1
  T11 generation request                → source week + occurrence id preserved
  T12 persistence / reload              → count, week, indicator, occurrence id survive
  T13 quota separation                  → timetable capacity never changes counts/codes
  T14 cross-week isolation              → no overflow in either direction
"""

from datetime import date, timedelta
from typing import List

import pytest

from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.coverage_validator import CoverageValidator
from src.models import Week, WeekType, TermConfig


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_week(week_number: int, indicators: List[str],
              week_type: WeekType = WeekType.INSTRUCTION) -> Week:
    start = date(2026, 9, 7) + timedelta(days=(week_number - 1) * 7)
    return Week(
        scheme_of_work_id="test-scheme",
        week_number=week_number,
        start_date=start,
        end_date=start + timedelta(days=6),
        week_type=week_type,
        strand="Strand",
        sub_strand="Sub-strand",
        content_standards=[f"B9.1.{week_number}.1 Content standard"],
        indicators=indicators,
        resources=[],
    )


def make_config(teaching_days=(0, 2, 4), lessons_per_week=3) -> TermConfig:
    return TermConfig(
        scheme_of_work_id="test-scheme",
        term_start_date=date(2026, 9, 1),
        term_end_date=date(2026, 12, 31),
        lessons_per_week=lessons_per_week,
        lesson_duration_minutes=60,
        class_size=24,
        teaching_days=list(teaching_days),
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
    return f"B9.1.{week}.{idx} Indicator text for {week}.{idx}."


def allocate(weeks, teaching_days=(0, 2, 4), lessons_per_week=3,
             include_special_weeks=False):
    config = make_config(teaching_days=teaching_days,
                         lessons_per_week=lessons_per_week)
    cal = CalendarEngine().build_calendar(config, weeks, [])
    coverage = AllocationEngine().allocate(
        weeks, cal, config, include_special_weeks)
    return coverage, config


def weeks_of(coverage):
    """Allocations grouped by SOURCE week (non-special rows only)."""
    out = {}
    for a in coverage.allocations:
        if getattr(a, "is_special_period", False):
            continue
        out.setdefault(a.week_number, []).append(a)
    return out


@pytest.fixture
def engine():
    return AllocationEngine()


# ── T1-T5: timetable capacity is never a cap ────────────────────────────────

class TestPeriodsNeverCapCoverage:
    def test_t1_two_periods_two_indicators(self, engine):
        weeks = [make_week(5, [indicator(5, 1), indicator(5, 2)])]
        coverage, _ = allocate(weeks, teaching_days=(0, 2))
        w5 = weeks_of(coverage)[5]
        assert len(w5) == 2
        assert all(a.week_number == 5 and a.teaching_week == 5 for a in w5)
        assert all(not a.carry_forward for a in w5)

    def test_t2_two_periods_three_indicators(self, engine):
        weeks = [make_week(5, [indicator(5, i) for i in range(1, 4)])]
        coverage, _ = allocate(weeks, teaching_days=(0, 2))
        w5 = weeks_of(coverage)[5]
        assert len(w5) == 3
        assert all(a.week_number == 5 and a.teaching_week == 5 for a in w5)
        assert not any(a.carry_forward for a in coverage.allocations)
        assert coverage.allocation_conflicts == []

    def test_t3_two_periods_four_indicators(self, engine):
        weeks = [make_week(5, [indicator(5, i) for i in range(1, 5)])]
        coverage, config = allocate(weeks, teaching_days=(0, 2))
        w5 = weeks_of(coverage)[5]
        assert len(w5) == 4
        assert all(a.week_number == 5 for a in w5)
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len(plans) == 4
        assert all(p.week_number == 5 for p in plans)

    def test_t4_one_period_four_indicators(self, engine):
        weeks = [make_week(5, [indicator(5, i) for i in range(1, 5)])]
        coverage, config = allocate(weeks, teaching_days=(0,))
        w5 = weeks_of(coverage)[5]
        assert len(w5) == 4
        assert all(a.week_number == 5 and a.teaching_week == 5 for a in w5)
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len(plans) == 4

    def test_t5_no_teaching_periods_three_indicators(self, engine):
        """0/unspecified teaching periods must NOT block generation."""
        weeks = [make_week(5, [indicator(5, i) for i in range(1, 4)])]
        coverage, config = allocate(weeks, teaching_days=())
        w5 = weeks_of(coverage)[5]
        assert len(w5) == 3
        assert all(a.week_number == 5 and a.teaching_week == 5 for a in w5)
        # Generation proceeds; the empty date falls back to week ending.
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len(plans) == 3
        assert all(p.week_number == 5 for p in plans)
        assert all(p.lesson_date is not None for p in plans)
        # The state is described as context, never as a carry-forward.
        assert not any("continue in the next" in w for w in coverage.warnings)
        assert any("teaching periods not specified" in w
                   for w in coverage.warnings)

    def test_more_periods_than_indicators_allocates_one(self, engine):
        """CASE F: 4 periods, 1 indicator → 1 lesson plan."""
        weeks = [make_week(5, [indicator(5, 1)])]
        coverage, _ = allocate(weeks, teaching_days=(0, 1, 2, 3))
        assert len(weeks_of(coverage)[5]) == 1


# ── T6/T7: repeated indicators and duplicate protection ─────────────────────

class TestRepeatedIndicatorsAreDistinctOccurrences:
    def test_t6_same_code_in_two_weeks_is_two_occurrences(self, engine):
        repeated = "B9.1.3.1.1 Explain the particle theory of matter."
        weeks = [
            make_week(5, [repeated]),
            make_week(6, [repeated]),
        ]
        coverage, config = allocate(weeks, teaching_days=(0, 2, 4))
        by_week = weeks_of(coverage)
        assert len(by_week[5]) == 1
        assert len(by_week[6]) == 1
        assert by_week[5][0].week_number == 5
        assert by_week[6][0].week_number == 6
        # Distinct source occurrence identities — never a duplicate.
        assert (by_week[5][0].source_occurrence_id
                != by_week[6][0].source_occurrence_id)
        assert coverage.indicators_duplicated == 0
        issues = CoverageValidator().validate(weeks, coverage)
        assert not [i for i in issues if "primary indicator of" in i.message]
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert sorted(p.week_number for p in plans) == [5, 6]

    def test_t7_same_source_occurrence_is_deduplicated(self, engine):
        """The SAME source cell parsed twice still allocates exactly once."""
        text = "B9.1.5.1 Describe the nature of matter."
        weeks = [make_week(5, [text, text])]
        coverage, _ = allocate(weeks, teaching_days=(0, 2, 4))
        assert len(weeks_of(coverage)[5]) == 1
        assert coverage.indicators_duplicated == 0

    def test_duplicate_protection_counts_source_occurrences(self, engine):
        """indicator_code alone can never trigger the duplicate error."""
        coverage, _ = allocate([
            make_week(5, ["B9.1.1.1 One.", "B9.1.1.1 One again."]),
            make_week(6, ["B9.1.1.1 One."]),
        ], teaching_days=(0, 2, 4))
        assert coverage.indicators_duplicated == 0


# ── T8/T9: mixed and special-only weeks ─────────────────────────────────────

class TestMixedAndSpecialWeeks:
    def test_t8_mixed_week_keeps_instructional_occurrences(self, engine):
        week = make_week(5, [indicator(5, 1), indicator(5, 2)],
                         week_type=WeekType.MIXED)
        week.special_period_label = "MID-TERM (09-09-2026 to 10-09-2026)"
        week.special_period_type = "mid_term"
        other = make_week(6, [indicator(6, 1)])
        coverage, config = allocate([week, other], teaching_days=(0, 2, 4))
        by_week = weeks_of(coverage)
        assert len(by_week[5]) == 2
        assert all(a.week_number == 5 and a.teaching_week == 5
                   for a in by_week[5])
        assert not any(a.carry_forward for a in coverage.allocations)

    def test_t9_special_only_week_generates_no_lesson(self, engine):
        special = make_week(5, [], week_type=WeekType.OTHER)
        special.special_period_label = "MID-TERM"
        special.special_period_type = "mid_term"
        teaching = make_week(6, [indicator(6, 1)])
        coverage, config = allocate([special, teaching], teaching_days=(0, 2, 4))
        assert 5 not in weeks_of(coverage)
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len(plans) == 1
        assert plans[0].week_number == 6


# ── T10/T14: week order and cross-week isolation ────────────────────────────

class TestWeekOrderAndIsolation:
    def _mixed_scheme(self):
        return [
            make_week(1, [indicator(1, i) for i in range(1, 5)]),  # 4 / 2 days
            make_week(2, [indicator(2, 1), indicator(2, 2)]),      # 2 / 2 days
            make_week(3, [indicator(3, i) for i in range(1, 4)]),  # 3 / 1 day
        ]

    def test_t10_weeks_stay_numerically_ordered(self, engine):
        coverage, config = allocate(self._mixed_scheme(),
                                    teaching_days=(0, 2))
        ordered = sorted(coverage.allocations, key=lambda a: a.lesson_sequence)
        assert [a.week_number for a in ordered] == [1, 1, 1, 1, 2, 2, 3, 3, 3]
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert [p.week_number for p in plans] == [1, 1, 1, 1, 2, 2, 3, 3, 3]

    def test_t10_no_lesson_moved_into_a_later_week(self, engine):
        coverage, _ = allocate(self._mixed_scheme(), teaching_days=(0, 2))
        for a in coverage.allocations:
            assert a.teaching_week == a.week_number
            assert not a.carry_forward
            assert a.carry_forward_from_week is None

    def test_t14_cross_week_isolation(self, engine):
        """Week 1 overflow never enters Week 2, nor the reverse."""
        coverage, config = allocate(self._mixed_scheme(),
                                    teaching_days=(0, 2))
        by_week = weeks_of(coverage)
        assert len(by_week[1]) == 4
        assert len(by_week[2]) == 2
        assert len(by_week[3]) == 3
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len([p for p in plans if p.week_number == 1]) == 4
        assert len([p for p in plans if p.week_number == 2]) == 2
        assert len([p for p in plans if p.week_number == 3]) == 3
        # The preview report groups lessons under their own source week too.
        report = CoverageValidator().generate_report(self._mixed_scheme(),
                                                     coverage)
        for ws in report["weeks"]:
            assert ws["lesson_count"] == ws["indicator_count"]

    def test_no_capacity_conflict_language(self):
        coverage, _ = allocate(self._mixed_scheme(), teaching_days=(0, 2))
        assert coverage.allocation_conflicts == []
        banned = ("will continue in the next", "carried forward",
                  "waiting for next available")
        assert not any(b in w for w in coverage.warnings for b in banned)
        assert not any(b in c for c in coverage.allocation_conflicts
                       for b in banned)

    def test_warning_states_required_lesson_count(self):
        """The preview explains coverage in the required language."""
        coverage, _ = allocate(
            [make_week(5, [indicator(5, i) for i in range(1, 5)])],
            teaching_days=(0, 2))
        assert any(
            "4 curriculum indicators" in w
            and "2 timetable periods" in w
            and "4 lesson plans required for this week" in w
            for w in coverage.warnings
        )


# ── T13: quota separation ───────────────────────────────────────────────────

class TestQuotaSeparation:
    def test_timetable_capacity_never_changes_counts_or_codes(self):
        """Teating-period count is not a generation limit."""
        weeks = [
            make_week(1, [indicator(1, i) for i in range(1, 5)]),
            make_week(2, [indicator(2, 1), indicator(2, 2)]),
        ]
        sparse, _ = allocate(weeks, teaching_days=(0,))
        rich, _ = allocate(weeks, teaching_days=(0, 1, 2, 3, 4))
        assert sparse.total_generated_lessons == rich.total_generated_lessons
        assert sparse.total_generated_lessons == 6
        assert (sorted(a.indicator_code for a in sparse.allocations)
                == sorted(a.indicator_code for a in rich.allocations))

    def test_quota_selection_keys_are_timetable_independent(self):
        """The commercial quota keys on indicator codes, not periods."""
        weeks = [make_week(5, [indicator(5, i) for i in range(1, 4)])]
        codes = set()
        for days in ((), (0,), (0, 2, 4)):
            coverage, _ = allocate(weeks, teaching_days=days)
            codes.add(tuple(sorted(a.indicator_code
                                   for a in coverage.allocations)))
        assert len(codes) == 1


# ── T11: generation request preserves source week + occurrence identity ─────

class TestGenerationRequestIdentity:
    def test_lessons_carry_their_source_occurrence_identity(self, engine):
        weeks = [
            make_week(5, [indicator(5, i) for i in range(1, 5)]),
            make_week(6, [indicator(6, 1), indicator(6, 2)]),
        ]
        coverage, config = allocate(weeks, teaching_days=(0, 2))
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        alloc_by_id = {a.source_occurrence_id: a
                       for a in coverage.allocations}
        assert len(plans) == 6
        for plan in plans:
            assert plan.source_occurrence_id
            source = alloc_by_id[plan.source_occurrence_id]
            assert plan.week_number == source.week_number
            assert plan.teaching_week == source.week_number
            assert plan.source_occurrence_id.startswith(
                f"week{source.week_number}:")

    @pytest.mark.asyncio
    async def test_preview_rows_expose_source_occurrence_identity(self, db):
        """The preview payload (the UI's generation request) carries it too."""
        from tests.conftest import make_user
        from tests.test_curriculum_spine_and_provenance import make_scheme, add_week
        from src.routers import generation as gen_router

        user = make_user(db, email="coverage-sem@t.test")
        scheme = make_scheme(db, user.id)
        add_week(db, scheme.id, 5, indicators=[indicator(5, 1), indicator(5, 2)])
        add_week(db, scheme.id, 6, indicators=[indicator(5, 1)])
        db.commit()

        cfg = TermConfig(scheme_of_work_id=scheme.id)
        report = await gen_router.preview_allocation(scheme.id, cfg, user, db)
        rows = [r for r in report["lesson_review"]
                if not r.get("is_special_period")]
        assert len(rows) == 3
        ids = {r["source_occurrence_id"] for r in rows}
        assert len(ids) == 3, "repeated code across weeks stays two occurrences"
        assert all(r["source_occurrence_id"].startswith(
            f"week{r['source_week']}:") for r in rows)
        assert report["indicators_duplicated"] == 0
        assert not report["allocation_conflicts"]


# ── T12: persistence / reload ───────────────────────────────────────────────

class TestPersistenceAndReload:
    def test_generated_lessons_survive_save_and_reload(self, db):
        from tests.conftest import make_user
        from tests.test_export_download import make_job_with_lessons
        from src.engines.allocation_engine import AllocationEngine
        from src.service import data_service
        from src.routers.generation import _db_to_lesson_model

        user = make_user(db, email="coverage-persist@t.test")
        scheme_db, job = make_job_with_lessons(db, user, lessons=0)

        weeks = [
            make_week(5, [indicator(5, i) for i in range(1, 4)]),
            make_week(6, [indicator(6, 1)]),
        ]
        coverage, config = allocate(weeks, teaching_days=(0, 2))
        plans = AllocationEngine().generate_lesson_plans(
            coverage, config, scheme_db.id)
        assert len(plans) == 4
        for lp in plans:
            data_service.create_lesson_plan(db, user.id, job.id, scheme_db.id, lp)

        # Fresh read path — same as the review page and every export.
        reloaded = data_service.get_lesson_plans_for_job(db, job.id, user.id)
        assert len(reloaded) == 4
        models = [_db_to_lesson_model(row) for row in reloaded]
        assert sorted(m.week_number for m in models) == [5, 5, 5, 6]
        assert len({m.source_occurrence_id for m in models}) == 4
        for m in models:
            assert m.source_occurrence_id.startswith(f"week{m.week_number}:")
            assert m.teaching_week == m.week_number
            assert m.carry_forward is False
            assert m.indicator_codes
        # Source indicator identity is intact after reload.
        assert sorted(m.indicator_codes[0] for m in models
                      if m.week_number == 5) == sorted(
            indicator(5, i).split()[0] for i in range(1, 4))


# ── Migration: source_occurrence_id column (narrow, additive) ────────────────

class TestSourceOccurrenceMigration:
    def test_v032_adds_column_idempotently(self, tmp_path):
        from sqlalchemy import create_engine, inspect as sa_inspect, text
        from sqlalchemy.orm import sessionmaker
        import src.migrations.v032_source_occurrence_id as mig

        url = f"sqlite:///{tmp_path}/migration.db"
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE lesson_plans (id VARCHAR PRIMARY KEY)"
            ))
        Session = sessionmaker(bind=engine)
        session = Session()

        original = mig.engine
        try:
            mig.engine = engine  # the migration inspects its own database
            assert "source_occurrence_id" not in [
                c["name"] for c in sa_inspect(engine).get_columns("lesson_plans")
            ]
            mig.up(session)
            cols = [c["name"] for c in sa_inspect(engine).get_columns(
                "lesson_plans")]
            assert "source_occurrence_id" in cols
            # Idempotent: running again on an existing column is a no-op.
            mig.up(session)
        finally:
            mig.engine = original
            session.close()
            engine.dispose()

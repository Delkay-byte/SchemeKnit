"""
Phase 16.6 Sections D/E — source week-ending dates.

Source week-ending is authoritative through parse → IR → allocation →
generation → preview → export. Missing dates are derived and flagged.
"""
import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.models import ClassLevel, Subject, TermConfig, Week, WeekType
from src.parsers.docx_parser import DOCXParser

REAL = Path(__file__).resolve().parent.parent / "real_documents"
B6 = REAL / "BASIC 6 TERM 1.docx"
B6_FRENCH = REAL / "BASIC 6 FRENCH SCHEME OF LEARNING.docx"

pytestmark = pytest.mark.skipif(
    not B6.exists(), reason="real Basic 6 document not present"
)


def _parse(path: Path, subject: str = None) -> "object":
    kwargs = dict(original_filename=path.name)
    if subject:
        kwargs["target_subject"] = subject
    return asyncio.run(DOCXParser().parse(path, **kwargs))


def _week(scheme, n: int) -> Week:
    return next(w for w in scheme.weeks if w.week_number == n)


class TestSourceDatesRealDocuments:
    def test_french_week1_source_date_not_today(self):
        scheme = _parse(B6_FRENCH, "French")
        w1 = _week(scheme, 1)
        assert w1.end_date == date(2026, 9, 11)
        assert w1.week_ending_derived is False

    def test_french_all_weeks_seven_day_sequence(self):
        scheme = _parse(B6_FRENCH, "French")
        for w in scheme.weeks:
            assert w.week_ending_derived is False, (
                f"week {w.week_number} wrongly derived"
            )
            assert w.end_date != date.today() or w.week_number == 0
        ends = [w.end_date for w in sorted(scheme.weeks, key=lambda x: x.week_number)]
        for prev, nxt in zip(ends, ends[1:]):
            assert (nxt - prev).days == 7

    def test_b6_science_source_dates_not_overwritten(self):
        scheme = _parse(B6, "Science")
        w1 = _week(scheme, 1)
        assert w1.end_date == date(2026, 9, 11)
        assert w1.week_ending_derived is False
        # The classic defect: a source 20 November 2026 must never become
        # the Friday of a later calendar week or "today".
        w11 = _week(scheme, 11)
        assert w11.end_date == date(2026, 11, 20)
        assert w11.week_ending_derived is False

    def test_november_source_never_slides_to_next_friday(self):
        scheme = _parse(B6, "Science")
        w11 = _week(scheme, 11)
        # 20 November 2026 is a Friday; a naive "Friday of lesson week"
        # from a Monday 23 Nov lesson would yield 27 Nov — must not happen.
        assert w11.end_date != date(2026, 11, 23)
        assert w11.end_date != date(2026, 11, 27)


class TestDateFormats:
    def test_textual_full_month(self):
        assert DOCXParser()._parse_date("11 September 2026") == date(2026, 9, 11)

    def test_textual_abbrev_month(self):
        assert DOCXParser()._parse_date("11 Sep 2026") == date(2026, 9, 11)

    def test_us_style_month_first(self):
        assert DOCXParser()._parse_date("September 11, 2026") == date(2026, 9, 11)

    @pytest.mark.parametrize("raw", ["11/09/2026", "11-09-2026", "11.09.2026"])
    def test_day_first_numeric(self, raw):
        # Day-first: 11 September, never 11 November (US month-first).
        assert DOCXParser()._parse_date(raw) == date(2026, 9, 11)

    def test_november_day_first(self):
        assert DOCXParser()._parse_date("20/11/2026") == date(2026, 11, 20)

    def test_garbage_returns_none(self):
        assert DOCXParser()._parse_date("not-a-date") is None
        assert DOCXParser()._parse_date("") is None

    def test_week_cell_textual_date(self):
        info = DOCXParser()._extract_week_info("Week 3 | 25 September 2026")
        assert info["week_number"] == 3
        assert info["date"] == date(2026, 9, 25)

    def test_week_cell_numeric_date(self):
        info = DOCXParser()._extract_week_info("2 | 18/09/2026")
        assert info["week_number"] == 2
        assert info["date"] == date(2026, 9, 18)


class TestDerivedWhenMissing:
    def test_missing_date_flagged_derived(self):
        parsed = type("P", (), {})()
        parsed.weeks = []
        # Build a ParsedScheme-like object via the real parser path.
        from src.models import ParsedScheme, ParsedWeek

        scheme = ParsedScheme(
            filename="synthetic.docx",
            subject=str(Subject.SCIENCE.value),
            class_level=str(ClassLevel.BASIC_6.value),
            term="First Term",
            academic_year="2026/2027",
            weeks=[
                ParsedWeek(week_number=1, week_ending=date(2026, 9, 11)),
                ParsedWeek(week_number=2, week_ending=None),
                ParsedWeek(week_number=3, week_ending=date(2026, 9, 25)),
                ParsedWeek(week_number=4, week_ending=None),
            ],
        )
        weeks = DOCXParser()._convert_to_weeks(scheme)
        by_n = {w.week_number: w for w in weeks}

        assert by_n[1].week_ending_derived is False
        assert by_n[1].end_date == date(2026, 9, 11)

        # Week 2 has no source date → derived as previous + 7 days, flagged.
        assert by_n[2].week_ending_derived is True
        assert by_n[2].end_date == date(2026, 9, 18)

        assert by_n[3].week_ending_derived is False
        assert by_n[3].end_date == date(2026, 9, 25)

        # Week 4 gap after a source date → previous source + 7, flagged.
        assert by_n[4].week_ending_derived is True
        assert by_n[4].end_date == date(2026, 10, 2)

    def test_all_missing_first_uses_today_and_flags(self):
        from src.models import ParsedScheme, ParsedWeek

        scheme = ParsedScheme(
            filename="synthetic.docx",
            subject=str(Subject.SCIENCE.value),
            class_level=str(ClassLevel.BASIC_6.value),
            term="First Term",
            academic_year="2026/2027",
            weeks=[ParsedWeek(week_number=1, week_ending=None)],
        )
        weeks = DOCXParser()._convert_to_weeks(scheme)
        assert weeks[0].week_ending_derived is True
        assert weeks[0].end_date == date.today()


class TestNoOverwriteDownstream:
    def test_calendar_does_not_mutate_week_end_date(self):
        from src.engines.calendar_engine import CalendarEngine
        from src.models import TermConfig

        source_end = date(2026, 11, 20)
        week = Week(
            week_number=11,
            start_date=source_end,
            end_date=source_end,
            week_ending_derived=False,
            week_type=WeekType.INSTRUCTION,
            scheme_of_work_id="s1",
        )
        config = TermConfig(
            id="t1",
            scheme_of_work_id="s1",
            subject=Subject.SCIENCE,
            class_level=ClassLevel.BASIC_6,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
            teaching_days=[0, 1, 2, 3, 4],
        )
        CalendarEngine().build_calendar(config, [week])
        assert week.end_date == source_end

    def test_allocation_passes_source_week_ending(self):
        from src.engines.allocation_engine import AllocationEngine
        from src.engines.calendar_engine import CalendarEngine
        from src.models import TermConfig

        source_end = date(2026, 11, 20)
        week = Week(
            week_number=11,
            start_date=source_end,
            end_date=source_end,
            week_ending_derived=False,
            week_type=WeekType.INSTRUCTION,
            strand="Measurement",
            sub_strand="Time",
            content_standards=["B6.1 Measurement"],
            indicators=["B6.1.1.1 Measure time"],
            scheme_of_work_id="s1",
        )
        config = TermConfig(
            id="t1",
            scheme_of_work_id="s1",
            subject=Subject.SCIENCE,
            class_level=ClassLevel.BASIC_6,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
            teaching_days=[0, 1, 2, 3, 4],
        )
        calendar = CalendarEngine().build_calendar(config, [week])
        coverage = AllocationEngine().allocate([week], calendar, config)
        assert coverage.allocations
        for a in coverage.allocations:
            if a.week_number == 11:
                assert a.week_ending == source_end

    def test_export_prefers_stored_source_week_ending(self):
        from src.engines.official_ges_template import _resolve

        source = date(2026, 11, 20)
        lesson = {"week_ending": source, "lesson_date": date(2026, 11, 23)}
        resolved = _resolve("week_ending", lesson, {})
        assert "20th November, 2026" in resolved

    def test_export_falls_back_to_friday_without_source(self):
        from src.engines.official_ges_template import _resolve

        lesson = {"week_ending": None, "lesson_date": date(2026, 9, 23)}
        resolved = _resolve("week_ending", lesson, {})
        assert "25th September, 2026" in resolved

    def test_lesson_builder_carries_week_ending(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator, TermConfig

        source = date(2026, 11, 20)
        alloc = AllocatedIndicator(
            indicator_code="B6.1.1.1",
            indicator_description="B6.1.1.1 Measure time",
            content_standard_code="B6.1",
            content_standard_description="Measurement",
            strand="Measurement",
            sub_strand="Time",
            week_number=11,
            week_ending=source,
            lesson_date=date(2026, 11, 23),
            teaching_week=11,
            allocated=True,
        )
        config = TermConfig(
            id="t1",
            scheme_of_work_id="s1",
            subject=Subject.SCIENCE,
            class_level=ClassLevel.BASIC_6,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
        )
        lp = build_lesson(alloc, config, "s1")
        assert lp.week_ending == source

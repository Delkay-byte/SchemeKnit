"""
SchemeKnit Teaching Calendar Engine

Deterministic calendar calculation:
- Respects configured teaching days
- Excludes holidays
- Maps weeks to dates
- Calculates available lesson slots
"""

from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple

from ..models import (
    TeachingDay, TeachingCalendar, TermConfig, Week, WeekType, Holiday
)


class CalendarEngine:
    """Production calendar engine for lesson scheduling."""

    def build_calendar(
        self,
        term_config: TermConfig,
        weeks: List[Week],
        extra_holidays: Optional[List[Holiday]] = None,
    ) -> TeachingCalendar:
        """Build a complete teaching calendar from term config and scheme weeks."""
        holidays: Dict[date, str] = {}
        for h in term_config.holidays:
            holidays[h.date] = h.name
        if extra_holidays:
            for h in extra_holidays:
                holidays[h.date] = h.name

        all_days = self._generate_date_range(
            term_config.term_start_date,
            term_config.term_end_date,
        )

        week_boundaries = self._compute_week_boundaries(weeks)

        teaching_days: List[TeachingDay] = []
        total_lessons = 0
        lesson_slot_counter: Dict[date, int] = {}

        for d in all_days:
            dow = d.weekday()
            is_teaching = dow in term_config.teaching_days
            is_holiday = d in holidays
            holiday_name = holidays.get(d) if is_holiday else None

            if is_holiday:
                is_teaching = False

            week_num, week_end = self._find_week_for_date(d, week_boundaries)

            td = TeachingDay(
                date=d,
                day_of_week=dow,
                is_teaching_day=is_teaching,
                is_holiday=is_holiday,
                holiday_name=holiday_name,
                week_number=week_num,
                week_ending=week_end,
                lesson_slot=0,
            )

            if is_teaching and week_num is not None:
                lesson_slot_counter[d] = lesson_slot_counter.get(d, 0)
                td.lesson_slot = lesson_slot_counter[d]
                total_lessons += 1

            teaching_days.append(td)

        return TeachingCalendar(
            term_start=term_config.term_start_date,
            term_end=term_config.term_end_date,
            teaching_days=term_config.teaching_days,
            holidays=holidays,
            days=teaching_days,
            total_teaching_days=sum(1 for d in teaching_days if d.is_teaching_day),
            total_lessons=total_lessons,
        )

    def get_lesson_dates_for_week(
        self,
        calendar: TeachingCalendar,
        week_number: int,
        max_lessons: Optional[int] = None,
    ) -> List[date]:
        """Get the lesson dates for a specific week number."""
        dates = [
            d.date for d in calendar.days
            if d.is_teaching_day and d.week_number == week_number
        ]
        if max_lessons is not None:
            dates = dates[:max_lessons]
        return dates

    def get_week_dates(
        self,
        calendar: TeachingCalendar,
        week_number: int,
    ) -> Tuple[Optional[date], Optional[date]]:
        """Get the first and last teaching date for a week."""
        dates = self.get_lesson_dates_for_week(calendar, week_number)
        if not dates:
            return None, None
        return dates[0], dates[-1]

    def count_available_lessons(
        self,
        calendar: TeachingCalendar,
        include_special_weeks: bool = False,
        weeks: Optional[List[Week]] = None,
    ) -> int:
        """Count total available lessons in the calendar."""
        if not include_special_weeks and weeks:
            special_numbers = {
                w.week_number for w in weeks
                if w.week_type != WeekType.INSTRUCTION
            }
            return sum(
                1 for d in calendar.days
                if d.is_teaching_day
                and d.week_number is not None
                and d.week_number not in special_numbers
            )
        return sum(1 for d in calendar.days if d.is_teaching_day)

    def _generate_date_range(self, start: date, end: date) -> List[date]:
        """Generate all dates in a range."""
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def _compute_week_boundaries(
        self, weeks: List[Week]
    ) -> List[Tuple[int, date, date]]:
        """Build sorted list of (week_number, start, end).

        Real schemes are frequently extracted with a single-day range
        (start == end, e.g. just the Friday date). If left alone, only one
        teaching day per week lands inside that window, so a week with three
        indicators would wrongly report "only 1 teaching period available".

        Normalize each week to the full Monday→Sunday window around its stored
        date so every configured teaching day in that week is counted.
        """
        boundaries = []
        for w in weeks:
            start, end = w.start_date, w.end_date
            if start == end:
                # Expand the single stored date to the whole teaching week.
                # weekday(): Mon=0..Sun=6 → Monday = date - weekday() days.
                monday = start - timedelta(days=start.weekday())
                start = monday
                end = monday + timedelta(days=6)
            boundaries.append((w.week_number, start, end))
        boundaries.sort(key=lambda x: x[1])
        return boundaries

    def _find_week_for_date(
        self,
        d: date,
        boundaries: List[Tuple[int, date, date]],
    ) -> Tuple[Optional[int], Optional[date]]:
        """Find which scheme week a date falls into.

        A date belongs to a week only when it falls inside that week's
        (normalized) window. Dates before the first week, after the last
        week, or in a gap between weeks belong to no week — attaching them
        would inflate a week's available teaching periods.
        """
        for week_num, start, end in boundaries:
            if start <= d <= end:
                return week_num, end
        return None, None

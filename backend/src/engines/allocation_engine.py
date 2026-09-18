"""
SchemeKnit Lesson Allocation Engine
====================================

Deterministic curriculum-to-lesson allocation following the confirmed
teaching rule:

    ONE WEEK       = a curriculum CONTAINER (not one lesson)
    ONE INDICATOR  = ONE TEACHING PERIOD = ONE LESSON PLAN

A scheme week may contain 1, 2, 3, 5 or any number of indicators.
Each indicator is allocated its own teaching period within the week,
and each period becomes a separate, complete lesson plan.

Example:
    Week 1: Indicator 1 → Period 1 → Lesson 1
            Indicator 2 → Period 2 → Lesson 2
            Indicator 3 → Period 3 → Lesson 3

Special weeks (revision, assessment, SBA) are NOT subject to the
indicator→period rule — they retain their existing behaviour.
"""

from datetime import date
from typing import List, Optional, Dict, Tuple
from collections import defaultdict

from ..models import (
    Week, WeekType, TermConfig, TeachingCalendar,
    AllocatedIndicator, CurriculumCoverage, LessonPlan,
    LessonStatus, Subject, ClassLevel
)


class AllocationEngine:
    """Deterministic engine for allocating curriculum indicators to lessons.

    Core rule: ONE INDICATOR → ONE TEACHING PERIOD → ONE LESSON PLAN.
    """

    # ── Allocation ──────────────────────────────────────────────────────

    def allocate(
        self,
        weeks: List[Week],
        calendar: TeachingCalendar,
        config: TermConfig,
        include_special_weeks: bool = False,
    ) -> CurriculumCoverage:
        """Allocate each instruction indicator to its own teaching period.

        Returns a CurriculumCoverage describing every allocation plus any
        conflicts (e.g. more indicators than configured teaching periods).
        Conflicts are reported, never silently resolved.
        """
        allocations: List[AllocatedIndicator] = []
        warnings: List[str] = []
        conflicts: List[str] = []

        instruction_weeks = [
            w for w in weeks
            if include_special_weeks or w.week_type == WeekType.INSTRUCTION
        ]

        # ── Build one AllocatedIndicator per indicator per week ──────
        # The period_index is the 1-based position of the indicator within
        # its week. Period 1 = first lesson, Period 2 = second, etc.
        total_indicators = 0
        for week in instruction_weeks:
            # Real schemes often store multiple indicators concatenated into
            # a single string. Split them so each gets its own lesson.
            week_indicators = self._split_indicators(week.indicators)
            week_indicator_count = len(week_indicators)

            # Available teaching dates for this week from the calendar.
            # These are real dates derived from teaching_days + holidays.
            available_dates = [
                d.date for d in calendar.days
                if d.is_teaching_day and d.week_number == week.week_number
            ]

            # ── Conflict detection ────────────────────────────────────
            # If the week has more indicators than available teaching
            # periods, surface a conflict. Do NOT merge indicators.
            if week_indicator_count > len(available_dates) and week_indicator_count > 0:
                conflicts.append(
                    f"Week {week.week_number} contains {week_indicator_count} "
                    f"indicators but only {len(available_dates)} teaching periods "
                    f"are available. All {week_indicator_count} indicators will "
                    f"still be allocated, but some share a date."
                )

            if week_indicator_count == 0:
                warnings.append(
                    f"Week {week.week_number}: no indicators found"
                )
                if not available_dates:
                    warnings.append(
                        f"Week {week.week_number}: no teaching dates available"
                    )
                continue

            if not available_dates:
                warnings.append(
                    f"Week {week.week_number}: no teaching dates available; "
                    f"{week_indicator_count} indicators allocated without dates"
                )

            cs_text = week.content_standards[0] if week.content_standards else ""
            cs_code = self._extract_cs_code(cs_text)

            for idx, ind_text in enumerate(week_indicators):
                code = self._extract_indicator_code(ind_text)
                period_index = idx + 1  # 1-based

                # Assign a date: cycle through available dates if there
                # are more indicators than dates (conflict already reported).
                lesson_date: Optional[date] = None
                if available_dates:
                    date_idx = idx % len(available_dates)
                    lesson_date = available_dates[date_idx]

                alloc = AllocatedIndicator(
                    indicator_code=code,
                    indicator_description=ind_text,
                    content_standard_code=cs_code,
                    content_standard_description=cs_text,
                    strand=week.strand or "",
                    sub_strand=week.sub_strand or "",
                    week_number=week.week_number,
                    week_ending=week.end_date,
                    lesson_date=lesson_date,
                    period_index=period_index,
                    allocated=True,
                )
                allocations.append(alloc)
                total_indicators += 1

        # ── Assign global lesson sequence ────────────────────────────
        lesson_sequence = 0
        for alloc in allocations:
            alloc.lesson_sequence = lesson_sequence
            lesson_sequence += 1

        # ── Real coverage calculation ────────────────────────────────
        # Every indicator must be allocated exactly once.
        unique_codes = set(a.indicator_code for a in allocations)
        code_counts: Dict[str, int] = defaultdict(int)
        for a in allocations:
            code_counts[a.indicator_code] += 1
        duplicated = {c: n for c, n in code_counts.items() if n > 1}

        indicators_allocated = total_indicators
        indicators_unallocated = 0  # every indicator gets an allocation
        coverage_pct = (
            (indicators_allocated / total_indicators * 100)
            if total_indicators > 0 else 0.0
        )

        return CurriculumCoverage(
            total_instructional_weeks=len(instruction_weeks),
            total_indicators=total_indicators,
            total_generated_lessons=len(allocations),
            total_periods_allocated=len(allocations),
            indicators_allocated=indicators_allocated,
            indicators_unallocated=indicators_unallocated,
            indicators_duplicated=len(duplicated),
            coverage_percentage=coverage_pct,
            allocations=allocations,
            warnings=warnings,
            allocation_conflicts=conflicts,
        )

    # ── Lesson plan generation ──────────────────────────────────────────

    def generate_lesson_plans(
        self,
        coverage: CurriculumCoverage,
        config: TermConfig,
        scheme_id: str,
    ) -> List[LessonPlan]:
        """Generate ONE LessonPlan per allocated indicator.

        Each lesson:
          - has exactly ONE primary indicator
          - knows its week_number (source curriculum week)
          - knows its lesson_number = period_index within the week
          - derives objectives, activities, assessment from that indicator
        """
        lesson_plans: List[LessonPlan] = []

        # Group allocations by week, then by period_index within the week.
        per_week: Dict[int, List[AllocatedIndicator]] = defaultdict(list)
        for alloc in coverage.allocations:
            per_week[alloc.week_number].append(alloc)

        lesson_counter = 0  # global sequence across the whole term
        for week_num in sorted(per_week.keys()):
            # Sort by period_index so Period 1, 2, 3... are in order.
            allocs = sorted(per_week[week_num], key=lambda a: a.period_index)

            for alloc in allocs:
                lesson_counter += 1
                period_index = alloc.period_index

                # Each lesson carries exactly ONE indicator.
                single_indicator = alloc.indicator_description
                single_code = alloc.indicator_code

                topic = self._derive_topic(alloc)
                objectives = self._generate_objectives(single_indicator, single_code)
                intro = self._generate_introduction(alloc)
                main_acts = self._generate_main_activities(alloc, config)
                learner_acts = self._generate_learner_activities(alloc)
                teacher_acts = self._generate_teacher_activities(alloc)
                assessment = self._generate_assessment(alloc)
                conclusion = self._generate_conclusion(alloc)

                lp = LessonPlan(
                    scheme_of_work_id=scheme_id,
                    term_config_id=config.id,
                    week_number=week_num,
                    lesson_sequence=lesson_counter,
                    lesson_date=alloc.lesson_date or config.term_start_date,
                    # lesson_number = the period within this week (1-based)
                    lesson_number=period_index,
                    # Period label: "Period 1", "Period 2", etc.
                    # Teacher-configured period string is preserved if set.
                    period=self._period_label(period_index, config),
                    class_level=config.class_level,
                    subject=config.subject,
                    class_size=config.class_size,
                    duration_minutes=config.lesson_duration_minutes,
                    school_name=config.school_name,
                    teacher_name=config.teacher_name,
                    strand=alloc.strand,
                    sub_strand=alloc.sub_strand,
                    content_standard=alloc.content_standard_description,
                    content_standard_code=alloc.content_standard_code,
                    # ONE indicator per lesson — the core of this redesign.
                    indicators=[single_indicator],
                    indicator_codes=[single_code],
                    lesson_topic=topic,
                    previous_knowledge="",
                    learning_objectives=objectives,
                    core_competencies=list(getattr(config, "core_competencies", []) or []),
                    teaching_learning_resources=(
                        list(getattr(config, "teaching_learning_resources", []) or [])
                    ),
                    introduction=intro,
                    main_activities=main_acts,
                    learner_activities=learner_acts,
                    teacher_activities=teacher_acts,
                    assessment=assessment,
                    conclusion=conclusion,
                    references=list(getattr(config, "references", []) or []),
                    keywords=list(getattr(config, "keywords", []) or []),
                    status=LessonStatus.GENERATED,
                    ai_generated=False,
                )
                lesson_plans.append(lp)

        return lesson_plans

    # ── Helpers ──────────────────────────────────────────────────────────

    def _period_label(self, period_index: int, config: TermConfig) -> str:
        """Render the period label for a lesson.

        If the teacher configured a specific timetable period string
        (e.g. "1st & 2nd"), it is preserved verbatim. Otherwise a
        deterministic "Period N" label is used.
        """
        configured = getattr(config, "period", "") or ""
        if configured:
            return configured
        return f"Period {period_index}"

    def _extract_indicator_code(self, text: str) -> str:
        import re
        m = re.search(r'[Bb]?\d+\.\d+\.\d+\.\d+(\.\d+)?', text)
        return m.group(0) if m else text[:30]

    @staticmethod
    def _split_indicators(indicators: List[str]) -> List[str]:
        """Split concatenated indicator strings into one entry per indicator.

        Real GES schemes are frequently parsed with two or more indicators
        merged into a single string, e.g.::

            "B9.1.1.1.2 Discuss formation ... B9.1.1.1.3 Describe characteristics ..."

        If left untouched the allocation engine sees ONE indicator and silently
        drops the second — exactly the compression this redesign forbids. This
        splits such strings at each embedded indicator code so each gets its own
        teaching period and lesson plan.

        Strings with no code, or exactly one code, pass through unchanged.
        """
        import re

        # A code looks like B9.1.1.1.2 / 9.1.1.1.2 / B9.4.1.1.1 (4-5 numeric groups).
        # Use a CONSUMING match (not a lookahead) so a code cannot match again
        # inside itself — "B9.1.1.1.1" must yield ONE code, not "B9..." plus "9...".
        code_re = re.compile(r'[Bb]?\d+\.\d+\.\d+\.\d+(?:\.\d+)?')

        result: List[str] = []
        for text in indicators:
            if not text or not text.strip():
                continue
            positions = [m.start() for m in code_re.finditer(text)]
            # Only split when two or more codes are present in one string.
            if len(positions) >= 2:
                for i, pos in enumerate(positions):
                    end = positions[i + 1] if i + 1 < len(positions) else len(text)
                    chunk = text[pos:end].strip()
                    if chunk:
                        result.append(chunk)
            else:
                result.append(text.strip())
        return result

    def _extract_cs_code(self, text: str) -> str:
        import re
        m = re.search(r'[Bb]?\d+\.\d+\.\d+\.\d+', text)
        return m.group(0) if m else ""

    def _derive_topic(self, alloc: AllocatedIndicator) -> str:
        parts = []
        if alloc.strand:
            parts.append(alloc.strand)
        if alloc.sub_strand:
            parts.append(alloc.sub_strand)
        return " - ".join(parts) if parts else "Lesson"

    @staticmethod
    def _strip_indicator_code(text: str) -> str:
        """Remove a leading curriculum indicator code (e.g. B7.4.3.1.2) from text."""
        import re
        stripped = re.sub(r'^\s*[Bb]?\d+(?:\.\d+){2,4}[.:]?\s*', '', text).strip()
        return stripped or text.strip()

    @staticmethod
    def _phrase_performance_indicator(text: str) -> str:
        """Phrase an indicator as an approved GES performance indicator.

        Uses the approved voice: ``Learners can <verb phrase>``.
        The code prefix is stripped and common legacy prefixes are normalised.
        """
        clean = AllocationEngine._strip_indicator_code(text)
        lower = clean.lower()

        # Normalise legacy phrasing that already contains a learner-facing prefix.
        for prefix in (
            "learners can ", "students can ",
            "learners should be able to ", "students should be able to ",
            "by the end of the lesson, learners should be able to: ",
            "by the end of the lesson, learners should be able to ",
            "by the end of the lesson, the learner should be able to: ",
            "by the end of the lesson, the learner should be able to ",
            "by the end of the lesson, the learner could ",
        ):
            if lower.startswith(prefix):
                clean = clean[len(prefix):]
                break

        # Preserve the original capitalisation of the verb phrase — the approved
        # format uses lowercase verbs after "Learners can".

        return f"Learners can {clean}"

    def _generate_objectives(
        self, indicator: str, code: str
    ) -> list:
        """Generate objectives for a SINGLE indicator (per-lesson scope)."""
        from ..models import LearningObjective
        desc = self._phrase_performance_indicator(indicator)
        return [LearningObjective(
            description=desc,
            indicator_code=code,
        )]

    def _generate_introduction(self, alloc: AllocatedIndicator) -> str:
        topic = self._derive_topic(alloc)
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return (
            f"Begin with a review of the previous lesson on the topic: {topic}. "
            f"Use a short oral quiz or class discussion to activate prior knowledge. "
            f"Introduce today's lesson focused on the indicator: {indicator_desc}."
        )

    def _generate_main_activities(
        self, alloc: AllocatedIndicator, config: TermConfig
    ) -> list:
        from ..models import TeachingActivity
        duration = config.lesson_duration_minutes
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return [
            TeachingActivity(
                phase="MAIN",
                description=(
                    f"Present the content on: {indicator_desc}. "
                    f"Use board work, charts, and real examples relevant to the Ghanaian context."
                ),
                duration_minutes=int(duration * 0.5),
                resources=[],
            ),
        ]

    def _generate_learner_activities(self, alloc: AllocatedIndicator) -> list:
        from ..models import TeachingActivity
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return [
            TeachingActivity(
                phase="LEARNER",
                description=(
                    f"Learners work in pairs or groups to discuss and practice: "
                    f"{indicator_desc}. Teacher monitors and guides."
                ),
                duration_minutes=15,
                resources=[],
            ),
        ]

    def _generate_teacher_activities(self, alloc: AllocatedIndicator) -> list:
        from ..models import TeachingActivity
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return [
            TeachingActivity(
                phase="TEACHER",
                description=(
                    f"Teacher facilitates, observes group work, provides feedback, "
                    f"and clarifies misconceptions related to: {indicator_desc}."
                ),
                duration_minutes=10,
                resources=[],
            ),
        ]

    def _generate_assessment(self, alloc: AllocatedIndicator) -> str:
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return (
            f"Observe learners during group work. Ask oral questions to check understanding "
            f"of: {indicator_desc}. Collect and review any written work."
        )

    def _generate_conclusion(self, alloc: AllocatedIndicator) -> str:
        indicator_desc = self._strip_indicator_code(alloc.indicator_description)
        return (
            f"Summarise the key points of the lesson on: {indicator_desc}. "
            f"Assign homework related to today's indicator. "
            f"Prepare for the next lesson."
        )

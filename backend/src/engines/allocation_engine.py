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
from typing import List, Optional, Dict, Tuple, Any
from collections import defaultdict

from ..models import (
    Week, WeekType, TermConfig, TeachingCalendar,
    AllocatedIndicator, CurriculumCoverage, LessonPlan,
    LessonStatus, Subject, ClassLevel
)


def is_special_period_text(text) -> bool:
    """True when text is a special-period label, not curriculum content.

    Shares the parser's keyword list so parse and allocation agree on what a
    special period is (PART O). Defensive net for weeks persisted BEFORE the
    parser fix: rows saved as ``instruction`` whose cells hold "MID-TERM ..."
    are re-classified at allocation time instead of becoming fake lessons.
    """
    from ..parsers.docx_parser import SPECIAL_WEEK_KEYWORDS
    t = (text or "").strip().lower()
    return any(kw in t for kw in SPECIAL_WEEK_KEYWORDS)


def week_is_non_instructional(week) -> bool:
    """True when a week is a special period with NO teaching content (PART S).

    The distinction the product requires:
      * REVISION PERIOD WITH ACTUAL TEACHING CONTENT — the source row carries
        real indicators/strand text (a revision week that genuinely teaches)
        → False: it keeps allocating lessons.
      * NON-INSTRUCTIONAL SPECIAL PERIOD — a MID-TERM/VACATION/EXAM label row
        (reclassification cleared its curriculum fields) or a special week
        with no indicator/strand content at all → True: never a fake lesson.
    """
    if getattr(week, "special_period_label", ""):
        return True
    if getattr(week, "week_type", WeekType.INSTRUCTION) == WeekType.INSTRUCTION:
        return False
    has_indicators = bool(list(getattr(week, "indicators", None) or []))
    has_strand = bool((getattr(week, "strand", None) or "").strip())
    has_sub_strand = bool((getattr(week, "sub_strand", None) or "").strip())
    return not (has_indicators or has_strand or has_sub_strand)


def reclassify_special_weeks(weeks):
    """Normalize special-period weeks in place (PART O/P).

    A week claiming INSTRUCTION whose strand/sub-strand/indicator text is a
    special-period label ("MID-TERM (05-11-2026 to 06-11-2026)") is
    re-classified as a special period: its curriculum fields are cleared, the
    verbatim label is kept as metadata, and the normalized type is set.
    Normal instructional weeks are never touched.
    """
    from ..models import SpecialPeriodType
    for w in weeks or []:
        if getattr(w, "week_type", WeekType.INSTRUCTION) != WeekType.INSTRUCTION:
            continue
        candidates = [
            getattr(w, "strand", None) or "",
            getattr(w, "sub_strand", None) or "",
            *(list(getattr(w, "indicators", None) or [])),
        ]
        label = next((c.strip() for c in candidates if is_special_period_text(c)), "")
        if not label:
            continue
        # Curriculum authority stays with the source: a special-period label is
        # metadata, never a strand/indicator/lesson topic. A revision week
        # that carries REAL teaching content ("B9.1.1.2.1 Explain kinetic
        # theory") keeps its content: only the LABEL cell is a period name.
        def _is_label(cell: str) -> bool:
            c = (cell or "").strip()
            return bool(c) and is_special_period_text(c)
        w.special_period_label = label
        w.special_period_type = SpecialPeriodType.classify(label).value
        if _is_label(w.strand or ""):
            w.strand = None
        if _is_label(w.sub_strand or ""):
            w.sub_strand = None
        w.indicators = [t for t in (w.indicators or []) if not _is_label(t)]
        w.content_standards = [
            c for c in (w.content_standards or []) if not _is_label(c)
        ]
        # Weeks whose ONLY content was the label become special periods.
        still_content = (
            bool(w.indicators)
            or bool((w.strand or "").strip())
            or bool((w.sub_strand or "").strip())
        )
        if not still_content:
            w.week_type = WeekType.OTHER
    return weeks


def scheme_has_indicators(weeks) -> bool:
    """True when any instruction week actually carries an indicator.

    WAPEF Nursery schemes legitimately have no Content Standard / Indicator
    column — their weekly row (subject + strand + sub-strand) IS the
    curriculum unit. Forcing the indicator pipeline there would fabricate
    curriculum data, which the product never does.
    """
    for w in weeks or []:
        if getattr(w, "week_type", WeekType.INSTRUCTION) != WeekType.INSTRUCTION:
            continue
        if w.indicators:
            return True
    return False


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

        Teaching model (§6-§9):
          ONE INDICATOR → ONE TEACHING PERIOD → ONE LESSON PLAN

        Indicators are processed in curriculum order. Each is placed in the next
        available teaching period of its source week. When a source week contains
        more indicators than it has teaching periods, the surplus CARRY FORWARD
        to the following teaching week(s) — in order, never merged, never
        dropped, never duplicated. Unused periods in a week are left unused; a
        later week's indicator is never moved backwards into an earlier week.

        Every allocation keeps BOTH the source curriculum week and the actual
        teaching week so the lesson stays connected to its scheme origin while
        accurately representing when it is taught.
        """
        allocations: List[AllocatedIndicator] = []
        warnings: List[str] = []
        conflicts: List[str] = []

        # ── Special-period normalization (PART O/P) ─────────────────────
        # Defensive net for weeks persisted before the parser classified
        # special periods: "MID-TERM ..." rows stored as instruction are
        # re-classified here so they can never become fake lessons.
        reclassify_special_weeks(weeks)

        # Week selection: instruction weeks always; other weeks only when the
        # teacher explicitly includes special weeks. A REVISION week with real
        # teaching content therefore allocates ONLY when the teacher opts in
        # (PART S: the product treats an explicitly included revision week as
        # real teaching), while a MID-TERM label row never does — see the
        # special-period skip inside the loop below.
        instruction_weeks = sorted(
            (w for w in weeks
             if include_special_weeks or w.week_type == WeekType.INSTRUCTION),
            key=lambda w: w.week_number,
        )

        if not instruction_weeks:
            return CurriculumCoverage()

        # ── Nursery-style schemes (WAPEF_NURSERY source variant) ────────────
        # The source has no indicators. The weekly row (subject + strand +
        # sub-strand + resources) IS the unit of curriculum focus: one week =
        # one teaching period = one lesson. No indicator code and no content
        # standard is EVER fabricated for these rows. A special week carries
        # no teachable row content, so it never triggers this path.

        # ── Nursery-style schemes (WAPEF_NURSERY source variant) ────────────
        # The source has no indicators. The weekly row (subject + strand +
        # sub-strand + resources) IS the unit of curriculum focus: one week =
        # one teaching period = one lesson. No indicator code and no content
        # standard is EVER fabricated for these rows.
        if not scheme_has_indicators(instruction_weeks):
            return self._allocate_week_units(
                instruction_weeks, calendar, config, warnings, conflicts)

        last_teaching_week = instruction_weeks[-1].week_number

        # Carried-over indicators awaiting a teaching period in a later week.
        # Each pending item carries its SOURCE week's curriculum context (strand,
        # sub-strand, content standard) so a carried lesson still describes the
        # right curriculum even though it is taught later.
        pending: List[Dict[str, Any]] = []
        total_indicators = 0
        #: period counters per ACTUAL teaching week (1-based).
        period_counter: Dict[int, int] = defaultdict(int)

        def _make_alloc(item: Dict[str, Any], teaching_week: int,
                        lesson_date: Optional[date], period_index: int,
                        carry_forward: bool, needs_review: bool) -> AllocatedIndicator:
            return AllocatedIndicator(
                indicator_code=item["code"],
                indicator_description=item["text"],
                content_standard_code=item["cs_code"],
                content_standard_description=item["cs_text"],
                strand=item["strand"],
                sub_strand=item["sub_strand"],
                week_number=item["source_week"],
                week_ending=item["week_ending"],
                week_ending_derived=bool(item.get("week_ending_derived", False)),
                source_resources=list(item.get("source_resources") or []),
                lesson_date=lesson_date,
                period_index=period_index,
                allocated=True,
                teaching_week=teaching_week,
                carry_forward=carry_forward,
                carry_forward_from_week=(item["source_week"] if carry_forward else None),
                needs_review=needs_review,
            )

        for week in instruction_weeks:
            # ── Special periods are NOT lessons (PART Q/S) ───────────
            # A mid-term/exam/vacation (or non-teaching revision) week never
            # becomes a lesson plan and never consumes a lesson-generation
            # unit — even when special weeks are included in the allocation.
            # A metadata-only allocation row is emitted so the review UI can
            # show "Special Period: <label> — this period does not contain a
            # normal lesson" in the week table without any fake curriculum.
            # A REVISION week WITH actual teaching content stays instructional
            # (PART S): only content-less special periods are non-instructional.
            label = (getattr(week, "special_period_label", "") or "").strip()
            if week_is_non_instructional(week):
                if include_special_weeks:
                    special_alloc = AllocatedIndicator(
                        indicator_code="",
                        indicator_description="",
                        content_standard_code="",
                        content_standard_description="",
                        strand="",
                        sub_strand="",
                        week_number=week.week_number,
                        week_ending=week.end_date,
                        week_ending_derived=bool(
                            getattr(week, "week_ending_derived", False)),
                        source_resources=[],
                        lesson_date=None,
                        period_index=0,
                        allocated=False,
                        teaching_week=week.week_number,
                        carry_forward=False,
                        carry_forward_from_week=None,
                        needs_review=False,
                        special_period_label=label or (week.strand or "").strip(),
                        special_period_type=(
                            getattr(week, "special_period_type", "")
                            or "other_non_instructional"
                        ),
                        is_special_period=True,
                    )
                    allocations.append(special_alloc)
                warnings.append(
                    f"Week {week.week_number}: special period"
                    f"{f' ({label})' if label else ''} — not a teaching week; "
                    f"no lesson generated."
                )
                continue

            # Real teaching dates for this week (teaching days minus holidays).
            available_dates = sorted(
                d.date for d in calendar.days
                if d.is_teaching_day and d.week_number == week.week_number
            )

            # Real schemes store multiple indicators concatenated in one string.
            week_indicators = self._split_indicators(week.indicators)
            cs_text = week.content_standards[0] if week.content_standards else ""
            cs_code = self._extract_cs_code(cs_text)

            own_items = [
                {
                    "code": self._extract_indicator_code(t),
                    "text": t,
                    "cs_code": cs_code,
                    "cs_text": cs_text,
                    "strand": week.strand or "",
                    "sub_strand": week.sub_strand or "",
                    "source_week": week.week_number,
                    "week_ending": week.end_date,
                    "week_ending_derived": bool(
                        getattr(week, "week_ending_derived", False)
                    ),
                    # Source TLRs for THIS subject + source week only.
                    "source_resources": list(week.resources or []),
                }
                for t in week_indicators
            ]

            # ── Conflict detection (§7) ──────────────────────────────
            # A source week with more indicators than its own teaching periods.
            if len(own_items) > len(available_dates) and own_items:
                overflow = len(own_items) - len(available_dates)
                conflicts.append(
                    f"Week {week.week_number} contains {len(own_items)} "
                    f"indicators but only {len(available_dates)} teaching periods "
                    f"are available; {overflow} indicator"
                    f"{'s' if overflow != 1 else ''} will continue in the next "
                    f"teaching week(s)."
                )

            if not own_items and not pending:
                warnings.append(f"Week {week.week_number}: no indicators found")
                if not available_dates:
                    warnings.append(
                        f"Week {week.week_number}: no teaching dates available"
                    )
                continue

            # Carried indicators fill the earliest periods, then this week's own
            # indicators. Anything that does not fit becomes the new backlog.
            work = pending + own_items
            pending = []

            for idx, item in enumerate(work):
                if idx >= len(available_dates):
                    # No period left this week → carry forward to next week.
                    pending.append(item)
                    continue

                carry = item["source_week"] != week.week_number
                period_counter[week.week_number] += 1
                allocations.append(_make_alloc(
                    item,
                    teaching_week=week.week_number,
                    lesson_date=available_dates[idx],
                    period_index=period_counter[week.week_number],
                    carry_forward=carry,
                    needs_review=False,
                ))
                total_indicators += 1

        # ── Any indicators still pending have no teaching week left ──────
        # (the scheme ran out of teaching weeks). They are still allocated —
        # never dropped — but flagged for teacher review.
        for item in pending:
            carry = item["source_week"] != last_teaching_week
            period_counter[last_teaching_week] += 1
            allocations.append(_make_alloc(
                item,
                teaching_week=last_teaching_week,
                lesson_date=None,
                period_index=period_counter[last_teaching_week],
                carry_forward=carry,
                needs_review=True,
            ))
            total_indicators += 1
            warnings.append(
                f"Indicator {item['code']} (Week {item['source_week']}) has no "
                f"remaining teaching period in the term and needs review."
            )

        # ── Assign global lesson sequence (curriculum order) ─────────────
        # Special-period metadata rows do NOT take a lesson sequence: they are
        # not lessons and never consume a generation unit (PART S).
        seq = 0
        for alloc in allocations:
            if getattr(alloc, "is_special_period", False):
                alloc.lesson_sequence = -1
            else:
                alloc.lesson_sequence = seq
                seq += 1

        # ── Real coverage calculation ────────────────────────────────
        # Special-period metadata rows are not lessons (PART S): they are
        # excluded from every lesson/indicator count.
        real_allocations = [a for a in allocations
                            if not getattr(a, "is_special_period", False)]
        code_counts: Dict[str, int] = defaultdict(int)
        for a in real_allocations:
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
            total_generated_lessons=len(real_allocations),
            total_periods_allocated=len(real_allocations),
            indicators_allocated=indicators_allocated,
            indicators_unallocated=indicators_unallocated,
            indicators_duplicated=len(duplicated),
            coverage_percentage=coverage_pct,
            allocations=allocations,
            warnings=warnings,
            allocation_conflicts=conflicts,
        )

    # ── Lesson plan generation ──────────────────────────────────────────

    def _allocate_week_units(
        self,
        instruction_weeks: List[Week],
        calendar: TeachingCalendar,
        config: TermConfig,
        warnings: List[str],
        conflicts: List[str],
    ) -> CurriculumCoverage:
        """Allocate ONE lesson per weekly curriculum row (no indicator source).

        Used when a scheme legitimately carries no indicators (WAPEF Nursery):
        each instructional week becomes one lesson whose curriculum focus is
        the source row itself — subject/strand/sub-strand/resources verbatim.
        The empty indicator fields stay empty; nothing is invented.
        """
        allocations: List[AllocatedIndicator] = []

        for week in instruction_weeks:
            # ── Special periods are NOT lessons (PART Q/S) ───────────
            # (Nursery-style path: same rule, no quota consumption.)
            label = (getattr(week, "special_period_label", "") or "").strip()
            if week_is_non_instructional(week):
                warnings.append(
                    f"Week {week.week_number}: special period"
                    f"{f' ({label})' if label else ''} — not a teaching week; "
                    f"no lesson generated."
                )
                continue

            available_dates = sorted(
                d.date for d in calendar.days
                if d.is_teaching_day and d.week_number == week.week_number
            )
            if not available_dates:
                warnings.append(
                    f"Week {week.week_number}: no teaching dates available"
                )
            # The weekly row is the focus. One lesson per week, placed on the
            # first teaching date of that week (no carry-forward exists: the
            # row is the unit, and inventing an overflow split would fabricate
            # structure the source does not have).
            lesson_date = available_dates[0] if available_dates else None
            cs_text = week.content_standards[0] if week.content_standards else ""
            allocations.append(AllocatedIndicator(
                # No indicator exists in the source; the code stays empty and
                # the description records the actual source row focus.
                indicator_code="",
                indicator_description="",
                content_standard_code="",
                content_standard_description=cs_text,
                strand=week.strand or "",
                sub_strand=week.sub_strand or "",
                week_number=week.week_number,
                week_ending=week.end_date,
                week_ending_derived=bool(
                    getattr(week, "week_ending_derived", False)),
                source_resources=list(week.resources or []),
                lesson_date=lesson_date,
                period_index=1,
                allocated=True,
                teaching_week=week.week_number,
                carry_forward=False,
                carry_forward_from_week=None,
                needs_review=lesson_date is None,
            ))

        for seq, alloc in enumerate(allocations):
            alloc.lesson_sequence = seq

        total = len(allocations)
        return CurriculumCoverage(
            total_instructional_weeks=len(instruction_weeks),
            total_indicators=total,
            total_generated_lessons=total,
            total_periods_allocated=total,
            indicators_allocated=total,
            indicators_unallocated=0,
            indicators_duplicated=0,
            coverage_percentage=100.0 if total else 0.0,
            allocations=allocations,
            warnings=warnings,
            allocation_conflicts=conflicts,
        )

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
        # Generation Engine V3: the deterministic subject-aware lesson builder
        # composes ONE coherent three-phase lesson per indicator. The old
        # helpers below remain for API compatibility but are no longer the
        # generation path.
        from ..curriculum.lesson_builder import build_lesson

        ordered = sorted(coverage.allocations, key=lambda a: a.lesson_sequence)
        lesson_plans: List[LessonPlan] = []
        lesson_counter = 0
        for idx, alloc in enumerate(ordered):
            # Special-period metadata rows produce NO lesson plan (PART Q/S).
            if getattr(alloc, "is_special_period", False):
                continue
            lesson_counter += 1
            previous_indicator = (
                ordered[idx - 1].indicator_description if idx > 0 else None
            )
            next_indicator = (
                ordered[idx + 1].indicator_description
                if idx < len(ordered) - 1 else None
            )
            # KG-style rows carry a code-only indicator cell, so passing the
            # raw description to the builder gives it nothing to phrase
            # ("Build on the previous lesson ('')"). Substitute the row's own
            # curriculum focus (sub-strand) so continuation weeks like the
            # KG scheme's repeated "My School Family" rows still open with an
            # honest link to the previous lesson instead of cloning it.
            # Indicatorless Nursery rows are the same situation one step
            # further: the description is empty outright, and the scheme marks
            # genuine continuation weeks with IDENTICAL sub-strands
            # (Nursery Numeracy W5/W6 "Pairing"). Those two weeks must not
            # receive the same starter, so the previous row's sub-strand is
            # the link here too — never an invented indicator.
            from ..curriculum.lesson_builder import is_code_only_indicator as _ico
            if previous_indicator and _ico(previous_indicator):
                previous_indicator = ordered[idx - 1].sub_strand or None
            elif not previous_indicator:
                prev_row = ordered[idx - 1]
                if prev_row.sub_strand and prev_row.sub_strand == alloc.sub_strand:
                    previous_indicator = prev_row.sub_strand
            if next_indicator and _ico(next_indicator):
                next_indicator = ordered[idx + 1].sub_strand or None
            elif not next_indicator:
                nxt_row = ordered[idx + 1] if idx + 1 < len(ordered) else None
                if nxt_row and nxt_row.sub_strand and nxt_row.sub_strand == alloc.sub_strand:
                    next_indicator = nxt_row.sub_strand
            lp = build_lesson(
                alloc, config, scheme_id,
                previous_indicator=previous_indicator,
                next_indicator=next_indicator,
            )
            # Curriculum order and period label are assigned here so the
            # builder stays position-independent (and deterministic).
            lp.lesson_sequence = lesson_counter
            lp.period = self._period_label(alloc.period_index, config)
            # Special-period metadata flows onto the lesson row (PART O/R) so
            # review/export can present it as a period, not a lesson.
            lp.special_period_label = alloc.special_period_label
            lp.special_period_type = alloc.special_period_type
            lesson_plans.append(lp)

        return lesson_plans

    # ── Helpers ──────────────────────────────────────────────────────────

    def _period_label(self, period_index: int, config: TermConfig) -> str:
        """Render the period label for a lesson (PART K).

        Period/timing is LESSON-SPECIFIC teacher data: when the teacher
        configured a timetable period string (e.g. "1st & 2nd") it is used
        verbatim. When they did not, the field stays EMPTY — never "Period N",
        "0", "-" or "N/A" — so exports and review show a genuinely blank
        cell the teacher can fill in.
        """
        configured = getattr(config, "period", "") or ""
        return configured.strip()

    def _extract_indicator_code(self, text: str) -> str:
        import re
        m = re.search(r'[BbKk]?\d+\.\d+\.\d+\.\d+(\.\d+)?', text)
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
        # KG schemes use the same shape with a K prefix (K2.1.1.1.1-3). Use a
        # CONSUMING match (not a lookahead) so a code cannot match again
        # inside itself — "B9.1.1.1.1" must yield ONE code, not "B9..." plus "9...".
        code_re = re.compile(r'[BbKk]?\d+\.\d+\.\d+\.\d+(?:\.\d+)?')

        result: List[str] = []
        for text in indicators:
            if not text or not text.strip():
                continue
            positions: List[int] = []
            prev_code: Optional[str] = None
            prev_end = 0
            for m in code_re.finditer(text):
                code = m.group(0)
                # A repeated code separated only by whitespace is the SAME
                # indicator, not the next one: KG ranges come back from the
                # parser as "K2.1.1.1.1 K2.1.1.1.1-3" (code + rejoined range).
                # Splitting there would allocate one code-only phantom lesson.
                if (prev_code is not None and code == prev_code
                        and not text[prev_end:m.start()].strip()):
                    continue
                positions.append(m.start())
                prev_code = code
                prev_end = m.end()
            # Only split when two or more DISTINCT code positions are present.
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
        m = re.search(r'[BbKk]?\d+\.\d+\.\d+\.\d+', text)
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
        """Remove a leading curriculum indicator code (e.g. B7.4.3.1.2 / K2.1.1.1) from text."""
        import re
        stripped = re.sub(r'^\s*[BbKk]?\d+(?:\.\d+){2,4}[.:]?\s*', '', text).strip()
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

"""
SchemeKnit Lesson Allocation Engine
====================================

Deterministic curriculum-to-lesson allocation following the authoritative
weekly-coverage rule (Priority 1):

    SOURCE OCCURRENCE → WEEKLY LESSON PLAN

A source occurrence is ONE indicator entry extracted from the teacher's
scheme for a given source week. Every instructional source occurrence gets
EXACTLY ONE lesson plan, and that lesson plan stays in its SOURCE week.

    Week 5 (source): occurrence 1 → Lesson (Week 5)
                     occurrence 2 → Lesson (Week 5)
                     occurrence 3 → Lesson (Week 5)
                     occurrence 4 → Lesson (Week 5)

Teaching periods (``config.period``, teaching days, "2 periods", "Monday"…)
are TIMETABLE METADATA describing when the school teaches. They never cap,
defer, move or rebalance curriculum lesson plans. A week with 2 teaching
periods and 4 source occurrences produces 4 lesson plans in that week.

Special weeks (revision, assessment, SBA) are NOT subject to the
indicator→period rule — they retain their existing behaviour.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict, Tuple, Any
from collections import defaultdict
import re

from ..models import (
    Week, WeekType, TermConfig, TeachingCalendar,
    AllocatedIndicator, CurriculumCoverage, LessonPlan,
    LessonStatus, Subject, ClassLevel
)
from ..ai_resource_text import normalize_text_items


@dataclass
class BuildContext:
    """What one lesson was built from (Priority 4 quality gate rebuild).

    Holds the exact allocation handed to ``build_lesson`` — its
    ``indicator_description`` is the source string WITH the curriculum code —
    plus the neighbouring-indicator context and the pattern id that shaped it,
    so the gate can rebuild a failed lesson deterministically with a DIFFERENT
    pattern through the same code path.
    """

    alloc: AllocatedIndicator
    previous_indicator: Optional[str] = None
    next_indicator: Optional[str] = None
    pattern_id: str = ""


@dataclass
class BuildLedger:
    """Per-run record of every lesson's build context + the batch history."""

    #: lesson id → what it was built from.
    contexts: Dict[str, BuildContext] = field(default_factory=dict)
    #: The batch history after the run (pattern/fingerprint state the gate
    #: needs to rebuild with the same variation context).
    history: Any = None


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


_SPECIAL_DATE_RE = re.compile(
    r"(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})"
)


def special_period_date_range(label: str) -> Optional[Tuple[date, date]]:
    """Extract the (start, end) date range a special-period label declares.

    A mixed week prints its period as ``"MID-TERM (05-11-2026 to 06-11-2026)"``.
    Teaching begins AFTER that period ends, so the allocation must know the
    range to keep those days out of the teaching dates. Returns None when the
    label carries no dates (e.g. a bare ``"REVISION"``) — nothing is excluded.
    """
    if not label:
        return None
    dates = []
    for token in _SPECIAL_DATE_RE.findall(label):
        parsed = _parse_dayfirst_date(token)
        if parsed:
            dates.append(parsed)
    if len(dates) < 2:
        return None
    return min(dates), max(dates)


def _parse_dayfirst_date(token: str) -> Optional[date]:
    """Parse a day-first numeric date (DD-MM-YYYY). Returns None if invalid."""
    parts = re.split(r"[-/\.]", token)
    if len(parts) != 3:
        return None
    try:
        d, m, y = (int(p) for p in parts)
    except ValueError:
        return None
    if y < 100:
        y += 2000
    if not (1 <= d <= 31 and 1 <= m <= 12 and 2020 <= y <= 2030):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def is_special_period_label(text) -> bool:
    """STRICT label test (Defect D2): the whole cell is period vocabulary.

    :func:`is_special_period_text` is deliberately broad (keyword substring),
    which is right for scanning a week's cells for a period row but WRONG for
    deciding whether a specific cell's content IS the period: "Examine the
    nature of God" and "Examples: ironing in bulk" contain ``exam`` yet are
    curriculum. Every destructive decision — clearing a strand, dropping an
    indicator, naming a special period — uses this strict form, so real
    content can never be classified away (or silently dropped) by accident.
    """
    from ..parsers.docx_parser import is_special_label_text
    return is_special_label_text(text)


def week_is_non_instructional(week) -> bool:
    """True when a week is a special period with NO teaching content (PART S).

    The distinction the product requires:
      * REVISION PERIOD WITH ACTUAL TEACHING CONTENT — the source row carries
        real indicators/strand text (a revision week that genuinely teaches)
        → False: it keeps allocating lessons.
      * NON-INSTRUCTIONAL SPECIAL PERIOD — a MID-TERM/VACATION/EXAM label row
        (reclassification cleared its curriculum fields) or a special week
        with no indicator/strand content at all → True: never a fake lesson.
      * MIXED week — the source row holds a special period AND real teaching
        content (Defect 4). The special segment is metadata only; the teaching
        content remains allocatable → False. The special segment itself is
        never turned into a lesson.
    """
    if getattr(week, "week_type", None) == WeekType.MIXED:
        # Mixed weeks carry teaching content by definition; only the special
        # segment is excluded. A "mixed" week with no teaching content at all
        # is really a pure special period.
        has_content = (
            bool(list(getattr(week, "indicators", None) or []))
            or bool((getattr(week, "strand", None) or "").strip())
            or bool((getattr(week, "sub_strand", None) or "").strip())
        )
        return not has_content
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
        # Strict label test (Defect D2): only a cell that IS a period label
        # triggers reclassification. The broad keyword scan would treat
        # "Examine the nature of God"/"Examples: ..." (contain "exam") as a
        # period and CLEAR real indicators out of the scheme.
        label = next((c.strip() for c in candidates if is_special_period_label(c)), "")
        if not label:
            continue
        # Curriculum authority stays with the source: a special-period label is
        # metadata, never a strand/indicator/lesson topic. A revision week
        # that carries REAL teaching content ("B9.1.1.2.1 Explain kinetic
        # theory") keeps its content: only the LABEL cell is a period name.
        def _is_label(cell: str) -> bool:
            c = (cell or "").strip()
            return bool(c) and is_special_period_label(c)
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
        # Weeks that ALSO carry real teaching content are MIXED (Defect 4):
        # the special segment stays a period, the teaching segment stays
        # allocatable — neither is discarded.
        still_content = (
            bool(w.indicators)
            or bool((w.strand or "").strip())
            or bool((w.sub_strand or "").strip())
        )
        if not still_content:
            w.week_type = WeekType.OTHER
        else:
            w.week_type = WeekType.MIXED
    return weeks


def scheme_has_indicators(weeks) -> bool:
    """True when any instruction week actually carries an indicator.

    WAPEF Nursery schemes legitimately have no Content Standard / Indicator
    column — their weekly row (subject + strand + sub-strand) IS the
    curriculum unit. Forcing the indicator pipeline there would fabricate
    curriculum data, which the product never does.
    """
    for w in weeks or []:
        # MIXED weeks carry real teaching content, so their indicators count
        # (Defect 7: a mixed week's teaching segment stays allocatable).
        if getattr(w, "week_type", WeekType.INSTRUCTION) not in (
            WeekType.INSTRUCTION, WeekType.MIXED
        ):
            continue
        if w.indicators:
            return True
    return False


def _source_occurrence_id(week_number: int, position: int, code: str) -> str:
    """Stable identity of ONE source occurrence in the teacher's scheme.

    Format ``week<source_week>:<position_in_week>:<indicator_code>``. The id
    is derived ONLY from the source document's own structure — source week,
    position of the indicator entry within that week, and its indicator code.
    The timetable never participates, so the identity survives timetable
    changes, and the same indicator code appearing in two different source
    weeks yields two distinct ids (legitimate distinct occurrences).
    """
    safe = re.sub(r"[^A-Za-z0-9.]+", "_", (code or "").strip()).strip("_") or "row"
    return f"week{week_number}:{position}:{safe}"


class AllocationEngine:
    """Deterministic engine for allocating curriculum occurrences to lessons.

    Core rule: ONE SOURCE OCCURRENCE → ONE LESSON PLAN, IN ITS SOURCE WEEK.
    """

    # ── Allocation ──────────────────────────────────────────────────────

    def allocate(
        self,
        weeks: List[Week],
        calendar: TeachingCalendar,
        config: TermConfig,
        include_special_weeks: bool = False,
    ) -> CurriculumCoverage:
        """Allocate exactly one lesson-plan occurrence per source occurrence.

        Canonical rule (Priority 1 — weekly curriculum coverage semantics):

            SOURCE OCCURRENCE → WEEKLY LESSON PLAN

        Each instructional source occurrence in a source week becomes exactly
        one allocation, and that allocation keeps the source week as BOTH its
        curriculum week and its teaching week. Nothing is carried forward,
        rebalanced, deferred or dropped because of timetable capacity — the
        teacher's scheme defines curriculum placement, the timetable only
        describes context.

        Teaching dates are still attached when the calendar has one for the
        occurrence's position (honest scheduling context); when a week holds
        more occurrences than teaching days — or the timetable is unspecified
        — the lesson still belongs to its source week and the date simply stays
        empty for the teacher to fill in. A warning states that state plainly;
        it never blocks generation.

        Repeated indicator codes in DIFFERENT source weeks are distinct source
        occurrences and are never treated as duplicates. Duplicate detection
        keys on the source occurrence identity (week + position + code).
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
        # MIXED weeks (special period + real teaching content in the same
        # source row, Defect 4/7) always stay in the allocation: their special
        # segment is excluded from lesson allocation, their teaching segment
        # remains fully allocatable.
        instruction_weeks = sorted(
            (w for w in weeks
             if include_special_weeks
             or w.week_type in (WeekType.INSTRUCTION, WeekType.MIXED)),
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

        #: period index counter per SOURCE week (1-based lesson ordinal within
        #: the week). Teaching-week counters no longer exist: a lesson's week
        #: IS its source week.
        period_counter: Dict[int, int] = defaultdict(int)
        total_indicators = 0

        def _make_alloc(item: Dict[str, Any], teaching_week: int,
                        lesson_date: Optional[date], period_index: int,
                        carry_forward: bool, needs_review: bool) -> AllocatedIndicator:
            return AllocatedIndicator(
                indicator_code=item["code"],
                indicator_description=self._indicator_description(item["text"]),
                source_occurrence_id=item.get("source_occurrence_id", ""),
                content_standard_code=item["cs_code"],
                content_standard_description=item["cs_text"],
                strand=item["strand"],
                sub_strand=item["sub_strand"],
                week_number=item["source_week"],
                week_ending=item["week_ending"],
                week_ending_derived=bool(item.get("week_ending_derived", False)),
                source_resources=normalize_text_items(
                    list(item.get("source_resources") or [])),
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
                        # Strict test (D2): the fallback names the period only
                        # when the strand cell IS a label — curriculum prose
                        # that contains a keyword is never period metadata.
                        special_period_label=label or (
                            (week.strand or "").strip()
                            if is_special_period_label(week.strand)
                            else ""
                        ),
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

            # A MIXED week holds a special period AND teaching. Teaching begins
            # AFTER the period ends, so the period's own days are removed from
            # the teaching dates — the period end date is never the teaching
            # start. A label with no dates (bare "REVISION") excludes nothing.
            period_range = special_period_date_range(
                getattr(week, "special_period_label", "") or ""
            )
            if period_range:
                p_start, p_end = period_range
                available_dates = [
                    d for d in available_dates if not (p_start <= d <= p_end)
                ]

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

            # ── Defect D5: the same source cell parsed twice allocates twice ──
            # A week whose indicator list repeats the SAME (code, text) pair
            # would emit one allocation per copy: duplicated lessons plus a
            # false "duplicated indicator" report. First occurrence wins.
            deduped_items: List[Dict[str, Any]] = []
            seen_items = set()
            for item in own_items:
                key = (item["code"], item["text"])
                if key in seen_items:
                    continue
                seen_items.add(key)
                deduped_items.append(item)
            own_items = deduped_items

            if not own_items:
                warnings.append(f"Week {week.week_number}: no indicators found")
                if not available_dates:
                    warnings.append(
                        f"Week {week.week_number}: teaching periods not specified"
                    )
                continue

            # ── Source occurrence identity (Priority 1) ──────────────────
            # Each deduped entry IS one source occurrence of this scheme. Its
            # identity is (source week, position in the week, indicator code)
            # — stable across regeneration and never derived from the timetable.
            for position, item in enumerate(own_items):
                item["source_occurrence_id"] = _source_occurrence_id(
                    week.week_number, position, item["code"]
                )

            # ── Timetable context, never a cap (Priority 1) ───────────────
            # The timetable may hold fewer teaching days than the week has
            # curriculum occurrences (or none at all). That is context for the
            # teacher, NOT a reason to defer, move or drop a lesson plan: the
            # week's lesson count follows its source occurrences.
            if len(own_items) > len(available_dates):
                n_occ = len(own_items)
                n_days = len(available_dates)
                warnings.append(
                    f"Week {week.week_number}: {n_occ} curriculum indicator"
                    f"{'s' if n_occ != 1 else ''} · {n_days} timetable period"
                    f"{'s' if n_days != 1 else ''} — {n_occ} lesson plan"
                    f"{'s' if n_occ != 1 else ''} required for this week. "
                    f"Teaching periods describe the timetable; they do not "
                    f"cap, defer or move curriculum lesson plans."
                )
                if n_days == 0:
                    warnings.append(
                        f"Week {week.week_number}: teaching periods not "
                        f"specified — lesson plans still belong to Week "
                        f"{week.week_number}."
                    )

            # ── The allocation: one lesson plan per source occurrence ─────
            # Every occurrence is allocated HERE, in its own source week.
            # Teaching dates are attached to the first N occurrences as
            # scheduling context; occurrences beyond the timetable keep an
            # empty date (the lesson builder falls back to the week-ending
            # date) — they are never moved to a later week.
            for idx, item in enumerate(own_items):
                lesson_date = (
                    available_dates[idx] if idx < len(available_dates) else None
                )
                period_counter[week.week_number] += 1
                allocations.append(_make_alloc(
                    item,
                    teaching_week=week.week_number,
                    lesson_date=lesson_date,
                    period_index=period_counter[week.week_number],
                    carry_forward=False,
                    needs_review=False,
                ))
                total_indicators += 1

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
        # Duplicate detection keys on the SOURCE OCCURRENCE identity (week +
        # position + code), never on indicator_code alone: the same indicator
        # code in two different source weeks is two legitimate occurrences,
        # not a duplicate allocation. A duplicate can only be the SAME source
        # occurrence allocated more than once — which the per-week dedupe
        # above prevents at build time.
        occurrence_counts: Dict[str, int] = defaultdict(int)
        for a in real_allocations:
            occurrence_counts[
                a.source_occurrence_id
                or f"week{a.week_number}:{a.indicator_code}"
            ] += 1
        duplicated = {k: n for k, n in occurrence_counts.items() if n > 1}

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
                source_occurrence_id=_source_occurrence_id(
                    week.week_number, 0, ""),
                content_standard_code="",
                content_standard_description=cs_text,
                strand=week.strand or "",
                sub_strand=week.sub_strand or "",
                week_number=week.week_number,
                week_ending=week.end_date,
                week_ending_derived=bool(
                    getattr(week, "week_ending_derived", False)),
                # CANONICAL RESOURCES (PART 6): week.resources may arrive as
                # one comma-joined string (legacy rows persisted before the
                # parser normalized). Split into individual entries here so
                # every allocated lesson carries structured TLRs.
                source_resources=normalize_text_items(
                    list(week.resources or [])),
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
        *,
        ledger: Optional[BuildLedger] = None,
    ) -> List[LessonPlan]:
        """Generate ONE LessonPlan per allocated indicator.

        Each lesson:
          - has exactly ONE primary indicator
          - knows its week_number (source curriculum week)
          - knows its lesson_number = period_index within the week
          - derives objectives, activities, assessment from that indicator

        Lesson Pattern + Variation (Layers 3/4): a batch-level history is
        built once for the whole scheme/subject/class/term. Each lesson is
        then assigned the best-fitting TEACHING PATTERN through the curriculum
        evidence + subject pedagogy, with a bounded novelty penalty from the
        patterns already used in the batch. Curriculum fit always dominates:
        a pattern is never chosen merely to look different. The selected
        pattern supplies the teaching SHAPE; the indicator remains the
        substance, and indicator-specific content (assessment, assignments,
        resources, keywords) is untouched.
        """
        # Generation Engine V3: the deterministic subject-aware lesson builder
        # composes ONE coherent three-phase lesson per indicator. The old
        # helpers below remain for API compatibility but are no longer the
        # generation path.
        from ..curriculum.lesson_builder import build_lesson
        from ..curriculum.batch_context import build_batch_history

        ordered = sorted(coverage.allocations, key=lambda a: a.lesson_sequence)
        lesson_plans: List[LessonPlan] = []
        lesson_counter = 0

        # Layer 4: one batch history for the whole generation run. Provenance
        # is scheme/subject/class/term-scoped so history never leaks across
        # schemes, and the first lesson of a batch starts with an empty slate.
        batch_history = build_batch_history(config, scheme_id)

        def _source_indicator_text(a: AllocatedIndicator) -> str:
            """The indicator cell as the SOURCE scheme printed it (Defect D5).

            Allocations store the description WITHOUT its curriculum code, but
            the lesson keeps the source indicator string verbatim — lessons
            preserve the curriculum's own indicator text (code included) so
            review, export and provenance quote the scheme exactly. Rebuilt
            from code + description; an ``indicator_code`` that is not a real
            code (the extractor's prose fallback) is never re-attached.

            The real-code test recognises EVERY canonical shape
            (``src/curriculum/__init__.py``): the dotted-only test above used
            to reject "B7/JHS1 1.1.1.1" (RME / Social Studies / Creative Arts
            schemes), so the code was never re-attached and a partially
            stripped description reached the builder as prose.
            """
            from ..curriculum import INDICATOR_CODE_RE

            code = (a.indicator_code or "").strip()
            desc = a.indicator_description or ""
            if not desc:
                return code
            if not (INDICATOR_CODE_RE.fullmatch(code)
                    or re.fullmatch(r'[BbKk]?\d+(?:\.\d+){2,4}', code)):
                return desc
            return f"{code} {desc}"

        for idx, alloc in enumerate(ordered):
            # Special-period metadata rows produce NO lesson plan (PART Q/S).
            if getattr(alloc, "is_special_period", False):
                continue
            lesson_counter += 1
            source_text = _source_indicator_text(alloc)
            previous_indicator = (
                _source_indicator_text(ordered[idx - 1]) if idx > 0 else None
            )
            next_indicator = (
                _source_indicator_text(ordered[idx + 1])
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
            # ── Layer 3/4: select this lesson's teaching pattern ──────────
            # Deterministic and evidence-driven: curriculum fit (indicator
            # activity + subject pedagogy + corpus evidence) is scored, and a
            # BOUNDED novelty penalty from patterns already used lets equally
            # fitting patterns vary. The indicator, objective, assessment and
            # assignments are never changed by the pattern.
            from ..curriculum.batch_context import select_pattern_for_alloc
            try:
                lesson_pattern = select_pattern_for_alloc(
                    alloc, config, batch_history,
                    previous_indicator=previous_indicator,
                )
                if lesson_pattern is not None:
                    selection_verb = getattr(lesson_pattern, "id", "")
                    batch_history.note_selection(selection_verb)
            except Exception:
                # Pattern selection must never break a deterministic batch.
                lesson_pattern = None
            lp = build_lesson(
                # Defect D5: the builder reads ``indicator_description`` as the
                # lesson's indicator text; hand it the source string (rebuilt
                # above) while the allocation row keeps the code-less
                # description. Behaviour of every lesson is byte-identical to
                # the source-preserved contract.
                (alloc.model_copy(update={"indicator_description": source_text})
                 if source_text != (alloc.indicator_description or "") else alloc),
                config, scheme_id,
                previous_indicator=previous_indicator,
                next_indicator=next_indicator,
                pattern=lesson_pattern,
                batch_history=batch_history,
            )
            if ledger is not None:
                # Priority 4: remember exactly what this lesson was built from
                # so the quality gate can rebuild it deterministically with a
                # different teaching pattern (same evidence, same neighbours).
                ledger.contexts[lp.id] = BuildContext(
                    alloc=(
                        alloc.model_copy(update={"indicator_description": source_text})
                        if source_text != (alloc.indicator_description or "")
                        else alloc
                    ),
                    previous_indicator=previous_indicator,
                    next_indicator=next_indicator,
                    pattern_id=getattr(lesson_pattern, "id", "") or "",
                )
            # Curriculum order and period label are assigned here so the
            # builder stays position-independent (and deterministic).
            # Stable numbering (Priority 3): when the pipeline stamped a
            # full-scheme ordinal on this allocation BEFORE the subset filter,
            # the lesson keeps that number — so a lesson previewed as #12 of 30
            # is still #12 when only week 5 was generated, and per-lesson
            # drafts keyed by lesson_sequence cannot drift onto the wrong
            # lesson. Without a stamp (direct engine callers, full runs) the
            # dense 1-based counter over the filtered list is unchanged.
            ordinal = getattr(alloc, "lesson_ordinal", None)
            if isinstance(ordinal, int) and ordinal > 0:
                lp.lesson_sequence = ordinal
            else:
                lp.lesson_sequence = lesson_counter
            lp.period = self._period_label(alloc.period_index, config)
            # Special-period metadata flows onto the lesson row (PART O/R) so
            # review/export can present it as a period, not a lesson.
            lp.special_period_label = alloc.special_period_label
            lp.special_period_type = alloc.special_period_type
            lesson_plans.append(lp)

        if ledger is not None:
            # The gate rebuilds with the same variation context the batch used.
            ledger.history = batch_history

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
    def _indicator_description(text: str) -> str:
        """The indicator cell WITHOUT its curriculum code (Defect D5).

        The code already lives in ``indicator_code``; keeping it in the
        description too made every consumer that renders the description show
        it twice (the provenance panel prints ``indicator — indicator_text``,
        the lessons list prints ``indicator_codes[0]`` above ``indicators[0]``)
        and produced bare-code descriptions like "K2.1.1.1.1" for KG rows. A
        code-only cell has NO description — "" — never the code as its own
        prose.

        The removal uses the CANONICAL code shape list (``INDICATOR_CODE_RE``,
        which covers "B7.1.1.1.1", "B7/JHS1 1.1.1.1", "B7/JHS1.1.1.1.1" and
        bare "1.1.1.1"). The old dotted-only pattern matched the "1.1.1.1"
        TAIL inside "B7/JHS1 1.1.1.1 Attributes of God …", leaving "B7/JHS1"
        in the prose — which the lesson then phrased as "Learners can B7/JHS1
        Attributes of God …". Only the code is removed: the source's own
        separator (" : ", " . ") stays, so the rebuilt source string keeps
        quoting the scheme verbatim.
        """
        if not text:
            return ""
        from ..curriculum import INDICATOR_CODE_RE
        # Only complete codes are removed: anything else in the cell (the
        # source's own " : " separator, an orphan ".2" fragment) is the
        # scheme's verbatim text and must survive so the rebuilt source
        # string keeps quoting the scheme exactly. Fragments are cleaned at
        # the phrasing layer (``_first_clause`` / ``_learner_phrase``), never
        # here.
        desc = INDICATOR_CODE_RE.sub(" ", text).strip()
        if not re.search(r"[A-Za-z]", desc):
            return ""
        return desc

    @staticmethod
    def _strip_indicator_code(text: str) -> str:
        """Remove a leading curriculum code in ANY canonical shape.

        Uses the shared ``CODE_PREFIX_RE`` so "B7/JHS1 1.1.1.1" (RME, Social
        Studies, Creative Arts schemes) and "K2.1.1.1.1-3" ranges are removed
        exactly like the dotted "B7.4.3.1.2" — the dotted-only pattern used
        here left "/JHS" fragments in learner-facing prose.
        """
        from ..curriculum import CODE_PREFIX_RE
        stripped = CODE_PREFIX_RE.sub("", text).strip()
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

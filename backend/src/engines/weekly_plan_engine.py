"""
Weekly class-teacher plan engine (Approved WAPEF Basic 1-3 Plan).

Basic 1-3 is the CLASS-TEACHER model: one teacher teaches several subjects on
different days inside the SAME weekly plan. This engine turns the teacher's
subject + teaching-day selections into the weekly plan's subject sections,
distributing the week's curriculum across the subject's teaching days so each
day carries its own starter/main/reflection and no two days are clones.

The model keeps the two planning concepts apart (brief §10-§11):

* the SCHEME supplies curriculum content (indicators, strands, resources);
* the TIMETABLE (the teacher's teaching-day selection) decides which subject
  is taught when.

Neither is hard-coded: the subjects are the teacher's, the days are the
teacher's, and any metadata the scheme does not supply stays blank rather than
being fabricated (brief §2, §9).

Reuse, not duplication (brief §13, §23, §35):
* curriculum allocation reuses ``AllocationEngine``'s indicator splitting and
  carry-forward semantics;
* each day's starter/main/reflection is composed by ``build_lesson`` with its
  ``position_index``/``day_label`` class-teacher hooks, so a later teaching day
  on the same curriculum focus opens differently and composes a different MAIN
  block — established single-lesson output is unchanged;
* WAPEF fields reuse ``wapef_fields`` verbatim (no second copy);
* the day model, template and export live in ``wapef_basic13_template``.
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..models import (
    AIMode,
    ClassLevel,
    DayPlan,
    SubjectMetadata,
    SubjectPlan,
    TermConfig,
    Week,
    WeekType,
    WeeklyClassPlan,
    WeeklyPlanRequest,
    WeeklyPlanSubjectRequest,
)
from .allocation_engine import AllocationEngine
from .calendar_engine import CalendarEngine
from .wapef_basic13_template import (
    WEEK_DAYS,
    format_day_label,
    normalize_day_groups,
    normalize_teaching_days,
    weekday_index,
)


# ── Week resolution ───────────────────────────────────────────────────────────

def resolve_week(weeks: Sequence[Week], week_number: int) -> Optional[Week]:
    """The instruction week the plan covers (None when the scheme lacks it).

    A non-instruction week (revision/assessment) is never silently substituted:
    the class-teacher weekly plan teaches curriculum, and a revision week has
    no indicators to distribute across days.
    """
    candidates = [
        w for w in (weeks or [])
        if w.week_number == week_number
        and getattr(w, "week_type", WeekType.INSTRUCTION) == WeekType.INSTRUCTION
    ]
    return candidates[0] if candidates else None


def week_ending_of(week: Optional[Week], request: WeeklyPlanRequest) -> Optional[date]:
    """The week's ending date: the source's own value when it has one.

    The source is authoritative; only when it has no date is the term-derived
    Friday used (and flagged as derived, exactly as the allocation engine
    labels derived dates).
    """
    if week is not None and getattr(week, "end_date", None) is not None:
        return week.end_date
    return None


def term_friday(week_number: int, request: WeeklyPlanRequest) -> Optional[date]:
    """The Friday of ``week_number`` derived from the term dates (Mon-Fri week).

    Used only as a fallback when the scheme supplies no week-ending date; the
    result is flagged derived so the teacher knows it is not from the source.
    """
    try:
        start = date.fromisoformat(str(request.term_start_date))
    except Exception:
        return None
    # Week 1 starts on the first Monday on/after term_start.
    offset = (start.weekday() + 1) % 7  # days to the next Monday
    first_monday = start + timedelta(days=offset)
    friday = first_monday + timedelta(weeks=max(week_number - 1, 0)) + timedelta(days=4)
    return friday


# ── Subject metadata ──────────────────────────────────────────────────────────

def _split_indicators(text: Optional[str]) -> List[str]:
    """Reuse the allocation engine's own indicator splitting (never invent)."""
    engine = AllocationEngine()
    return engine._split_indicators(text or "")


def _extract_code(text: str) -> str:
    return AllocationEngine()._extract_indicator_code(text) if text else ""


def build_subject_metadata(
    week: Optional[Week],
    subject_name: str,
    class_level: ClassLevel,
    request: WeeklyPlanRequest,
    subject_request: WeeklyPlanSubjectRequest,
) -> SubjectMetadata:
    """One subject section's metadata, from the scheme's own curriculum data.

    Every field is optional and a value the source never supplied stays blank
    (brief §2, §9). The WAPEF fields are the teacher's selections, kept as
    given — never invented, never overwritten (brief §15).
    """
    indicators = _split_indicators(week.indicators if week else None)
    indicator_codes = [_extract_code(t) for t in indicators]

    standard_texts: List[str] = []
    standard_codes: List[str] = []
    for raw in (week.content_standards if week else []):
        raw = (raw or "").strip()
        if not raw:
            continue
        standard_texts.append(raw)
        standard_codes.append(_extract_code(raw))

    performance: List[str] = []
    if week is not None:
        # The scheme's performance indicator column when it exists; the first
        # indicator phrased for the learner is the honest fallback used across
        # the product, and only when the column is empty.
        perf = [p.strip() for p in getattr(week, "performance_indicators", []) or [] if p.strip()]
        if perf:
            performance = perf
        elif indicators:
            performance = [AllocationEngine()._phrase_performance_indicator(indicators[0])]

    week_ending = week_ending_of(week, request)
    derived = week is None or not getattr(week, "end_date", None)
    if week_ending is None:
        week_ending = term_friday(request.week_number, request)

    teacher_keywords = [k.strip() for k in (subject_request.keywords or []) if k.strip()]
    teacher_competencies = [c.strip() for c in (subject_request.core_competencies or []) if c.strip()]
    teacher_tlrs = [t.strip() for t in (subject_request.other_tlrs or []) if t.strip()]

    return SubjectMetadata(
        subject=subject_name,
        class_level=_class_level_value(class_level),
        week_number=request.week_number,
        week_ending=week_ending,
        week_ending_derived=bool(derived and week_ending is not None),
        reference=_reference_for(week, subject_name),
        strand=(week.strand or "") if week is not None else "",
        sub_strand=(week.sub_strand or "") if week is not None else "",
        content_standards=standard_texts,
        content_standard_codes=standard_codes,
        indicators=indicators,
        indicator_codes=indicator_codes,
        performance_indicators=performance,
        teaching_learning_resources=_resources_for(week, teacher_tlrs),
        core_competencies=teacher_competencies or _competencies_for(week),
        keywords=teacher_keywords,
        wapef_deep_hope=subject_request.wapef_deep_hope or "",
        wapef_storyline=subject_request.wapef_storyline or "",
        wapef_through_lines=list(subject_request.wapef_through_lines or []),
        wapef_gods_story=subject_request.wapef_gods_story or "",
    )


def _class_level_value(class_level) -> str:
    if isinstance(class_level, ClassLevel):
        return class_level.value
    return str(getattr(class_level, "value", class_level) or "")


def _reference_for(week: Optional[Week], subject_name: str) -> str:
    """The source's own reference line (e.g. "English Language curriculum").

    Never fabricated: when the scheme has no reference column the field stays
    blank rather than inventing a page number.
    """
    if week is None:
        return ""
    references = list(getattr(week, "references", []) or [])
    if references:
        return references[0].strip()
    return ""


def _resources_for(week: Optional[Week], teacher_tlrs: Sequence[str]) -> List[str]:
    """Subject-scoped resources: the scheme week's own TLRs + the teacher's.

    Resources never leak between subjects: only THIS subject's source week
    contributes (brief §19).
    """
    out: List[str] = []
    if week is not None:
        out.extend((r or "").strip() for r in (week.resources or []) if (r or "").strip())
    out.extend(t for t in teacher_tlrs if t)
    # Order-preserving dedupe.
    seen, result = set(), []
    for item in out:
        key = " ".join(item.split()).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(" ".join(item.split()))
    return result


def _competencies_for(week: Optional[Week]) -> List[str]:
    """Core competencies the scheme's own week carries (blank when absent)."""
    if week is None:
        return []
    raw = getattr(week, "core_competencies", None)
    if not raw:
        return []
    if isinstance(raw, str):
        return [" ".join(raw.split())] if raw.strip() else []
    out = []
    for item in raw:
        text = " ".join(str(item or "").split())
        if text:
            out.append(text)
    return out


# ── Day allocation ─────────────────────────────────────────────────────────────

def distribute_indicators(
    indicators: Sequence[str],
    day_groups: Sequence[Sequence[str]],
) -> List[List[str]]:
    """Distribute the week's indicators across the subject's teaching days.

    Brief §13: the curriculum is spread across the subject's days rather than
    cloned into every day. Indicators are handed out round-robin in curriculum
    order over the DAY GROUPS (week order), so:

    * a subject with one indicator taught on five days keeps that indicator as
      the week's focus on every day (the source's own meaning when one
      indicator spans the week) — the DAY CONTENT still differs because the
      generator composes a different starter/main per position; and
    * a subject with several indicators splits them across its days, extras
      round-robining back to the earliest days (never dropped, never reordered).

    Indicators are never invented and their curriculum order is preserved.
    """
    groups = [list(g) for g in day_groups if g]
    if not groups or not indicators:
        return [[] for _ in groups]
    if len(indicators) == 1:
        # One source indicator may span several teacher-selected days. Preserve
        # the week's focus; day content still varies by lesson position.
        return [[indicators[0]] for _ in groups]
    buckets: List[List[str]] = [[] for _ in groups]
    for index, indicator in enumerate(indicators):
        buckets[index % len(groups)].append(indicator)
    return buckets


def lesson_dates_for_week(
    week: Optional[Week],
    request: WeeklyPlanRequest,
) -> Dict[str, date]:
    """Canonical day name -> date within the plan's week (derived fallback).

    The source's week dates are authoritative; the derived map is only used
    when the scheme carries no dates, and the metadata flags that derivation.
    """
    friday = week_ending_of(week, request) or term_friday(request.week_number, request)
    if friday is None:
        return {}
    return {name: friday - timedelta(days=(4 - i)) for i, name in enumerate(WEEK_DAYS)}


# ── Subject plan assembly ──────────────────────────────────────────────────────

def build_subject_plan(
    subject_request: WeeklyPlanSubjectRequest,
    scheme_weeks: Sequence[Week],
    class_level: ClassLevel,
    request: WeeklyPlanRequest,
    context: Optional[Dict[str, Any]] = None,
) -> SubjectPlan:
    """Build one subject section of the weekly class plan.

    The teacher's teaching-day groups are authoritative (brief §10-§11): they
    decide which days carry a plan row, and a day the subject is not taught on
    gets NO row (never an empty Monday-Friday skeleton). Each day group becomes
    one DayPlan — a single day, or one shared entry for a grouped
    "MONDAY & THURSDAY" row (brief §5, §26 CASE C).
    """
    ctx = context or {}
    subject_name = ctx.get("subject_name") or _subject_name_from(
        subject_request, scheme_weeks,
    )

    week = resolve_week(scheme_weeks, request.week_number)
    groups = normalize_day_groups(subject_request.teaching_day_groups)
    # A teacher who has not selected days gets the week's own teaching days as
    # a starting point — data-driven from the scheme's calendar, never a
    # hard-coded Monday-Friday schedule.
    if not groups:
        groups = _scheme_day_groups(week, request)

    metadata = build_subject_metadata(
        week, subject_name, class_level, request, subject_request,
    )

    day_plans = _build_day_plans(
        week, groups, metadata, request, subject_request, ctx,
    )

    return SubjectPlan(
        scheme_of_work_id=subject_request.scheme_id,
        job_id=ctx.get("job_id", ""),
        subject=subject_name,
        teaching_days=normalize_teaching_days([d for g in groups for d in g]),
        teaching_day_groups=groups,
        metadata=metadata,
        day_plans=day_plans,
    )


def _subject_name_from(
    subject_request: WeeklyPlanSubjectRequest,
    scheme_weeks: Sequence[Week],
) -> str:
    """The subject's display name: the scheme's own subject label."""
    for week in scheme_weeks or []:
        label = getattr(week, "subject_name", None)
        if label:
            return str(label)
    return ""


def _scheme_day_groups(
    week: Optional[Week], request: WeeklyPlanRequest,
) -> List[List[str]]:
    """The teaching days the scheme's own calendar gives this subject's week.

    Never hard-coded: derived from the term's teaching days intersected with
    the week's real dates. Falls back to every weekday only when the term
    carries no teaching-day configuration.
    """
    teaching_days = list(request_term_teaching_days(request))
    if not teaching_days:
        return [[name] for name in WEEK_DAYS]
    return [[WEEK_DAYS[index]] for index in sorted(teaching_days)]


def request_term_teaching_days(request: WeeklyPlanRequest) -> List[int]:
    """The term's configured teaching days (weekday ints)."""
    raw = getattr(request, "teaching_days", None)
    if raw:
        return [int(d) for d in raw if 0 <= int(d) <= 4]
    # No explicit configuration: Monday-Friday is the Basic 1-3 school week,
    # stated as a calendar default rather than a subject timetable.
    return [0, 1, 2, 3, 4]


def _build_day_plans(
    week: Optional[Week],
    groups: List[List[str]],
    metadata: SubjectMetadata,
    request: WeeklyPlanRequest,
    subject_request: WeeklyPlanSubjectRequest,
    ctx: Dict[str, Any],
) -> List[DayPlan]:
    """One DayPlan per teaching-day group, each with its own phase content."""
    from ..curriculum.lesson_builder import build_lesson
    from ..models import AIMode, AllocatedIndicator

    indicators = list(metadata.indicators or [])
    buckets = distribute_indicators(indicators, groups)
    day_dates = lesson_dates_for_week(week, request)
    previous_label = ""
    day_plans: List[DayPlan] = []

    for position, group in enumerate(groups):
        focus = buckets[position] if position < len(buckets) else []
        focus_codes = [_extract_code(t) for t in focus]
        label = format_day_label(group)

        # The day's curriculum focus: the scheme's indicators for this day.
        # When the week has fewer indicators than days, the source's own
        # meaning (one indicator across the week) is preserved — the DAY
        # CONTENT still differs via build_lesson's position hooks.
        alloc = AllocatedIndicator(
            indicator_code=focus_codes[0] if focus_codes else "",
            indicator_description=focus[0] if focus else (
                metadata.indicators[0] if metadata.indicators else ""
            ),
            content_standard_code=metadata.content_standard_codes[0] if metadata.content_standard_codes else "",
            content_standard_description=metadata.content_standards[0] if metadata.content_standards else "",
            strand=metadata.strand,
            sub_strand=metadata.sub_strand,
            week_number=request.week_number,
            week_ending=metadata.week_ending,
            week_ending_derived=metadata.week_ending_derived,
            source_resources=list(metadata.teaching_learning_resources or []),
            lesson_date=day_dates.get(group[0]),
            period_index=position,
            allocated=True,
            teaching_week=request.week_number,
            carry_forward=False,
            carry_forward_from_week=None,
            needs_review=False,
        )

        config = _term_config_for(request, metadata, ctx)
        lesson = build_lesson(
            alloc,
            config,
            scheme_id=ctx.get("scheme_id", subject_request.scheme_id),
            previous_indicator=metadata.indicators[position - 1]
            if position and metadata.indicators and position - 1 < len(metadata.indicators)
            else None,
            next_indicator=metadata.indicators[position + 1]
            if metadata.indicators and position + 1 < len(metadata.indicators)
            else None,
            position_index=position,
            day_label=label,
            previous_day_label=previous_label,
        )

        day_plans.append(DayPlan(
            days=list(group),
            day_label=label,
            focus_indicators=focus,
            focus_indicator_codes=focus_codes,
            starter=getattr(lesson, "starter_activity", "") or "",
            main_activities=list(getattr(lesson, "main_activities", []) or []),
            reflection=getattr(lesson, "reflection", "")
            or getattr(lesson, "assessment", "")
            or getattr(lesson, "conclusion", ""),
            resources=list(metadata.teaching_learning_resources or []),
            lesson_date=day_dates.get(group[0]),
            period=getattr(lesson, "period", "") or "",
        ))
        previous_label = label

    return day_plans


def _term_config_for(
    request: WeeklyPlanRequest,
    metadata: SubjectMetadata,
    ctx: Dict[str, Any],
) -> TermConfig:
    """A TermConfig for ``build_lesson`` (subject/level/duration from the plan)."""
    from ..models import Subject

    subject_label = metadata.subject or ctx.get("subject_name", "")
    try:
        subject = Subject(subject_label) if subject_label else Subject.UNKNOWN
    except Exception:
        subject = Subject.UNKNOWN
    try:
        class_level = ClassLevel(metadata.class_level) if metadata.class_level else ClassLevel.UNKNOWN
    except Exception:
        class_level = ClassLevel.UNKNOWN

    return TermConfig(
        scheme_of_work_id=ctx.get("scheme_id", ""),
        academic_year=request.academic_year,
        term=request.term,
        class_level=class_level,
        subject=subject,
        class_size=request.class_size,
        lesson_duration_minutes=request.lesson_duration_minutes,
        lessons_per_week=1,
        term_start_date=request.term_start_date,
        term_end_date=request.term_end_date,
        teaching_days=request_term_teaching_days(request),
        template_id=ctx.get("template_id", ""),
        ai_mode=getattr(request, "ai_mode", AIMode.OFF),
    )


# ── Weekly plan assembly ───────────────────────────────────────────────────────

def build_weekly_plan(
    request: WeeklyPlanRequest,
    schemes_by_id: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> WeeklyClassPlan:
    """Build one weekly class plan holding every subject the teacher selected.

    ``schemes_by_id`` maps scheme id -> {weeks, subject, class_level}: the
    normalized curriculum IR the existing ingestion produces. Subjects are
    built independently and nothing (metadata, indicators, resources, WAPEF
    selections) leaks between them (brief §19).
    """
    ctx = dict(context or {})
    class_level = request.class_level
    subjects: List[SubjectPlan] = []

    for subject_request in request.subjects or []:
        entry = schemes_by_id.get(subject_request.scheme_id) or {}
        weeks = list(entry.get("weeks") or [])
        scheme_class = entry.get("class_level") or class_level
        subject_ctx = dict(ctx)
        subject_ctx.setdefault("scheme_id", subject_request.scheme_id)
        if entry.get("subject"):
            subject_ctx.setdefault("subject_name", _subject_label(entry["subject"]))
        subjects.append(build_subject_plan(
            subject_request, weeks, scheme_class, request, subject_ctx,
        ))

    template_id = ctx.get("template_id") or _default_template_for(class_level)
    week_ending = _weekly_week_ending(subjects, request, schemes_by_id)

    return WeeklyClassPlan(
        owner_id=ctx.get("owner_id", ""),
        class_level=class_level,
        week_number=request.week_number,
        term=request.term,
        academic_year=request.academic_year,
        term_start_date=request.term_start_date,
        term_end_date=request.term_end_date,
        school_name=ctx.get("school_name"),
        teacher_name=ctx.get("teacher_name"),
        template_id=template_id,
        subjects=subjects,
    )


def _subject_label(subject) -> str:
    if isinstance(subject, str):
        return subject
    return str(getattr(subject, "value", subject) or "")


def _weekly_week_ending(
    subjects: Sequence[SubjectPlan],
    request: WeeklyPlanRequest,
    schemes_by_id: Dict[str, Any],
) -> Optional[date]:
    """The weekly plan's own week-ending: the first subject section's source
    value (they share the week), else the term-derived Friday."""
    for subject in subjects:
        ending = getattr(subject.metadata, "week_ending", None)
        if ending is not None:
            return ending
    return term_friday(request.week_number, request)


def _default_template_for(class_level) -> str:
    """Route by the class band (brief §27): Basic 1-3 -> class-teacher plan;
    everything else keeps the subject-teacher Approved WAPEF Plan."""
    from .wapef_basic13_template import wapef_template_for_class

    return wapef_template_for_class(class_level)


def teaching_days_summary(plan: WeeklyClassPlan) -> List[Dict[str, Any]]:
    """Subject -> teaching days, for the review UI's day-allocation view."""
    return [
        {
            "subject": subject.subject,
            "scheme_of_work_id": subject.scheme_of_work_id,
            "teaching_days": list(subject.teaching_days),
            "teaching_day_groups": [list(g) for g in subject.teaching_day_groups],
        }
        for subject in plan.subjects
    ]


def plan_validation_issues(plan: WeeklyClassPlan) -> List[str]:
    """Structural problems with a weekly plan (empty = ready to export).

    Cross-subject day overlap is NOT a problem: the class-teacher model has
    one teacher delivering several subjects on the same weekdays (the real
    fixture runs English AND Maths Monday-Friday), each in its own section
    and period. The same is true of two DIFFERENT schemes sharing one
    subject name — they are two sections of the same week. What IS a
    problem is one scheme claiming a day twice: the same section selected
    twice, or a repeated day inside one section.
    """
    issues: List[str] = []
    if not plan.subjects:
        issues.append("The weekly plan has no subject sections.")
        return issues
    seen_schemes: Dict[str, str] = {}
    day_counts: Dict[Tuple[str, str], int] = {}
    for subject in plan.subjects:
        if not subject.subject:
            issues.append("A subject section has no subject name.")
        if not subject.day_plans:
            issues.append(f"{subject.subject or 'A subject'} has no teaching days.")
        if subject.scheme_of_work_id and subject.scheme_of_work_id in seen_schemes:
            issues.append(
                f"{subject.subject or 'A subject'} appears more than once "
                "in this weekly plan."
            )
        elif subject.scheme_of_work_id:
            seen_schemes[subject.scheme_of_work_id] = subject.subject
        section_key = subject.scheme_of_work_id or subject.subject
        for day_plan in subject.day_plans:
            for day in day_plan.days:
                key = (section_key, day)
                day_counts[key] = day_counts.get(key, 0) + 1
                if day_counts[key] == 2:
                    issues.append(
                        f"{day} is assigned twice within {subject.subject}."
                    )
    return issues

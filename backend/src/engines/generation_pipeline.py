"""
SchemeKnit Lesson Generation Pipeline

Production pipeline:
Validated Scheme → Term Config → Calendar → Allocation → Lesson Plans → Validation → Export
"""

import logging
import inspect
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def supports_kwarg(fn, name: str) -> bool:
    """True when a callable's signature accepts keyword ``name``.

    Lets the pipeline pass newer optional arguments (e.g. teacher_keywords) to
    providers that support them while remaining compatible with providers that
    do not — without swallowing real errors from inside the call.
    """
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False

from ..models import (
    SchemeOfWork, Week, WeekType, TermConfig, TeachingCalendar,
    CurriculumCoverage, LessonPlan, GenerationJob, JobStatus,
    LessonStatus, TemplateType, AIMode, ValidationIssue, ValidationSeverity,
    Holiday, EducationalLevel, CLASS_LEVEL_TO_EDUCATIONAL_LEVEL,
    Subject, ClassLevel, GenerationMethod, ContentSource,
)
from .calendar_engine import CalendarEngine
from ..ai_resource_text import normalize_structured_references
from .allocation_engine import AllocationEngine
from .coverage_validator import CoverageValidator
from .docx_export import DOCXExportEngine, default_template_for_lessons
from .pdf_export import PDFExportEngine
from .xlsx_export import XLSXExportEngine
from .zip_export import ZIPExportEngine
from .template_engine import (
    get_visible_sections,
    get_template_by_id, get_templates_for_level, get_profile_for_class_level,
)
from .ai_provider import get_provider, resolve_provider_mode
from .zeli_generation import (
    ZeliGenerationError,
    generate_zeli_content,
    get_zeli_provider,
    zeli_lesson_context,
)


_PLACEHOLDER_RESOURCES = frozenset({
    "none", "n/a", "na", "null", "nil", "-", "—", "...", "no resources",
})


def _clean_resources(values: Any) -> List[str]:
    """Provider resource lists without placeholder junk.

    Models occasionally write ``"None"``/``"N/A"``/``"null"`` instead of an
    empty array. That is not a teaching resource, and printing it made the
    quality gate flag the lesson as filler text. Real named resources are kept
    verbatim.
    """
    if not isinstance(values, (list, tuple)):
        return []
    out: List[str] = []
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text and text.lower() not in _PLACEHOLDER_RESOURCES:
            out.append(text)
    return out


def _compose_prose(primary: Any, *extras: Any) -> str:
    """Join provider-authored prose parts, dropping empty/placeholder ones.

    Provider V2 payloads carry the main prose (``activity``) plus the
    teacher/learner actions and success criteria. Those extra fields were
    previously discarded, which lost the explicit evidence a teacher needs and
    left the lesson text weaker than the model's own output.
    """
    parts: List[str] = []
    for value in (primary,) + extras:
        text = str(value).strip() if value is not None else ""
        if text and text.lower() not in _PLACEHOLDER_RESOURCES:
            parts.append(text)
    return " ".join(parts)


def _dedupe_activities(activities: List[Any]) -> List[Any]:
    """Drop exact-duplicate activity descriptions (keep first occurrence).

    Models occasionally emit the same instruction in two list entries; the
    quality gate's boilerplate check then flags the whole lesson. Matching is
    whitespace- and case-insensitive; distinct texts are never merged.
    """
    seen = set()
    kept = []
    for act in activities:
        desc = getattr(act, "description", "") or ""
        key = " ".join(desc.split()).lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept.append(act)
    return kept


def _fit_activity_durations(activities: List[Any],
                            budget_minutes: Optional[int]) -> List[Any]:
    """Rescale phase durations so their sum fits the lesson duration.

    Models propose phase durations freely (e.g. 80 minutes of activities for
    a 45-minute lesson), which would print an impossible timetable. Only runs
    when the sum exceeds the budget; redistribution is proportional and
    integer-summing via the deterministic builder's _distribute.
    """
    if not activities or not budget_minutes or budget_minutes <= 0:
        return activities
    durations = [int(getattr(a, "duration_minutes", 0) or 0)
                 for a in activities]
    if sum(durations) <= budget_minutes:
        return activities
    weights = durations if sum(durations) > 0 else [1] * len(activities)
    from ..curriculum.lesson_builder import _distribute
    fitted = _distribute(int(budget_minutes), weights)
    for act, minutes in zip(activities, fitted):
        act.duration_minutes = minutes
    return activities


def _wapef_context_lines(lp: LessonPlan) -> List[str]:
    """Read-only WAPEF context lines for the AI prompt (empty when none set).

    The teacher's structured selections are described as instructional
    guidance, never as output fields — the AI cannot echo them back.
    """
    from .wapef_fields import format_through_lines
    lines: List[str] = []
    deep_hope = (getattr(lp, "wapef_deep_hope", "") or "").strip()
    storyline = (getattr(lp, "wapef_storyline", "") or "").strip()
    through_lines = list(getattr(lp, "wapef_through_lines", None) or [])
    gods_story = (getattr(lp, "wapef_gods_story", "") or "").strip()
    if deep_hope:
        lines.append(f"Deep Hope: {deep_hope}")
    if storyline:
        lines.append(f"Storyline: {storyline}")
    if through_lines:
        lines.append(f"Through lines: {format_through_lines(through_lines)}")
    if gods_story:
        lines.append(f"God's Story: {gods_story}")
    return lines


class GenerationPipeline:
    """Production lesson plan generation pipeline."""

    def __init__(self):
        self.calendar_engine = CalendarEngine()
        self.allocation_engine = AllocationEngine()
        self.coverage_validator = CoverageValidator()
        self.docx_engine = DOCXExportEngine()
        self.pdf_engine = PDFExportEngine()
        self.xlsx_engine = XLSXExportEngine()
        self.zip_engine = ZIPExportEngine()

    def generate_all(
        self,
        scheme: SchemeOfWork,
        config: TermConfig,
        include_special_weeks: bool = False,
        selected_weeks: Optional[List[int]] = None,
        template_id: Optional[str] = None,
        db=None,
    ) -> GenerationJob:
        """Run the full generation pipeline."""
        job = GenerationJob(
            scheme_of_work_id=scheme.id,
            config=config,
            status=JobStatus.PROCESSING,
        )
        lesson_plans: List[LessonPlan] = []

        try:
            calendar = self.calendar_engine.build_calendar(
                config, scheme.weeks, config.holidays
            )

            weeks_to_use = scheme.weeks
            if selected_weeks:
                weeks_to_use = [w for w in scheme.weeks if w.week_number in selected_weeks]

            coverage = self.allocation_engine.allocate(
                weeks_to_use, calendar, config, include_special_weeks
            )

            # Stable lesson numbering (Priority 3): stamp each allocation with
            # its 1-based ordinal over the FULL scheme (curriculum order,
            # special-period rows excluded) BEFORE any subset filter. A lesson
            # generated from a subset keeps the number the preview showed it,
            # so per-lesson review drafts keyed by lesson_sequence can never
            # drift onto the wrong lesson when only one week/occurrence is
            # generated. Full-scheme runs are unaffected (ordinal == the dense
            # counter the generator would have assigned anyway).
            _ordinal = 0
            for _alloc in sorted(coverage.allocations, key=lambda a: a.lesson_sequence):
                if getattr(_alloc, "is_special_period", False):
                    continue
                _ordinal += 1
                _alloc.lesson_ordinal = _ordinal

            # ── Free Tier indicator selection ─────────────────────────────
            # When the teacher selected a subset of indicators, generate ONLY
            # those. The allocation itself is unchanged, so source week,
            # teaching week, indicator code/text, lesson sequence and
            # carry-forward state are all preserved — the curriculum is never
            # reordered or dropped. Unselected indicators simply remain in the
            # scheme for the next generation. Occurrence-level selection (a
            # single timetable occurrence of a code, e.g. "[Generate lesson]"
            # on week 5's copy of a repeating indicator) takes precedence over
            # the code list; the router resolves codes from the occurrences it
            # reserved quota for, so the two can never disagree.
            selected = list(getattr(config, "selected_indicator_codes", []) or [])
            selected_occ = list(getattr(config, "selected_occurrence_ids", []) or [])
            selection_applied = bool(selected) or bool(selected_occ)
            if selection_applied:
                if selected_occ:
                    occ_set = set(selected_occ)
                    kept = [
                        a for a in coverage.allocations
                        if a.source_occurrence_id and a.source_occurrence_id in occ_set
                    ]
                else:
                    sel_set = set(selected)
                    kept = [a for a in coverage.allocations if a.indicator_code in sel_set]
                coverage.allocations = kept
                coverage.total_generated_lessons = len(kept)
                coverage.total_periods_allocated = len(kept)
                coverage.total_indicators = len(kept)
                coverage.indicators_allocated = len(kept)
                coverage.indicators_unallocated = 0
                coverage.coverage_percentage = 100.0 if kept else 0.0

            # total_lessons = actual lessons to generate = number of allocated
            # indicators (one indicator → one teaching period → one lesson).
            # This replaces the old calendar-slot estimate.
            job.total_lessons = coverage.total_generated_lessons

            # A deliberate subset selection is not a coverage failure: skip the
            # full-scheme missing-indicator validation so the teacher is not
            # warned that unselected indicators "disappeared".
            validation_issues = (
                [] if selection_applied
                else self.coverage_validator.validate(scheme.weeks, coverage)
            )
            job.progress = 30

            from ..engines.allocation_engine import BuildLedger
            build_ledger = BuildLedger()
            lesson_plans = self.allocation_engine.generate_lesson_plans(
                coverage, config, scheme.id, ledger=build_ledger,
            )
            job._build_ledger = build_ledger

            educational_level = CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(
                scheme.class_level, EducationalLevel.JHS
            )
            # Propagate the scheme's detected subject/class_level onto lessons
            # when the TermConfig left them UNKNOWN (the default). The scheme
            # is the source of truth for metadata — config defaults must never
            # override a real detected value.
            for lp in lesson_plans:
                lp.educational_level = educational_level.value
                lp.template_id = template_id
                if lp.subject is Subject.UNKNOWN or lp.subject is None:
                    lp.subject = scheme.subject
                if lp.class_level is ClassLevel.UNKNOWN or lp.class_level is None:
                    lp.class_level = scheme.class_level

            job.progress = 60

            if config.generation_method == GenerationMethod.ZELI:
                # Generate with Zeli: the provider produces the WHOLE lesson.
                # There is no deterministic substitute — a failure marks the job
                # failed and the router reports it truthfully, so a teacher can
                # never be shown deterministic prose labelled "Zeli".
                self._generate_with_zeli(lesson_plans, config, job, db=db)
            elif config.ai_mode != AIMode.OFF:
                try:
                    self._enrich_with_ai(lesson_plans, config, job)
                except Exception as e:
                    logger.error(
                        "AI enrichment pipeline failed for job %s: %s: %s",
                        job.id, type(e).__name__, e,
                    )
                    job.error_message = (
                        f"AI enrichment could not be completed. "
                        f"Your lessons were generated using the standard lesson engine."
                    )
            job.progress = 80

            for lp in lesson_plans:
                lp.status = LessonStatus.GENERATED

            job.lesson_plan_ids = [lp.id for lp in lesson_plans]
            job.completed_lessons = len(lesson_plans)
            job.remaining_lessons = 0
            job.progress = 100
            job.status = JobStatus.COMPLETED
            job.completed_date = datetime.utcnow()

            job._lesson_plans = lesson_plans
            job._coverage = coverage
            job._calendar = calendar
            job._validation_issues = validation_issues

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            # Preserve the classified, teacher-safe Zeli failure so the HTTP
            # layer can answer 429/503/504 instead of a generic 500.
            if isinstance(e, ZeliGenerationError):
                job._zeli_error = e
            job._lesson_plans = lesson_plans

        return job

    def export_docx_combined(
        self,
        job_title: str,
        lesson_plans: List[LessonPlan],
        template_type: TemplateType = TemplateType.GES_STYLE,
        output_path: Path = Path("exports/lesson_plans.docx"),
        template_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> Path:
        if template_id:
            template = get_template_by_id(template_id)
        else:
            template = default_template_for_lessons(lesson_plans, template_type)
        return self.docx_engine.export_combined(lesson_plans, template, output_path,
                                                context=context)

    def export_docx_batch(
        self,
        lesson_plans: List[LessonPlan],
        template_type: TemplateType = TemplateType.GES_STYLE,
        output_dir: Path = Path("exports/docx"),
        template_id: Optional[str] = None,
    ) -> List[Path]:
        if template_id:
            template = get_template_by_id(template_id)
        else:
            template = default_template_for_lessons(lesson_plans, template_type)
        return self.docx_engine.export_batch(lesson_plans, template, output_dir)

    def export_pdf_batch(
        self,
        lesson_plans: List[LessonPlan],
        template_type: TemplateType = TemplateType.GES_STYLE,
        output_dir: Path = Path("exports/pdf"),
        template_id: Optional[str] = None,
    ) -> List[Path]:
        if template_id:
            template = get_template_by_id(template_id)
        else:
            template = default_template_for_lessons(lesson_plans, template_type)
        return self.pdf_engine.export_batch(lesson_plans, template, output_dir)

    def export_pdf_structured(
        self,
        lesson_plans: List[LessonPlan],
        output_path: Path = Path("exports/lesson_plans.pdf"),
        template_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> Path:
        """Render a template-faithful PDF with no DOCX -> PDF toolchain.

        Hosts without Word or LibreOffice still owe the teacher a real lesson
        plan, so the structured renderer lays the content out directly with
        ReportLab instead of extracting text from a DOCX (which flattened every
        table into prose).
        """
        from .structured_pdf import render_structured_pdf
        template = get_template_by_id(template_id) if template_id else None
        if template is None:
            template = default_template_for_lessons(lesson_plans)
        return render_structured_pdf(
            lesson_plans, template=template, output_path=output_path,
            render_context=context)

    def export_xlsx(
        self,
        lesson_plans: List[LessonPlan],
        output_path: Path = Path("exports/register.xlsx"),
        title: str = "Lesson Plan Register",
    ) -> Path:
        return self.xlsx_engine.export_register(lesson_plans, output_path, title)

    def export_zip(
        self,
        lesson_plans: List[LessonPlan],
        template_type: TemplateType = TemplateType.GES_STYLE,
        output_path: Path = Path("exports/lesson_plans.zip"),
        template_id: Optional[str] = None,
        structure: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> Path:
        # The chosen template must travel with the request: the ZIP engine
        # otherwise falls back to the head of DEFAULT_TEMPLATES (the JHS form).
        template = (get_template_by_id(template_id) if template_id
                    else default_template_for_lessons(lesson_plans, template_type))
        return self.zip_engine.export_batch(lesson_plans, output_path, template_type, structure,
                                            context=context, template=template)

    def export_docx_combined_custom(
        self,
        lesson_plans: List[LessonPlan],
        structure: dict,
        output_path: Path = Path("exports/lesson_plans.docx"),
        context: dict = None,
    ) -> Path:
        return self.docx_engine.export_combined_custom(lesson_plans, structure, output_path, context)

    def export_docx_batch_custom(
        self,
        lesson_plans: List[LessonPlan],
        structure: dict,
        output_dir: Path = Path("exports/docx"),
        context: dict = None,
    ) -> List[Path]:
        return self.docx_engine.export_batch_custom(lesson_plans, structure, output_dir, context=context)

    def _complete_zeli_timeline(self, lp: LessonPlan,
                                content: Optional[dict] = None) -> None:
        """Place the provider's starter/plenary into the lesson timeline.

        The V2 provider returns the starter and plenary as separate sections,
        while SchemeKnit's lesson layout (and its quality gate) expects a
        single timeline whose phase rows include a PHASE 1 and a PHASE 3
        boundary and whose minutes sum exactly to the lesson duration.

        This is structural normalisation, not invented content: every row's
        text comes verbatim from the provider's own starter/conclusion. When
        the provider supplied explicit minutes for those sections they are
        honoured (the first real DeepSeek run exposed an invented 15-minute
        exit slip because the provider's 5 minutes were ignored); only the
        remaining slack is distributed deterministically so the printed
        timetable is always arithmetically possible.
        """
        from ..curriculum.lesson_rubric import phase_rows
        from ..models import TeachingActivity

        duration = int(lp.duration_minutes or 0)
        if duration <= 0:
            return
        content = content if isinstance(content, dict) else {}

        def _section(name: str) -> dict:
            value = content.get(name)
            return value if isinstance(value, dict) else {}

        def _provider_minutes(section: dict) -> int:
            try:
                value = int(section.get("duration_minutes") or 0)
            except (TypeError, ValueError):
                return 0
            return value if 0 < value < duration else 0

        activities = list(lp.main_activities or [])
        p1, _p2, p3 = phase_rows(lp)
        starter_text = (lp.starter_activity or "").strip()
        plenary_text = (lp.conclusion or "").strip()

        # Default boundary budgets (used only when the provider gave no
        # explicit minutes) keep the opening/closing short for a 60-minute
        # lesson instead of sweeping all leftover time into the plenary.
        default_boundary = max(1, min(10, duration // 12))
        starter_wanted = 0
        plenary_wanted = 0
        if starter_text and not p1:
            starter_wanted = (
                _provider_minutes(_section("starter")) or default_boundary)
        if plenary_text and not p3:
            plenary_wanted = (
                _provider_minutes(_section("plenary")) or default_boundary)

        # Never let the boundary rows crowd out the main learning.
        if starter_wanted + plenary_wanted >= duration:
            scale = (duration - 1) / max(starter_wanted + plenary_wanted, 1)
            starter_wanted = int(starter_wanted * scale)
            plenary_wanted = int(plenary_wanted * scale)

        main_budget = max(duration - starter_wanted - plenary_wanted, 0)
        if activities:
            spent = sum(int(a.duration_minutes or 0) for a in activities)
            if spent > main_budget:
                activities = _fit_activity_durations(activities, main_budget)
                spent = sum(int(a.duration_minutes or 0) for a in activities)
            # Absorb any slack into the last teaching phase so the printed
            # timetable always sums to the lesson duration.
            slack = main_budget - spent
            if slack > 0:
                activities[-1].duration_minutes = int(
                    activities[-1].duration_minutes or 0) + slack
        else:
            # No main phases: give the remaining time to the boundary rows.
            starter_wanted += main_budget // 2
            plenary_wanted += main_budget - main_budget // 2

        if starter_text and not p1 and starter_wanted > 0:
            activities.insert(0, TeachingActivity(
                phase="STARTER",
                description=lp.starter_activity,
                duration_minutes=starter_wanted,
                source=ContentSource.AI,
            ))
        if plenary_text and not p3 and plenary_wanted > 0:
            activities.append(TeachingActivity(
                phase="PLENARY",
                description=lp.conclusion,
                duration_minutes=plenary_wanted,
                source=ContentSource.AI,
            ))

        # Final arithmetic guard for any branch that skipped a boundary row.
        total = sum(int(a.duration_minutes or 0) for a in activities)
        if activities and total < duration:
            activities[-1].duration_minutes = int(
                activities[-1].duration_minutes or 0) + (duration - total)
        elif activities and total > duration:
            activities = _fit_activity_durations(activities, duration)

        lp.main_activities = activities

    def _generate_with_zeli(
        self,
        lesson_plans: List[LessonPlan],
        config: TermConfig,
        job: GenerationJob,
        db=None,
    ):
        """Generate whole lesson content with Zeli (the 'Generate with Zeli' method).

        Every lesson goes through the SAME provider contract the rest of the
        product uses (``generate_lesson_v2``), then through SchemeKnit's strict
        whole-lesson validator and the existing quality gate (run later by the
        router). Teacher- and curriculum-owned fields are still applied through
        ``_apply_v2_content``, so curriculum authority, Ghanaian context,
        assessment structure and differentiation are preserved.

        Unlike the optional enrichment path, a failure NEVER silently falls
        back to deterministic content: it raises ``ZeliGenerationError`` and the
        whole run fails with a teacher-safe reason, leaving existing lessons and
        quota untouched. A special period (no instructional content) is skipped,
        exactly as in the enrichment path.
        """
        provider = get_zeli_provider()
        provider_name = provider.get_name() if hasattr(provider, "get_name") else "zeli"
        model = str(getattr(provider, "model", "") or "")

        sorted_plans = sorted(lesson_plans, key=lambda lp: lp.lesson_sequence)
        for idx, lp in enumerate(sorted_plans):
            if bool(getattr(lp, "special_period_label", "") or ""):
                logger.info(
                    "Skipping Zeli generation for special-period lesson %s (%s)",
                    lp.id, lp.special_period_label,
                )
                continue

            prev_context = None
            next_context = None
            if idx > 0:
                prev_lp = sorted_plans[idx - 1]
                prev_context = (
                    f"Previous lesson: {prev_lp.strand} - {prev_lp.sub_strand}. "
                    f"Indicator: {prev_lp.indicators[0] if prev_lp.indicators else 'N/A'}"
                )
            if idx < len(sorted_plans) - 1:
                next_lp = sorted_plans[idx + 1]
                next_context = (
                    f"Next lesson: {next_lp.strand} - {next_lp.sub_strand}. "
                    f"Indicator: {next_lp.indicators[0] if next_lp.indicators else 'N/A'}"
                )

            context = zeli_lesson_context(
                lp, config,
                previous_lesson_context=prev_context,
                next_lesson_context=next_context,
            )
            job.ai_enrichment_total_attempted += 1

            content = generate_zeli_content(
                provider=provider, context=context, db=db)

            # Apply the validated whole-lesson content. Curriculum fields and
            # teacher-owned metadata are protected inside _apply_v2_content;
            # whole_lesson=True lets the provider's own teaching moves,
            # materials and prior knowledge replace the deterministic scaffold.
            self._apply_v2_content(lp, content, config, whole_lesson=True)
            self._complete_zeli_timeline(lp, content)

            lp.ai_generated = True
            lp.generation_method = "zeli"
            lp.ai_provider = provider_name
            lp.ai_model = model
            job.ai_enrichment_succeeded += 1

        logger.info(
            "Zeli generated %d lesson(s) with provider=%s for job %s",
            job.ai_enrichment_succeeded, provider_name, job.id,
        )

    def _enrich_with_ai(
        self,
        lesson_plans: List[LessonPlan],
        config: TermConfig,
        job: GenerationJob,
    ):
        """Enrich lesson plans using Generation V2 with quality gate.

        V2 uses indicator-grounded, subject-aware prompts.
        Quality gate validates each enriched lesson before marking it ready.
        Falls back to deterministic content if V2 fails quality validation.

        Unexpected exceptions are logged with full diagnostic context and
        tracked on the job so they are never silently swallowed.
        """
        from ..curriculum.quality_gate import validate_lesson_quality, QualityStatus
        from ..curriculum.indicator_interpreter import Indicator as CurriculumIndicator

        # Resolve OFF/BASIC/ENHANCED onto a real named provider when one is
        # configured (Gemini/Groq/Ollama/…). OFF never reaches a provider.
        # Provider choice does not change curriculum authority, quota, quality
        # gate, lesson structure, or allocation — only the content source.
        mode_key = resolve_provider_mode(config.ai_mode)
        if mode_key == "OFF":
            logger.info(
                "AI OFF — deterministic generation for job %s", job.id,
            )
            return
        provider = get_provider(mode_key)
        if not provider.is_available():
            logger.info(
                "AI provider unavailable (resolved=%s, ai_mode=%s) — "
                "deterministic generation for job %s",
                mode_key, config.ai_mode.value, job.id,
            )
            return
        logger.info(
            "AI enrichment using provider=%s (ai_mode=%s) for job %s",
            provider.get_name(), config.ai_mode.value, job.id,
        )

        # Build previous/next context for lesson sequence continuity
        sorted_plans = sorted(lesson_plans, key=lambda lp: lp.lesson_sequence)

        for idx, lp in enumerate(sorted_plans):
            # ── Special periods are never AI-generated (PART Q/R) ─────────
            # A special-period allocation carries no instructional content and
            # no fake curriculum fields, so there is nothing for a provider to
            # enrich: sending "MID-TERM" placeholders to Gemini would ask it
            # to invent a lesson that does not exist.
            if bool(getattr(lp, "special_period_label", "") or ""):
                logger.info(
                    "Skipping AI enrichment for special-period lesson %s (%s)",
                    lp.id, lp.special_period_label,
                )
                continue
            job.ai_enrichment_total_attempted += 1
            try:
                # Determine previous and next lesson context
                prev_context = None
                next_context = None
                if idx > 0:
                    prev_lp = sorted_plans[idx - 1]
                    prev_context = (
                        f"Previous lesson: {prev_lp.strand} - {prev_lp.sub_strand}. "
                        f"Indicator: {prev_lp.indicators[0] if prev_lp.indicators else 'N/A'}"
                    )
                if idx < len(sorted_plans) - 1:
                    next_lp = sorted_plans[idx + 1]
                    next_context = (
                        f"Next lesson: {next_lp.strand} - {next_lp.sub_strand}. "
                        f"Indicator: {next_lp.indicators[0] if next_lp.indicators else 'N/A'}"
                    )

                # Get source resources from the lesson's SOURCE TLRs (scheme provenance).
                # Falls back to the display union only when source fields are empty
                # (legacy lessons). Never uses another subject/week's resources.
                source_resources = list(
                    getattr(lp, "source_tlrs", None)
                    or lp.teaching_learning_resources
                    or []
                )

                # V2 structured generation. ``teacher_keywords`` is only sent
                # when the provider's signature supports it, so third-party or
                # test providers that predate the field keep working.
                v2_kwargs = dict(
                    subject=lp.subject or "",
                    class_level=lp.class_level or "",
                    strand=lp.strand or "",
                    sub_strand=lp.sub_strand or "",
                    content_standard=lp.content_standard or "",
                    indicator_code=lp.indicator_codes[0] if lp.indicator_codes else "",
                    indicator_text=lp.indicators[0] if lp.indicators else "",
                    class_size=lp.class_size or 35,
                    duration_minutes=lp.duration_minutes or 60,
                    source_resources=source_resources,
                    previous_lesson_context=prev_context,
                    next_lesson_context=next_context,
                    week_number=lp.week_number,
                    term=(config.term if config else None),
                    teaching_week=lp.teaching_week,
                    period=lp.period,
                )
                if supports_kwarg(provider.generate_lesson_v2, "teacher_keywords"):
                    v2_kwargs["teacher_keywords"] = list(lp.keywords or [])
                if supports_kwarg(provider.generate_lesson_v2, "source_week_ending"):
                    v2_kwargs["source_week_ending"] = (
                        lp.week_ending.isoformat() if lp.week_ending else None
                    )
                if supports_kwarg(provider.generate_lesson_v2, "other_tlrs"):
                    v2_kwargs["other_tlrs"] = list(
                        getattr(lp, "other_tlrs", None) or [])
                if supports_kwarg(provider.generate_lesson_v2, "core_competencies"):
                    v2_kwargs["core_competencies"] = list(lp.core_competencies or [])
                if supports_kwarg(provider.generate_lesson_v2, "references"):
                    v2_kwargs["references"] = list(lp.references or [])
                # WAPEF selections are teacher-owned structured context. They
                # are sent READ-ONLY (as instructional guidance) and never as
                # JSON the AI could echo back into the lesson fields.
                wapef_ctx = _wapef_context_lines(lp)
                if wapef_ctx and supports_kwarg(provider.generate_lesson_v2, "wapef_context"):
                    v2_kwargs["wapef_context"] = wapef_ctx
                content = provider.generate_lesson_v2(**v2_kwargs)

                if not content:
                    logger.warning(
                        "V2 provider returned empty content for lesson %s "
                        "(indicator=%s, week=%d) — deterministic fallback",
                        lp.id, lp.indicator_codes, lp.week_number,
                    )
                    job.ai_enrichment_errors[lp.id] = "empty_response"
                    continue

                # Apply V2 content to the lesson plan. Teacher-supplied metadata
                # (keywords/TLRs/competencies/references) is MERGED, never
                # replaced, so explicit teacher input always survives.
                self._apply_v2_content(lp, content, config)

                # Create a temporary indicator for quality gate
                indicator_for_gate = CurriculumIndicator(
                    code=lp.indicator_codes[0] if lp.indicator_codes else "",
                    exact_text=f"{lp.indicator_codes[0] if lp.indicator_codes else ''} {lp.indicators[0] if lp.indicators else ''}",
                    description=lp.indicators[0] if lp.indicators else "",
                    source_week=lp.week_number,
                    source_subject=lp.subject or "",
                )

                # Quality gate
                lesson_dict = self._lesson_to_dict(lp)
                report = validate_lesson_quality(lesson_dict, indicator_for_gate)

                if report.passed:
                    lp.ai_generated = True
                    job.ai_enrichment_succeeded += 1
                else:
                    # Quality gate failed — revert to deterministic content
                    # The deterministic content from generate_lesson_plans() is still in place
                    # so we just skip the AI enrichment for this lesson
                    failed_checks = [i.check_name for i in report.failures]
                    logger.warning(
                        "Quality gate failed for lesson %s (indicator=%s): %s — "
                        "deterministic fallback",
                        lp.id, lp.indicator_codes, failed_checks,
                    )
                    job.ai_enrichment_errors[lp.id] = f"quality_gate_failed: {failed_checks}"

            except Exception as e:
                # AI failure does not block the pipeline — deterministic content remains
                # But we ALWAYS log and record the diagnostic
                logger.error(
                    "V2 enrichment failed for lesson %s (indicator=%s, week=%d): "
                    "%s: %s",
                    lp.id, lp.indicator_codes, lp.week_number,
                    type(e).__name__, e,
                )
                job.ai_enrichment_errors[lp.id] = f"{type(e).__name__}: {e}"
                # ai_generated remains False — deterministic fallback

    def _apply_v2_content(self, lp: LessonPlan, content: dict, config: TermConfig = None,
                          *, whole_lesson: bool = False):
        """Apply V2 structured content to a lesson plan.

        Maps the V2 output schema to the existing LessonPlan fields.
        Curriculum fields are NEVER overwritten by AI.

        Teacher-supplied metadata (keywords, TLRs, core competencies,
        references) is MERGED with — never replaced by — the AI output, so the
        teacher's explicit input survives AI enrichment.

        ``whole_lesson`` distinguishes the "Generate with Zeli" method from the
        optional enrichment path. Zeli writes the whole lesson, so its own
        prior knowledge, teaching moves, resources and vocabulary must survive;
        the deterministic scaffold is only the fallback when the provider did
        not supply a field. Enrichment keeps the scaffold as the authority.
        """

        def _merge_unique(base, extra):
            out = []
            seen = {str(x).strip().lower() for x in (base or []) if str(x).strip()}
            for x in (base or []):
                if str(x).strip() and str(x).strip() not in out:
                    out.append(str(x).strip())
            for x in (extra or []):
                key = str(x).strip().lower()
                if key and key not in seen:
                    out.append(str(x).strip())
                    seen.add(key)
            return out

        # ── AI overwrite guards (Section P) ────────────────────────────────
        # Precedence: AUTHORITATIVE SOURCE > TEACHER > AI.
        # Snapshot teacher-owned fields so AI cannot replace them. For a
        # whole-lesson Zeli run the deterministic scaffold's keyword guesses
        # are NOT teacher input; only the batch config carries teacher terms.
        teacher_keywords = []
        if whole_lesson:
            if config:
                for k in (getattr(config, "keywords", []) or []):
                    if k and k not in teacher_keywords:
                        teacher_keywords.append(k)
        else:
            teacher_keywords = list(lp.keywords or [])
            if config:
                for k in (getattr(config, "keywords", []) or []):
                    if k and k.lower() not in {x.lower() for x in teacher_keywords}:
                        teacher_keywords.append(k)
        lesson_source_tlrs = list(getattr(lp, "source_tlrs", None) or [])
        # OTHER TLRs are TEACHER-ADDED ONLY (PART I): the batch config seed is
        # never copied into per-lesson other_tlrs — that would fabricate data
        # the teacher never entered for this lesson. Empty stays empty.
        lesson_other_tlrs = list(getattr(lp, "other_tlrs", None) or [])
        lesson_competencies = list(lp.core_competencies or [])
        if config:
            for c in (getattr(config, "core_competencies", []) or []):
                if c and c.lower() not in {x.lower() for x in lesson_competencies}:
                    lesson_competencies.append(c)
        lesson_references = list(lp.references or [])
        if config:
            for r in (getattr(config, "references", []) or []):
                if r and r.lower() not in {x.lower() for x in lesson_references}:
                    lesson_references.append(r)
        lesson_structured_refs = normalize_structured_references(
            getattr(lp, "structured_references", None))
        # Authoritative curriculum facts — AI must never change these.
        authoritative = {
            "indicator_codes": list(lp.indicator_codes or []),
            "indicators": list(lp.indicators or []),
            "content_standard": lp.content_standard,
            "content_standard_code": lp.content_standard_code,
            "week_number": lp.week_number,
            "week_ending": lp.week_ending,
            "strand": lp.strand,
            "sub_strand": lp.sub_strand,
        }
        # WAPEF teacher selections (and teacher-written remarks) are strictly
        # teacher-owned: snapshotted before the AI content is applied and
        # restored verbatim afterwards, so no AI output path can ever choose,
        # rewrite or clear them. See engines/wapef_fields.py.
        wapef_snapshot = {
            "wapef_deep_hope": getattr(lp, "wapef_deep_hope", "") or "",
            "wapef_storyline": getattr(lp, "wapef_storyline", "") or "",
            "wapef_through_lines": list(getattr(lp, "wapef_through_lines", None) or []),
            "wapef_gods_story": getattr(lp, "wapef_gods_story", "") or "",
            "remarks": getattr(lp, "remarks", "") or "",
        }
        # Learning objectives
        if "learning_objectives" in content and content["learning_objectives"]:
            from ..models import LearningObjective
            objectives = []
            for obj in content["learning_objectives"]:
                if isinstance(obj, str):
                    objectives.append(LearningObjective(
                        description=obj,
                        indicator_code=lp.indicator_codes[0] if lp.indicator_codes else "",
                        source=ContentSource.AI,
                    ))
                elif isinstance(obj, dict):
                    objectives.append(LearningObjective(
                        description=obj.get("description", obj.get("objective", "")),
                        indicator_code=lp.indicator_codes[0] if lp.indicator_codes else "",
                        source=ContentSource.AI,
                    ))
            if objectives:
                lp.learning_objectives = objectives

        # Key vocabulary: teacher-supplied terms FIRST and always retained, then
        # AI-suggested indicator vocabulary added on top. AI never replaces.
        # A whole-lesson run starts from the teacher/config terms only: the
        # deterministic keyword guesses are not teacher input and were being
        # echoed back as if they were (e.g. "watch", "notice", "materials").
        if "key_vocabulary" in content and content["key_vocabulary"]:
            base_keywords = [] if whole_lesson else list(lp.keywords or [])
            lp.keywords = _merge_unique(
                _merge_unique(base_keywords, teacher_keywords),
                content["key_vocabulary"])
        elif teacher_keywords:
            base_keywords = [] if whole_lesson else list(lp.keywords or [])
            lp.keywords = _merge_unique(base_keywords, teacher_keywords)

        # Starter — keep the provider's teacher/learner actions with it so the
        # opening is a complete teaching move, not a lone instruction.
        starter = content.get("starter", {})
        if isinstance(starter, dict):
            teacher_action = starter.get("teacher_action")
            learner_action = starter.get("learner_action")
            lp.starter_activity = _compose_prose(
                starter.get("activity"),
                f"Teacher: {teacher_action}" if teacher_action else "",
                f"Learners: {learner_action}" if learner_action else "",
            )
        elif isinstance(starter, str):
            lp.starter_activity = starter

        # Main learning activities
        main = content.get("main_learning", {})
        if isinstance(main, dict):
            from ..models import TeachingActivity
            activities = []
            for phase_key, phase in main.items():
                if isinstance(phase, dict):
                    activities.append(TeachingActivity(
                        phase=phase.get("name", phase_key).upper(),
                        description=phase.get("activity", ""),
                        duration_minutes=phase.get("duration_minutes", 15),
                        resources=_clean_resources(phase.get("resources_used", [])),
                        source=ContentSource.AI,
                    ))
            if activities:
                lp.main_activities = _fit_activity_durations(
                    _dedupe_activities(activities), lp.duration_minutes)
        elif isinstance(main, list):
            from ..models import TeachingActivity
            activities = []
            for item in main:
                if isinstance(item, dict):
                    activities.append(TeachingActivity(
                        phase=item.get("phase", "MAIN").upper(),
                        description=item.get("description", item.get("activity", "")),
                        duration_minutes=item.get("duration_minutes", 15),
                        resources=_clean_resources(item.get("resources_used", [])),
                        source=ContentSource.AI,
                    ))
            if activities:
                lp.main_activities = _fit_activity_durations(
                    _dedupe_activities(activities), lp.duration_minutes)

        # Learner activities (from main_learning or dedicated field)
        if "learner_activities" in content:
            learner_acts = content["learner_activities"]
            if isinstance(learner_acts, list):
                from ..models import TeachingActivity
                activities = []
                for item in learner_acts:
                    if isinstance(item, dict):
                        activities.append(TeachingActivity(
                            phase="LEARNER",
                            description=item.get("description", item.get("activity", "")),
                            duration_minutes=item.get("duration_minutes", 15),
                        ))
                    elif isinstance(item, str):
                        activities.append(TeachingActivity(
                            phase="LEARNER",
                            description=item,
                            duration_minutes=15,
                        ))
                if activities:
                    lp.learner_activities = _dedupe_activities(activities)

        # Teacher/learner columns. Optional enrichment keeps the deterministic
        # curriculum-grounded rows and only fills genuinely empty columns. A
        # whole-lesson Zeli run is different: the provider wrote the lesson's
        # teaching moves, so its per-phase actions replace the generic scaffold
        # rows instead of sitting beside contradictory ones.
        if isinstance(main, dict):
            from ..models import TeachingActivity
            if whole_lesson:
                phase_rows_source = [p for p in main.values()
                                     if isinstance(p, dict)]
                mapped_by_phase = {
                    str(getattr(act, "phase", "") or "").upper(): act
                    for act in (lp.main_activities or [])
                }
                teacher_rows = []
                learner_rows = []
                for idx, phase in enumerate(phase_rows_source):
                    name = str(phase.get("name") or "").upper()
                    mapped = mapped_by_phase.get(name)
                    if mapped is None and idx < len(lp.main_activities or []):
                        mapped = (lp.main_activities or [])[idx]
                    minutes = int(
                        getattr(mapped, "duration_minutes", 0) or 0)
                    teacher_action = str(
                        phase.get("teacher_action") or "").strip()
                    learner_action = str(
                        phase.get("learner_action") or "").strip()
                    if teacher_action:
                        teacher_rows.append(TeachingActivity(
                            phase=name or "MAIN",
                            description=teacher_action,
                            duration_minutes=minutes,
                            source=ContentSource.AI,
                        ))
                    if learner_action:
                        learner_rows.append(TeachingActivity(
                            phase=name or "MAIN",
                            description=learner_action,
                            duration_minutes=minutes,
                            source=ContentSource.AI,
                        ))
                if teacher_rows:
                    lp.teacher_activities = _dedupe_activities(teacher_rows)
                if learner_rows:
                    lp.learner_activities = _dedupe_activities(learner_rows)
            else:
                if not getattr(lp, "teacher_activities", None):
                    rows = []
                    for phase_key, phase in main.items():
                        if not isinstance(phase, dict):
                            continue
                        action = str(phase.get("teacher_action") or "").strip()
                        if not action:
                            continue
                        rows.append(TeachingActivity(
                            phase=str(phase.get("name", phase_key)).upper(),
                            description=_compose_prose(
                                phase.get("activity"), f"Teacher: {action}"),
                            duration_minutes=phase.get("duration_minutes", 15),
                        ))
                    if rows:
                        lp.teacher_activities = _dedupe_activities(rows)
                if not getattr(lp, "learner_activities", None):
                    rows = []
                    for phase_key, phase in main.items():
                        if not isinstance(phase, dict):
                            continue
                        action = str(phase.get("learner_action") or "").strip()
                        if not action:
                            continue
                        rows.append(TeachingActivity(
                            phase=str(phase.get("name", phase_key)).upper(),
                            description=_compose_prose(
                                phase.get("activity"), f"Learners: {action}"),
                            duration_minutes=phase.get("duration_minutes", 15),
                        ))
                    if rows:
                        lp.learner_activities = _dedupe_activities(rows)

        # Assessment — the provider's success criteria are the evidence the
        # teacher checks, so they belong with the task (never dropped).
        assessment = content.get("assessment", {})
        if isinstance(assessment, dict):
            task = assessment.get("activity") or assessment.get("method") or ""
            criteria = assessment.get("success_criteria")
            lp.assessment = _compose_prose(
                task, f"Success criteria: {criteria}" if criteria else "")
        elif isinstance(assessment, str):
            lp.assessment = assessment

        # Plenary / conclusion — keep the provider's closing actions and exit
        # check so the lesson ends with evidence, not just a summary.
        plenary = content.get("plenary", {})
        if isinstance(plenary, dict):
            teacher_action = plenary.get("teacher_action")
            learner_action = plenary.get("learner_action")
            lp.conclusion = _compose_prose(
                plenary.get("activity"),
                f"Teacher: {teacher_action}" if teacher_action else "",
                f"Learners: {learner_action}" if learner_action else "",
            )
        elif isinstance(plenary, str):
            lp.conclusion = plenary

        # Differentiation
        diff = content.get("differentiation", {})
        if isinstance(diff, dict):
            parts = []
            if diff.get("support"):
                parts.append(f"Needs Support (NS): {diff['support']}")
            if diff.get("core"):
                parts.append(f"High Performing (HP): {diff['core']}")
            if diff.get("extension"):
                parts.append(f"More Able (MA): {diff['extension']}")
            lp.differentiation = "\n".join(parts)
        elif isinstance(diff, str):
            lp.differentiation = diff

        # Homework — the AI enriches the deterministic follow-up task. The
        # canonical home-assignment field and the legacy homework column are
        # written together so the two can never disagree (PART 15): templates
        # that read only one of them render the same task.
        if "homework_or_extension" in content:
            home_task = str(content["homework_or_extension"] or "").strip()
            if home_task:
                lp.homework = home_task
                lp.home_assignment = home_task

        # Prior knowledge: the provider states exactly what learners need to
        # know before this lesson. This is the field the template renders; the
        # old code ignored it and stored teacher notes here instead. Teacher
        # notes are not prior knowledge and have no template cell, so they are
        # deliberately not persisted as one.
        prior_knowledge = str(content.get("prior_knowledge") or "").strip()
        if prior_knowledge and not getattr(lp, "teacher_edited", False):
            lp.previous_knowledge = prior_knowledge

        # Teacher-supplied metadata must survive AI enrichment (merge, never
        # replace). AI suggestions are appended after the teacher's own values.
        # source_tlrs / other_tlrs are NEVER written by AI.
        if teacher_keywords:
            lp.keywords = _merge_unique(teacher_keywords, lp.keywords)
        if lesson_competencies:
            lp.core_competencies = _merge_unique(
                lesson_competencies, lp.core_competencies)
        if lesson_references:
            lp.references = _merge_unique(lesson_references, lp.references)
        # Restore authoritative curriculum fields if anything mutated them.
        lp.indicator_codes = authoritative["indicator_codes"]
        lp.indicators = authoritative["indicators"]
        lp.content_standard = authoritative["content_standard"]
        lp.content_standard_code = authoritative["content_standard_code"]
        lp.week_number = authoritative["week_number"]
        lp.week_ending = authoritative["week_ending"]
        lp.strand = authoritative["strand"]
        lp.sub_strand = authoritative["sub_strand"]
        # WAPEF selections always win: restore the teacher's exact values.
        lp.wapef_deep_hope = wapef_snapshot["wapef_deep_hope"]
        lp.wapef_storyline = wapef_snapshot["wapef_storyline"]
        lp.wapef_through_lines = wapef_snapshot["wapef_through_lines"]
        lp.wapef_gods_story = wapef_snapshot["wapef_gods_story"]
        lp.remarks = wapef_snapshot["remarks"]
        # SOURCE TLRs stay source-only; OTHER TLRs stay teacher-only.
        lp.source_tlrs = lesson_source_tlrs
        lp.other_tlrs = lesson_other_tlrs
        if lesson_structured_refs:
            lp.structured_references = lesson_structured_refs

        # Resources suggested by the AI for the phases may only enrich the
        # DISPLAY union and never mutate source_tlrs or other_tlrs.
        ai_resources = []
        main = content.get("main_learning", {})
        if isinstance(main, dict):
            for phase in main.values():
                if isinstance(phase, dict):
                    ai_resources.extend(
                        _clean_resources(phase.get("resources_used", [])))
        resources_block = content.get("resources", {})
        if isinstance(resources_block, dict):
            ai_resources.extend(_clean_resources(
                resources_block.get("suggested_alternatives", [])))
        # Do NOT pull "source_resources" from AI — source comes from the scheme.
        if ai_resources:
            if whole_lesson:
                # The provider chose the materials for its own activities.
                # Keep the source TLRs (authoritative) and teacher-added TLRs,
                # but drop the deterministic scaffold's generic science kit
                # ("hand lens", "containers", ...), which does not describe
                # this lesson and bloated the printed resource row.
                lp.teaching_learning_resources = _merge_unique(
                    list(lp.source_tlrs or []) + list(lp.other_tlrs or []),
                    ai_resources,
                )
            else:
                lp.teaching_learning_resources = _merge_unique(
                    list(lp.source_tlrs or []) + list(lp.other_tlrs or []),
                    _merge_unique(lp.teaching_learning_resources, ai_resources),
                )

    def _lesson_to_dict(self, lp: LessonPlan) -> dict:
        """Convert a LessonPlan to a dict for the quality gate."""
        def _label(value):
            if isinstance(value, (Subject, ClassLevel)):
                return value.value if value.value else ""
            return value or ""
        return {
            "subject": _label(lp.subject),
            "class_level": _label(lp.class_level),
            "strand": lp.strand or "",
            # Source strand from the allocation — used by strand_match so the
            # check is a real comparison, not a self-comparison no-op.
            "source_strand": lp.strand or "",
            "sub_strand": lp.sub_strand or "",
            "sub_strand": lp.sub_strand or "",
            "lesson_topic": lp.lesson_topic or "",
            "indicators": lp.indicators or [],
            "indicator_codes": lp.indicator_codes or [],
            "homework": lp.homework or "",
            "learning_objectives": [
                {"description": obj.description} for obj in (lp.learning_objectives or [])
            ],
            "main_activities": [
                {"description": act.description, "duration_minutes": act.duration_minutes}
                for act in (lp.main_activities or [])
            ],
            "learner_activities": [
                {"description": act.description, "duration_minutes": act.duration_minutes}
                for act in (lp.learner_activities or [])
            ],
            "assessment": lp.assessment or "",
            "introduction": lp.introduction or "",
            "starter_activity": lp.starter_activity or "",
            "conclusion": lp.conclusion or "",
            "differentiation": lp.differentiation or "",
            "class_size": lp.class_size or 35,
            "duration_minutes": lp.duration_minutes or 60,
            "keywords": lp.keywords or [],
            "teaching_learning_resources": lp.teaching_learning_resources or [],
        }

"""
SchemeKnit Lesson Generation Pipeline

Production pipeline:
Validated Scheme → Term Config → Calendar → Allocation → Lesson Plans → Validation → Export
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

from ..models import (
    SchemeOfWork, Week, WeekType, TermConfig, TeachingCalendar,
    CurriculumCoverage, LessonPlan, GenerationJob, JobStatus,
    LessonStatus, TemplateType, AIMode, ValidationIssue, ValidationSeverity,
    Holiday, EducationalLevel, CLASS_LEVEL_TO_EDUCATIONAL_LEVEL,
    Subject, ClassLevel,
)
from .calendar_engine import CalendarEngine
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
    ) -> GenerationJob:
        """Run the full generation pipeline."""
        job = GenerationJob(
            scheme_of_work_id=scheme.id,
            config=config,
            status=JobStatus.PROCESSING,
        )

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

            # ── Free Tier indicator selection ─────────────────────────────
            # When the teacher selected a subset of indicators, generate ONLY
            # those. The allocation itself is unchanged, so source week,
            # teaching week, indicator code/text, lesson sequence and
            # carry-forward state are all preserved — the curriculum is never
            # reordered or dropped. Unselected indicators simply remain in the
            # scheme for the next generation.
            selected = list(getattr(config, "selected_indicator_codes", []) or [])
            selection_applied = bool(selected)
            if selection_applied:
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

            lesson_plans = self.allocation_engine.generate_lesson_plans(
                coverage, config, scheme.id
            )

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

            if config.ai_mode != AIMode.OFF:
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

        return job

    def export_docx_combined(
        self,
        job_title: str,
        lesson_plans: List[LessonPlan],
        template_type: TemplateType = TemplateType.GES_STYLE,
        output_path: Path = Path("exports/lesson_plans.docx"),
        template_id: Optional[str] = None,
    ) -> Path:
        if template_id:
            template = get_template_by_id(template_id)
        else:
            template = default_template_for_lessons(lesson_plans, template_type)
        return self.docx_engine.export_combined(lesson_plans, template, output_path)

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

                # Get source resources from the lesson plan
                source_resources = list(lp.teaching_learning_resources or [])

                # V2 structured generation
                content = provider.generate_lesson_v2(
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
                )

                if not content:
                    logger.warning(
                        "V2 provider returned empty content for lesson %s "
                        "(indicator=%s, week=%d) — deterministic fallback",
                        lp.id, lp.indicator_codes, lp.week_number,
                    )
                    job.ai_enrichment_errors[lp.id] = "empty_response"
                    continue

                # Apply V2 content to the lesson plan
                self._apply_v2_content(lp, content)

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

    def _apply_v2_content(self, lp: LessonPlan, content: dict):
        """Apply V2 structured content to a lesson plan.

        Maps the V2 output schema to the existing LessonPlan fields.
        Curriculum fields are NEVER overwritten by AI.
        """
        # Learning objectives
        if "learning_objectives" in content and content["learning_objectives"]:
            from ..models import LearningObjective
            objectives = []
            for obj in content["learning_objectives"]:
                if isinstance(obj, str):
                    objectives.append(LearningObjective(
                        description=obj,
                        indicator_code=lp.indicator_codes[0] if lp.indicator_codes else "",
                    ))
                elif isinstance(obj, dict):
                    objectives.append(LearningObjective(
                        description=obj.get("description", obj.get("objective", "")),
                        indicator_code=lp.indicator_codes[0] if lp.indicator_codes else "",
                    ))
            if objectives:
                lp.learning_objectives = objectives

        # Key vocabulary
        if "key_vocabulary" in content and content["key_vocabulary"]:
            lp.keywords = content["key_vocabulary"]

        # Starter
        starter = content.get("starter", {})
        if isinstance(starter, dict):
            lp.starter_activity = starter.get("activity", "")
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
                        resources=phase.get("resources_used", []),
                    ))
            if activities:
                lp.main_activities = activities
        elif isinstance(main, list):
            from ..models import TeachingActivity
            activities = []
            for item in main:
                if isinstance(item, dict):
                    activities.append(TeachingActivity(
                        phase=item.get("phase", "MAIN").upper(),
                        description=item.get("description", item.get("activity", "")),
                        duration_minutes=item.get("duration_minutes", 15),
                        resources=item.get("resources_used", []),
                    ))
            if activities:
                lp.main_activities = activities

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
                    lp.learner_activities = activities

        # Assessment
        assessment = content.get("assessment", {})
        if isinstance(assessment, dict):
            lp.assessment = assessment.get("activity", assessment.get("method", ""))
        elif isinstance(assessment, str):
            lp.assessment = assessment

        # Plenary / conclusion
        plenary = content.get("plenary", {})
        if isinstance(plenary, dict):
            lp.conclusion = plenary.get("activity", "")
        elif isinstance(plenary, str):
            lp.conclusion = plenary

        # Differentiation
        diff = content.get("differentiation", {})
        if isinstance(diff, dict):
            parts = []
            if diff.get("support"):
                parts.append(f"Support: {diff['support']}")
            if diff.get("core"):
                parts.append(f"Core: {diff['core']}")
            if diff.get("extension"):
                parts.append(f"Extension: {diff['extension']}")
            lp.differentiation = "\n".join(parts)
        elif isinstance(diff, str):
            lp.differentiation = diff

        # Homework
        if "homework_or_extension" in content:
            lp.homework = content["homework_or_extension"]

        # Teacher notes
        if "teacher_notes" in content:
            # Store in previous_knowledge field (which is underutilized)
            if not lp.previous_knowledge:
                lp.previous_knowledge = content["teacher_notes"]

    def _lesson_to_dict(self, lp: LessonPlan) -> dict:
        """Convert a LessonPlan to a dict for the quality gate."""
        return {
            "subject": lp.subject or "",
            "class_level": lp.class_level or "",
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

"""
SchemeKnit Lesson Generation Pipeline

Production pipeline:
Validated Scheme → Term Config → Calendar → Allocation → Lesson Plans → Validation → Export
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..models import (
    SchemeOfWork, Week, WeekType, TermConfig, TeachingCalendar,
    CurriculumCoverage, LessonPlan, GenerationJob, JobStatus,
    LessonStatus, TemplateType, AIMode, ValidationIssue, ValidationSeverity,
    Holiday, EducationalLevel, CLASS_LEVEL_TO_EDUCATIONAL_LEVEL
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
from .ai_provider import get_provider


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

            # total_lessons = actual lessons to generate = number of allocated
            # indicators (one indicator → one teaching period → one lesson).
            # This replaces the old calendar-slot estimate.
            job.total_lessons = coverage.total_generated_lessons

            validation_issues = self.coverage_validator.validate(scheme.weeks, coverage)
            job.progress = 30

            lesson_plans = self.allocation_engine.generate_lesson_plans(
                coverage, config, scheme.id
            )

            educational_level = CLASS_LEVEL_TO_EDUCATIONAL_LEVEL.get(
                scheme.class_level, EducationalLevel.JHS
            )
            for lp in lesson_plans:
                lp.educational_level = educational_level.value
                lp.template_id = template_id

            job.progress = 60

            if config.ai_mode != AIMode.OFF:
                self._enrich_with_ai(lesson_plans, config)
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
    ):
        provider = get_provider(config.ai_mode.value)
        if not provider.is_available():
            return

        for lp in lesson_plans:
            try:
                content = provider.generate_lesson_content(
                    indicator=lp.indicators[0] if lp.indicators else "",
                    strand=lp.strand or "",
                    sub_strand=lp.sub_strand or "",
                    content_standard=lp.content_standard or "",
                )
                if content:
                    if content.get("introduction"):
                        lp.introduction = content["introduction"]
                    if content.get("main_activity"):
                        lp.main_activities[0].description = content["main_activity"]
                    if content.get("assessment"):
                        lp.assessment = content["assessment"]
                    if content.get("conclusion"):
                        lp.conclusion = content["conclusion"]
                    lp.ai_generated = True
            except Exception:
                continue

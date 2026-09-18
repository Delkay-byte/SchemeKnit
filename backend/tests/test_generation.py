"""
SchemeKnit Generation Pipeline Tests

Tests for the complete lesson plan generation pipeline.
"""

import pytest
from datetime import date, timedelta
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    SchemeOfWork, Week, WeekType, TermConfig, Subject, ClassLevel,
    Holiday, AIMode, TemplateType, LessonPlan
)
from src.engines.calendar_engine import CalendarEngine
from src.engines.allocation_engine import AllocationEngine
from src.engines.coverage_validator import CoverageValidator
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.docx_export import DOCXExportEngine
from src.engines.xlsx_export import XLSXExportEngine
from src.engines.zip_export import ZIPExportEngine
from src.engines.template_engine import get_template_by_type, get_visible_sections, DEFAULT_TEMPLATES
from src.engines.ai_provider import get_provider, MockProvider


@pytest.fixture
def sample_weeks():
    return [
        Week(
            id=f"week_{i}",
            week_number=i,
            week_type=WeekType.INSTRUCTION,
            start_date=date(2026, 9, 11) + timedelta(weeks=i-1),
            end_date=date(2026, 9, 17) + timedelta(weeks=i-1),
            strand="Number" if i % 2 == 0 else "Algebra",
            sub_strand=f"Sub-topic {i}",
            content_standards=[f"Standard {i}"],
            indicators=[f"Indicator {i}.1", f"Indicator {i}.2"],
            resources=["Charts", "Ruler"],
            scheme_of_work_id="test_scheme",
        )
        for i in range(1, 13)
    ]


@pytest.fixture
def term_config():
    return TermConfig(
        scheme_of_work_id="test_scheme",
        term_start_date="2026-09-11",
        term_end_date="2026-12-18",
        lessons_per_week=3,
        lesson_duration_minutes=60,
        class_size=11,
        teaching_days=[0, 2, 4],
        holidays=[],
        ai_mode=AIMode.OFF,
        template_type=TemplateType.GES_STYLE,
        include_special_weeks=False,
        subject=Subject.MATHEMATICS,
        class_level=ClassLevel.BASIC_9,
        school_name="Test School",
        teacher_name="Test Teacher",
    )


@pytest.fixture
def sample_scheme(sample_weeks):
    from datetime import datetime
    return SchemeOfWork(
        id="test_scheme",
        filename="test_scheme.docx",
        upload_date=datetime.now(),
        subject=Subject.MATHEMATICS,
        class_level=ClassLevel.BASIC_9,
        term="1",
        academic_year="2026/2027",
        weeks=sample_weeks,
        status="uploaded",
    )


class TestCalendarEngine:
    def test_build_calendar(self, term_config, sample_weeks):
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, [])
        
        assert calendar is not None
        assert calendar.total_lessons > 0
        assert len(calendar.teaching_days) > 0

    def test_excludes_holidays(self, term_config, sample_weeks):
        holidays = [
            Holiday(id="h1", name="Independence Day", date="2026-09-21", is_recurring=False)
        ]
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, holidays)
        
        teaching_dates = [d.date for d in calendar.days if d.is_teaching_day]
        assert date(2026, 9, 21) not in teaching_dates


class TestAllocationEngine:
    def test_allocate(self, sample_weeks, term_config):
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, [])
        
        alloc_engine = AllocationEngine()
        coverage = alloc_engine.allocate(sample_weeks, calendar, term_config, False)
        
        assert coverage is not None
        assert coverage.total_indicators > 0
        assert coverage.indicators_allocated > 0

    def test_generate_lesson_plans(self, sample_weeks, term_config):
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, [])
        
        alloc_engine = AllocationEngine()
        coverage = alloc_engine.allocate(sample_weeks, calendar, term_config, False)
        
        plans = alloc_engine.generate_lesson_plans(coverage, term_config, "test_scheme")
        
        assert len(plans) > 0
        assert all(isinstance(lp, LessonPlan) for lp in plans)
        assert all(lp.subject == Subject.MATHEMATICS for lp in plans)


class TestCoverageValidator:
    def test_validate_complete(self, sample_weeks, term_config):
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, [])
        alloc_engine = AllocationEngine()
        coverage = alloc_engine.allocate(sample_weeks, calendar, term_config, False)
        
        validator = CoverageValidator()
        issues = validator.validate(sample_weeks, coverage)
        
        assert isinstance(issues, list)

    def test_generate_report(self, sample_weeks, term_config):
        engine = CalendarEngine()
        calendar = engine.build_calendar(term_config, sample_weeks, [])
        alloc_engine = AllocationEngine()
        coverage = alloc_engine.allocate(sample_weeks, calendar, term_config, False)
        
        validator = CoverageValidator()
        report = validator.generate_report(sample_weeks, coverage)
        
        assert "total_instructional_weeks" in report
        assert "coverage_percentage" in report


class TestGenerationPipeline:
    def test_generate_all(self, sample_scheme, term_config):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        assert job is not None
        assert job.status.value == "completed"
        assert job.total_lessons > 0
        assert hasattr(job, '_lesson_plans')
        assert len(job._lesson_plans) > 0

    def test_export_docx(self, sample_scheme, term_config, tmp_path):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        plans = job._lesson_plans
        files = pipeline.export_docx_batch(plans, output_dir=tmp_path / "docx")
        
        assert len(files) > 0
        assert all(f.exists() for f in files)
        assert all(f.suffix == '.docx' for f in files)

    def test_export_xlsx(self, sample_scheme, term_config, tmp_path):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        plans = job._lesson_plans
        output = pipeline.export_xlsx(plans, tmp_path / "register.xlsx")
        
        assert output.exists()
        assert output.suffix == '.xlsx'


class TestTemplateEngine:
    def test_getJHS_template(self):
        from src.engines.template_engine import get_templates_for_level
        from src.models import EducationalLevel
        templates = get_templates_for_level(EducationalLevel.JHS)
        assert len(templates) > 0
        assert templates[0].family.value == "jhs"

    def test_get_visible_sections(self):
        template = get_template_by_type(TemplateType.GES_STYLE)
        sections = get_visible_sections(template)
        
        assert len(sections) > 0
        assert any(s.name == "header" for s in sections)

    def test_default_templates_count(self):
        from src.engines.template_engine import DEFAULT_TEMPLATES
        # 5 legacy + approved organizational + the four GES-style forms
        assert len(DEFAULT_TEMPLATES) == 10
        assert any(t.id == "tpl-approved-org-headteacher" for t in DEFAULT_TEMPLATES)
        # Official flag is evidence-based: all four bundled GES/NaCCA forms are
        # verified against their own source documents, plus the headteacher
        # alias of the verified JHS source.
        assert {t.id for t in DEFAULT_TEMPLATES if t.is_official} == {
            "tpl-official-ges-nacca-jhs",
            "tpl-approved-org-headteacher",
            "tpl-official-ges-nacca-kg",
            "tpl-official-ges-nacca-primary",
            "tpl-official-ges-nacca-shs",
        }


class TestAIProvider:
    def test_mock_provider(self):
        provider = get_provider("OFF")
        assert isinstance(provider, MockProvider)
        assert provider.is_available()

    def test_mock_generate(self):
        provider = MockProvider()
        result = provider.generate_lesson_content(
            indicator="Test indicator",
            strand="Number",
            sub_strand="Basic Operations",
            content_standard="Learners should understand basic operations"
        )
        assert isinstance(result, dict)


class TestExportEngines:
    def test_DOCXExport(self, sample_scheme, term_config, tmp_path):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        engine = DOCXExportEngine()
        plans = job._lesson_plans
        output = engine.export_single(plans[0], output_path=tmp_path / "test.docx")
        
        assert output.exists()

    def test_XLSXExport(self, sample_scheme, term_config, tmp_path):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        engine = XLSXExportEngine()
        plans = job._lesson_plans
        output = engine.export_register(plans, tmp_path / "register.xlsx")
        
        assert output.exists()

    def test_ZIPExport(self, sample_scheme, term_config, tmp_path):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(sample_scheme, term_config)
        
        engine = ZIPExportEngine()
        plans = job._lesson_plans
        output = engine.export_batch(plans, tmp_path / "batch.zip")
        
        assert output.exists()

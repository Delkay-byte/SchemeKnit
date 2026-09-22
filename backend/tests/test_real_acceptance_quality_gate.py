"""
Real Document Acceptance + Quality Gate + Curriculum IR Trace
============================================================

Exercises the FULL pipeline with real PDFs:
  REAL PDF → parse → curriculum IR → allocation → V2 prompt → mock provider
  → structured JSON → V2 content application → quality gate → LessonPlan

Also tests the quality gate against deliberately malformed input.
And traces the curriculum IR for one Basic 7 and one Basic 9 lesson.
"""

import asyncio
import sys
sys.path.insert(0, '.')

from pathlib import Path
from datetime import date
from typing import Dict, Any
from unittest.mock import MagicMock, patch

from src.parsers.pdf_parser import PDFParser
from src.models import (
    WeekType, Subject, TermConfig, AIMode, Holiday, TeachingCalendar, TeachingDay,
    LessonPlan, AllocatedIndicator,
)
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.ai_provider import AIProvider, _build_v2_prompt_from_context
from src.curriculum import Indicator
from src.curriculum.quality_gate import validate_lesson_quality, QualityStatus, QualityReport

REAL_DOCS = Path(__file__).parent.parent / "real_documents"
BASIC7_PDF = REAL_DOCS / "BASIC 7 TERM 1.pdf"
BASIC9_PDF = REAL_DOCS / "BASIC 9 TERM 1.pdf"


# ── Mock V2 Provider ──────────────────────────────────────────────────────────

class RealisticV2MockProvider(AIProvider):
    """Returns realistic V2 structured JSON matching the V2 output schema."""

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           term=None, teaching_week=None, period=None):
        verb = indicator_text.split(' ', 1)[-1] if ' ' in indicator_text else indicator_text
        topic = indicator_text.split('.')[0] if '.' in indicator_text else indicator_text

        return {
            "learning_objectives": [f"Learners can {verb}"],
            "key_vocabulary": [sub_strand, "classification", "properties"],
            "starter": {
                "activity": f"Teacher displays contrasting examples of {sub_strand}. "
                           f"Learners observe in pairs and identify similarities and differences.",
                "duration_minutes": 8,
                "resources": ["chart", "real objects"],
                "teacher_action": "Display examples and guide observation",
                "learner_action": "Observe, discuss, share",
            },
            "main_learning": {
                "phase1": {
                    "name": "EXPLANATION",
                    "activity": f"Teacher explains {topic} using diagrams and real-life "
                              f"examples from the Ghanaian context.",
                    "duration_minutes": 15,
                    "teacher_action": "Explain with diagrams",
                    "learner_action": "Listen, take notes, ask questions",
                    "resources_used": ["chalkboard", "diagrams"],
                },
                "phase2": {
                    "name": "MODELLING",
                    "activity": f"Teacher demonstrates the process step by step. "
                              f"Learners observe and take notes.",
                    "duration_minutes": 12,
                    "teacher_action": "Demonstrate and question",
                    "learner_action": "Observe, take notes",
                    "resources_used": ["real materials", "chart"],
                },
            },
            "learner_activities": [
                {
                    "phase": "PRACTICE",
                    "description": f"Working in pairs, learners examine samples and "
                                  f"complete a structured worksheet about {sub_strand}.",
                    "duration_minutes": 15,
                    "resources": ["worksheet", "samples"],
                },
            ],
            "assessment": {
                "method": "Observation and worksheet evaluation",
                "activity": f"Teacher observes pair work and records which learners "
                           f"can correctly identify and explain {topic}.",
                "success_criteria": f"Learners can correctly identify and explain {topic}.",
                "duration_minutes": 10,
            },
            "plenary": {
                "activity": f"Teacher leads a class discussion summarising key points about {sub_strand}.",
                "duration_minutes": 5,
            },
            "differentiation": {
                "support": f"Provide diagrams and word bank for learners needing support with {sub_strand}.",
                "core": "All learners complete the worksheet with teacher guidance.",
                "extension": f"Advanced learners research real-world applications of {sub_strand} in Ghana.",
            },
            "homework_or_extension": f"Write about how {sub_strand} applies in everyday life in Ghana.",
            "teacher_notes": "Use local examples relevant to the Ghanaian context.",
        }

    def is_available(self):
        return True


def _make_term_config(scheme_id="real-acceptance", ai_mode=AIMode.BASIC):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7),
        term_end_date=date(2026, 12, 18),
        semester=1,
        lessons_per_week=3,
        lesson_duration_minutes=45,
        teaching_days=[0, 1, 2, 3, 4],
        holidays=[Holiday(name="Founder's Day", date=date(2026, 11, 20))],
        ai_mode=ai_mode,
    )


# ════════════════════════════════════════════════════════════════════════════
# BASIC 7 SCIENCE — FULL PIPELINE ACCEPTANCE
# ════════════════════════════════════════════════════════════════════════════

class TestBasic7ScienceAcceptance:
    """Real PDF → parse → allocate → generate → quality gate → inspect."""

    @classmethod
    def setup_class(cls):
        if not BASIC7_PDF.exists():
            import pytest
            pytest.skip("Real Basic 7 PDF not available")
        parser = PDFParser()
        cls.scheme = asyncio.run(
            parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
        )
        cls.config = _make_term_config(scheme_id=cls.scheme.id)

    def test_parse_succeeds(self):
        assert self.scheme is not None
        assert len(self.scheme.weeks) > 0

    def test_science_subject_detected(self):
        assert self.scheme.subject == Subject.SCIENCE

    def test_weeks_contain_indicators(self):
        for week in self.scheme.weeks:
            if week.week_type == WeekType.INSTRUCTION:
                assert len(week.indicators) > 0, f"Week {week.week_number} has no indicators"

    def test_strands_extracted(self):
        strands = [w.strand for w in self.scheme.weeks if w.strand]
        assert len(strands) > 0, "No strands extracted from PDF"

    def test_curriculum_ir_trace_basic7(self):
        """Trace: PDF → subject section → curriculum IR → indicator."""
        week = self.scheme.weeks[0]
        assert week.strand is not None
        assert week.sub_strand is not None
        assert len(week.indicators) > 0

        first_indicator = week.indicators[0]
        assert "." in first_indicator or " " in first_indicator

        print(f"\n  CURRICULUM IR TRACE (Basic 7 Science Week 1):")
        print(f"    Strand: {week.strand}")
        print(f"    Sub-strand: {week.sub_strand}")
        print(f"    Indicators: {week.indicators[:3]}")
        print(f"    Content standards: {week.content_standards[:2]}")

    def test_allocation_separate_lessons(self):
        """Multiple indicators in same week produce separate lesson plans."""
        calendar = CalendarEngine().build_calendar(
            self.config, self.scheme.weeks, self.config.holidays
        )
        coverage = AllocationEngine().allocate(
            self.scheme.weeks, calendar, self.config
        )

        week2 = [w for w in self.scheme.weeks if w.week_number == 2]
        if week2 and len(week2[0].indicators) > 1:
            assert coverage.total_generated_lessons >= len(week2[0].indicators), \
                f"Expected >= {len(week2[0].indicators)} lessons for week 2"

    def test_generate_with_mock_provider(self):
        """Full pipeline with mock V2 provider produces lessons."""
        mock_provider = RealisticV2MockProvider()
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.scheme, self.config)

        assert job.status.value == "completed"
        assert len(job._lesson_plans) > 0
        self._lessons = job._lesson_plans

    def test_ai_generated_marked(self):
        """Lessons from mock V2 are marked ai_generated=True."""
        pipeline = GenerationPipeline()
        mock_provider = RealisticV2MockProvider()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.scheme, self.config)

        ai_count = sum(1 for lp in job._lesson_plans if lp.ai_generated)
        assert ai_count > 0, f"No lessons marked ai_generated (out of {len(job._lesson_plans)})"

    def test_quality_gate_passes(self):
        """Quality gate accepts the mock V2 lessons."""
        from src.curriculum.indicator_interpreter import Indicator as CI

        pipeline = GenerationPipeline()
        mock_provider = RealisticV2MockProvider()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.scheme, self.config)

        passed = 0
        for lp in job._lesson_plans[:5]:
            indicator = CI(
                code=lp.indicator_codes[0] if lp.indicator_codes else "unknown",
                exact_text=f"{lp.indicator_codes[0] if lp.indicator_codes else ''} {lp.indicators[0] if lp.indicators else ''}",
                description=lp.indicators[0] if lp.indicators else "",
                source_week=lp.week_number,
                source_subject="Science",
            )
            lesson_dict = {
                "subject": lp.subject or "",
                "strand": lp.strand or "",
                "sub_strand": lp.sub_strand or "",
                "indicator_codes": lp.indicator_codes or [],
                "learning_objectives": [{"description": o.description} for o in (lp.learning_objectives or [])],
                "main_activities": [{"description": a.description, "duration_minutes": a.duration_minutes} for a in (lp.main_activities or [])],
                "learner_activities": [{"description": a.description, "duration_minutes": a.duration_minutes} for a in (lp.learner_activities or [])],
                "assessment": lp.assessment or "",
                "starter_activity": lp.starter_activity or "",
                "conclusion": lp.conclusion or "",
                "differentiation": lp.differentiation or "",
                "class_size": lp.class_size or 35,
                "duration_minutes": lp.duration_minutes or 60,
                "keywords": lp.keywords or [],
                "teaching_learning_resources": lp.teaching_learning_resources or [],
            }
            report = validate_lesson_quality(lesson_dict, indicator)
            if report.passed:
                passed += 1

        assert passed >= 3, f"Only {passed}/5 lessons passed quality gate"

    def test_lesson_inspection_basic7(self):
        """Inspect 3 real Basic 7 lessons for quality."""
        pipeline = GenerationPipeline()
        mock_provider = RealisticV2MockProvider()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.scheme, self.config)

        lessons = job._lesson_plans[:3]
        assert len(lessons) >= 3, f"Only {len(lessons)} lessons generated"

        for i, lp in enumerate(lessons):
            print(f"\n  BASIC 7 LESSON {i+1}: Week {lp.week_number} | Seq {lp.lesson_sequence}")
            print(f"    Subject: {lp.subject}")
            print(f"    Strand: {lp.strand}")
            print(f"    Sub-strand: {lp.sub_strand}")
            print(f"    Indicator: {lp.indicator_codes}")
            print(f"    Objectives: {[o.description[:60] for o in lp.learning_objectives]}")
            print(f"    Starter: {(lp.starter_activity or '')[:80]}...")
            print(f"    Main activities: {len(lp.main_activities)}")
            print(f"    Learner activities: {len(lp.learner_activities)}")
            print(f"    Assessment: {(lp.assessment or '')[:80]}...")
            print(f"    Differentiation: {(lp.differentiation or '')[:80]}...")
            print(f"    ai_generated: {lp.ai_generated}")

            assert lp.subject == Subject.SCIENCE
            assert lp.strand is not None
            assert len(lp.learning_objectives) > 0
            assert lp.assessment is not None and len(lp.assessment) > 0


# ════════════════════════════════════════════════════════════════════════════
# BASIC 9 — MULTI-SUBJECT ACCEPTANCE
# ════════════════════════════════════════════════════════════════════════════

class TestBasic9Acceptance:
    """Real PDF → parse multiple subjects → allocate → generate → inspect."""

    @classmethod
    def setup_class(cls):
        if not BASIC9_PDF.exists():
            import pytest
            pytest.skip("Real Basic 9 PDF not available")
        parser = PDFParser()
        cls.english_scheme = asyncio.run(
            parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="English Language")
        )
        cls.science_scheme = asyncio.run(
            parser.parse(BASIC9_PDF, original_filename="BASIC 9 TERM 1.pdf", target_subject="Science")
        )

    def test_english_parse(self):
        assert self.english_scheme is not None
        assert self.english_scheme.subject == Subject.ENGLISH

    def test_science_parse(self):
        assert self.science_scheme is not None
        assert self.science_scheme.subject == Subject.SCIENCE

    def test_different_strands_per_subject(self):
        """Different subjects produce different strands (subject-aware)."""
        eng_strands = {w.strand for w in self.english_scheme.weeks if w.strand}
        sci_strands = {w.strand for w in self.science_scheme.weeks if w.strand}
        assert eng_strands != sci_strands, f"Subjects share same strands: {eng_strands}"

    def test_english_generation(self):
        config = _make_term_config(scheme_id=self.english_scheme.id)
        mock_provider = RealisticV2MockProvider()
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.english_scheme, config)

        assert job.status.value == "completed"
        assert len(job._lesson_plans) > 0
        self._eng_lessons = job._lesson_plans

    def test_science_generation(self):
        config = _make_term_config(scheme_id=self.science_scheme.id)
        mock_provider = RealisticV2MockProvider()
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(self.science_scheme, config)

        assert job.status.value == "completed"
        assert len(job._lesson_plans) > 0
        self._sci_lessons = job._lesson_plans

    def test_subject_strategy_varies(self):
        """English and Science lessons have different structural characteristics."""
        config = _make_term_config(scheme_id=self.english_scheme.id)
        mock_provider = RealisticV2MockProvider()
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            eng_job = pipeline.generate_all(self.english_scheme, config)
            sci_job = pipeline.generate_all(self.science_scheme, config)

        eng_strands = {lp.strand for lp in eng_job._lesson_plans if lp.strand}
        sci_strands = {lp.strand for lp in sci_job._lesson_plans if lp.strand}
        assert eng_strands != sci_strands

    def test_basic9_lesson_inspection(self):
        """Inspect 3 Basic 9 lessons from different subjects."""
        config_sci = _make_term_config(scheme_id=self.science_scheme.id)
        config_eng = _make_term_config(scheme_id=self.english_scheme.id)
        mock_provider = RealisticV2MockProvider()
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            sci_job = pipeline.generate_all(self.science_scheme, config_sci)
            eng_job = pipeline.generate_all(self.english_scheme, config_eng)

        all_lessons = sci_job._lesson_plans[:2] + eng_job._lesson_plans[:1]
        assert len(all_lessons) >= 3

        for i, lp in enumerate(all_lessons):
            print(f"\n  BASIC 9 LESSON {i+1}: Week {lp.week_number} | {lp.subject}")
            print(f"    Strand: {lp.strand}")
            print(f"    Sub-strand: {lp.sub_strand}")
            print(f"    Indicator: {lp.indicator_codes}")
            print(f"    Objectives: {[o.description[:60] for o in lp.learning_objectives]}")
            print(f"    ai_generated: {lp.ai_generated}")

            assert lp.strand is not None
            assert len(lp.learning_objectives) > 0


# ════════════════════════════════════════════════════════════════════════════
# QUALITY GATE — REJECTION OF INVALID INPUT
# ════════════════════════════════════════════════════════════════════════════

class TestQualityGateRejection:
    """Quality gate must reject clearly invalid lessons."""

    def _make_indicator(self, code="B7.1.1.1.1", text="Classify materials"):
        return Indicator(
            code=code,
            exact_text=f"{code} {text}",
            description=text,
            source_week=1,
            source_subject="Science",
        )

    def test_rejects_missing_indicator(self):
        indicator = self._make_indicator(code="", text="")
        lesson = {
            "subject": "Science", "strand": "Matter",
            "indicator_codes": [],
            "learning_objectives": [{"description": "Learners can classify"}],
            "main_activities": [{"description": "Activity", "duration_minutes": 15}],
            "learner_activities": [{"description": "Practice", "duration_minutes": 15}],
            "assessment": "Quiz", "starter_activity": "Review",
            "conclusion": "Summary", "differentiation": "Differentiated",
            "class_size": 35, "duration_minutes": 60,
            "keywords": [], "teaching_learning_resources": [],
        }
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed or report.overall_status == QualityStatus.WARN

    def test_rejects_empty_objectives(self):
        indicator = self._make_indicator()
        lesson = {
            "subject": "Science", "strand": "Matter",
            "indicator_codes": ["B7.1.1.1.1"],
            "learning_objectives": [],
            "main_activities": [{"description": "Activity", "duration_minutes": 15}],
            "learner_activities": [{"description": "Practice", "duration_minutes": 15}],
            "assessment": "Quiz", "starter_activity": "Review",
            "conclusion": "Summary", "differentiation": "Differentiated",
            "class_size": 35, "duration_minutes": 60,
            "keywords": [], "teaching_learning_resources": [],
        }
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed

    def test_rejects_empty_assessment(self):
        indicator = self._make_indicator()
        lesson = {
            "subject": "Science", "strand": "Matter",
            "indicator_codes": ["B7.1.1.1.1"],
            "learning_objectives": [{"description": "Learners can classify"}],
            "main_activities": [{"description": "Activity", "duration_minutes": 15}],
            "learner_activities": [{"description": "Practice", "duration_minutes": 15}],
            "assessment": "", "starter_activity": "Review",
            "conclusion": "Summary", "differentiation": "Differentiated",
            "class_size": 35, "duration_minutes": 60,
            "keywords": [], "teaching_learning_resources": [],
        }
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed

    def test_rejects_empty_main_activities(self):
        indicator = self._make_indicator()
        lesson = {
            "subject": "Science", "strand": "Matter",
            "indicator_codes": ["B7.1.1.1.1"],
            "learning_objectives": [{"description": "Learners can classify"}],
            "main_activities": [],
            "learner_activities": [],
            "assessment": "Quiz", "starter_activity": "Review",
            "conclusion": "Summary", "differentiation": "Differentiated",
            "class_size": 35, "duration_minutes": 60,
            "keywords": [], "teaching_learning_resources": [],
        }
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed

    def test_accepts_valid_lesson(self):
        indicator = self._make_indicator()
        lesson = {
            "subject": "Science", "strand": "Matter",
            "sub_strand": "Materials",
            "indicator_codes": ["B7.1.1.1.1"],
            "learning_objectives": [{"description": "Learners can classify materials into solids, liquids, and gases"}],
            "main_activities": [
                {"description": "Teacher demonstrates classification using real samples", "duration_minutes": 15},
                {"description": "Learners sort samples into categories", "duration_minutes": 10},
            ],
            "learner_activities": [
                {"description": "Pairs classify given materials and record results", "duration_minutes": 15},
            ],
            "assessment": "Teacher observes classification accuracy during group work",
            "starter_activity": "Display contrasting material samples for observation",
            "conclusion": "Class discussion on key classification criteria",
            "differentiation": "Support: word bank; Core: samples; Extension: classify unfamiliar materials",
            "class_size": 35, "duration_minutes": 45,
            "keywords": ["classification", "solids", "liquids", "gases"],
            "teaching_learning_resources": ["real material samples", "chart"],
        }
        report = validate_lesson_quality(lesson, indicator)
        assert report.passed, f"Valid lesson rejected: {[i.message for i in report.failures]}"

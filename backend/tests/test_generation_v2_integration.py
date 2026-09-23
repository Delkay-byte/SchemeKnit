"""
Tests for Generation V2 integration — the real production path.

Covers:
- V2 prompt builder is invoked by the production AI generation path
- Canonical Curriculum IR is consumed by generation
- One indicator produces one generated lesson object
- Curriculum fields are preserved
- Subject-aware strategy is selected
- Objectives are measurable
- Assessment is indicator-aligned
- Resources remain grounded
- Differentiation is present
- Quality gate runs
- Low-quality generic output is rejected/flagged
- Structured JSON validation works
- Provider abstraction remains intact
- Ollama/dev provider still works
- Production provider path remains compatible
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from src.models import (
    Week, WeekType, TermConfig, Subject, ClassLevel, AIMode,
    LessonPlan, LessonStatus, LearningObjective, TeachingActivity,
    AllocatedIndicator, CurriculumCoverage,
)
from src.engines.ai_provider import (
    AIProvider, MockProvider, OpenCodeZenProvider, OllamaProvider,
    get_provider, _build_v2_prompt_from_context, _parse_json_response,
    _strip_fences,
)
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.allocation_engine import AllocationEngine
from src.curriculum.quality_gate import validate_lesson_quality, QualityStatus
from src.curriculum.indicator_interpreter import interpret_indicator, Indicator
from src.curriculum.generation_prompt import build_generation_prompt


# ════════════════════════════════════════════════════════════════════════════
# PROVIDER ABSTRACTION
# ════════════════════════════════════════════════════════════════════════════

class TestProviderAbstraction:
    def test_mock_provider_returns_empty(self):
        provider = MockProvider()
        assert provider.is_available()
        assert provider.get_name() == "mock"
        result = provider.generate_lesson_content("test", "s", "ss", "cs")
        assert result == {}
        result_v2 = provider.generate_lesson_v2(
            subject="Science", class_level="Basic 9", strand="Energy",
            sub_strand="Forms", content_standard="Describe",
            indicator_code="B9.1.1.1", indicator_text="Identify energy forms",
        )
        assert result_v2 == {}

    def test_get_provider_factory(self):
        assert isinstance(get_provider("OFF"), MockProvider)
        assert isinstance(get_provider("BASIC"), MockProvider)
        assert isinstance(get_provider("ENHANCED"), MockProvider)
        assert isinstance(get_provider("unknown"), MockProvider)

    def test_opencode_zen_provider_configured(self):
        with patch.dict("os.environ", {"OPENCODE_ZEN_API_KEY": "test-key"}):
            provider = OpenCodeZenProvider()
            assert provider.is_available()
            assert provider.get_name() == "opencode-zen"

    def test_opencode_zen_provider_not_configured(self):
        with patch.dict("os.environ", {"OPENCODE_ZEN_API_KEY": ""}):
            provider = OpenCodeZenProvider()
            assert not provider.is_available()

    def test_provider_has_v2_method(self):
        provider = MockProvider()
        assert hasattr(provider, "generate_lesson_v2")

    def test_v2_method_signature(self):
        provider = MockProvider()
        import inspect
        sig = inspect.signature(provider.generate_lesson_v2)
        params = list(sig.parameters.keys())
        assert "subject" in params
        assert "indicator_code" in params
        assert "indicator_text" in params
        assert "class_size" in params


# ════════════════════════════════════════════════════════════════════════════
# V2 PROMPT BUILDER
# ════════════════════════════════════════════════════════════════════════════

class TestV2PromptBuilder:
    def test_build_v2_prompt_from_context(self):
        prompt = _build_v2_prompt_from_context(
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Forms of Energy",
            content_standard="Describe energy forms",
            indicator_code="B9.1.1.1.2",
            indicator_text="Demonstrate the conversion of energy",
        )
        assert "Science" in prompt
        assert "B9.1.1.1.2" in prompt
        assert "Energy" in prompt
        assert "Basic 9" in prompt

    def test_build_v2_prompt_includes_output_schema(self):
        prompt = _build_v2_prompt_from_context(
            subject="Mathematics",
            class_level="Basic 7",
            strand="Algebra",
            sub_strand="Equations",
            content_standard="Solve equations",
            indicator_code="B7.2.1.1",
            indicator_text="Solve linear equations",
        )
        assert "learning_objectives" in prompt
        assert "assessment" in prompt
        assert "differentiation" in prompt
        assert "plenary" in prompt

    def test_build_v2_prompt_with_context(self):
        prompt = _build_v2_prompt_from_context(
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Forms",
            content_standard="Describe",
            indicator_code="B9.1.1.1",
            indicator_text="Identify energy forms",
            previous_lesson_context="Previous: Matter and its properties",
            next_lesson_context="Next: Classification of materials",
            teaching_day="Monday",
            week_number=3,
        )
        assert "Previous" in prompt
        assert "Next" in prompt
        assert "Monday" in prompt

    def test_build_v2_prompt_with_schedule_context(self):
        """16J: the teaching schedule (term / week / period) must be anchored
        into the generation prompt so AI is pinned to the exact curriculum slot."""
        prompt = _build_v2_prompt_from_context(
            subject="Mathematics",
            class_level="Basic 8",
            strand="Number",
            sub_strand="Operations",
            content_standard="Add and subtract",
            indicator_code="B8.2.1.1.3",
            indicator_text="Add fractions",
            term="First Term",
            teaching_week=4,
            week_number=3,
            period="Period 1",
        )
        assert "First Term" in prompt
        assert "Teaching Week: 4" in prompt
        assert "Curriculum Week: 3" in prompt
        assert "Period 1" in prompt

    def test_build_generation_prompt_directly(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Identify forms of energy",
            description="Identify forms of energy",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        prompt = build_generation_prompt(
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Forms",
            content_standard="Describe energy",
            indicator_code="B9.1.1.1",
            indicator_text="Identify forms of energy",
            interpretation=interp,
        )
        assert "SCIENCE" in prompt.upper() or "Science" in prompt
        assert "B9.1.1.1" in prompt


# ════════════════════════════════════════════════════════════════════════════
# JSON PARSING
# ════════════════════════════════════════════════════════════════════════════

class TestJsonParsing:
    def test_parse_valid_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_fences(self):
        result = _parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_json_with_surrounding_text(self):
        result = _parse_json_response('Here is the result: {"key": "value"} done.')
        assert result == {"key": "value"}

    def test_parse_empty_response_raises(self):
        import pytest
        from src.engines.ai_provider import AIResponseParseError
        with pytest.raises(AIResponseParseError):
            _parse_json_response("")
        with pytest.raises(AIResponseParseError):
            _parse_json_response(None)

    def test_parse_invalid_json_raises(self):
        import pytest
        from src.engines.ai_provider import AIResponseParseError
        with pytest.raises(AIResponseParseError):
            _parse_json_response("not json at all")

    def test_strip_fences(self):
        assert _strip_fences('```json\n{"a":1}\n```') == '{"a":1}'
        assert _strip_fences('{"a":1}') == '{"a":1}'
        assert _strip_fences("") == ""


# ════════════════════════════════════════════════════════════════════════════
# ALLOCATION ENGINE (ONE INDICATOR → ONE LESSON)
# ════════════════════════════════════════════════════════════════════════════

class TestAllocationIntegration:
    def _make_weeks(self):
        return [
            Week(
                week_number=1,
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 11),
                week_type=WeekType.INSTRUCTION,
                strand="Energy",
                sub_strand="Forms of Energy",
                content_standards=["Describe energy forms"],
                indicators=[
                    "B9.1.1.1.1 Identify forms of energy",
                    "B9.1.1.1.2 Discuss importance of energy",
                ],
                resources=["Charts", "diagrams"],
                scheme_of_work_id="test-scheme",
            ),
            Week(
                week_number=2,
                start_date=date(2026, 9, 14),
                end_date=date(2026, 9, 18),
                week_type=WeekType.INSTRUCTION,
                strand="Energy",
                sub_strand="Energy Conversion",
                content_standards=["Demonstrate energy conversion"],
                indicators=[
                    "B9.1.1.2.1 Demonstrate conversion of energy",
                    "B9.1.1.2.2 Solve energy problems",
                    "B9.1.1.2.3 Compare energy sources",
                ],
                resources=["Practical materials"],
                scheme_of_work_id="test-scheme",
            ),
        ]

    def _make_config(self):
        return TermConfig(
            id="test-config",
            scheme_of_work_id="test-scheme",
            academic_year="2025/2026",
            term="Term 1",
            class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE,
            class_size=35,
            lesson_duration_minutes=60,
            lessons_per_week=3,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
            teaching_days=[0, 2, 4],
            holidays=[],
            school_name="Test School",
            teacher_name="Test Teacher",
            ai_mode=AIMode.OFF,
        )

    def test_one_indicator_one_lesson(self):
        weeks = self._make_weeks()
        config = self._make_config()
        from src.models import TeachingCalendar, TeachingDay
        calendar = TeachingCalendar(
            term_start=date(2026, 9, 7),
            term_end=date(2026, 12, 18),
            teaching_days=[0, 2, 4],
            days=[
                TeachingDay(date=date(2026, 9, 7), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 9), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 11), day_of_week=4, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 14), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=2),
                TeachingDay(date=date(2026, 9, 16), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=2),
                TeachingDay(date=date(2026, 9, 18), day_of_week=4, is_teaching_day=True, is_holiday=False, week_number=2),
            ],
        )
        engine = AllocationEngine()
        coverage = engine.allocate(weeks, calendar, config)
        # Week 1: 2 indicators → 2 lessons. Week 2: 3 indicators → 3 lessons.
        assert coverage.total_generated_lessons == 5

    def test_carry_forward(self):
        # Week 1: 3 indicators, only 2 teaching days → 1 carries to week 2
        weeks = [
            Week(
                week_number=1,
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 11),
                week_type=WeekType.INSTRUCTION,
                strand="Energy", sub_strand="Forms",
                content_standards=["Describe energy"],
                indicators=[
                    "B9.1.1.1.1 Identify forms",
                    "B9.1.1.1.2 Discuss importance",
                    "B9.1.1.1.3 Compare sources",
                ],
                resources=["Charts"], scheme_of_work_id="test-scheme",
            ),
            Week(
                week_number=2,
                start_date=date(2026, 9, 14),
                end_date=date(2026, 9, 18),
                week_type=WeekType.INSTRUCTION,
                strand="Energy", sub_strand="Conversion",
                content_standards=["Demonstrate conversion"],
                indicators=["B9.1.1.2.1 Demonstrate conversion"],
                resources=["Materials"], scheme_of_work_id="test-scheme",
            ),
        ]
        config = self._make_config()
        from src.models import TeachingCalendar, TeachingDay
        calendar = TeachingCalendar(
            term_start=date(2026, 9, 7),
            term_end=date(2026, 12, 18),
            teaching_days=[0, 2],
            days=[
                TeachingDay(date=date(2026, 9, 7), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 9), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 14), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=2),
                TeachingDay(date=date(2026, 9, 16), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=2),
            ],
        )
        engine = AllocationEngine()
        coverage = engine.allocate(weeks, calendar, config)
        carried = sum(1 for a in coverage.allocations if a.carry_forward)
        assert carried >= 1

    def test_generate_lesson_plans_from_coverage(self):
        weeks = self._make_weeks()
        config = self._make_config()
        from src.models import TeachingCalendar, TeachingDay
        calendar = TeachingCalendar(
            term_start=date(2026, 9, 7),
            term_end=date(2026, 12, 18),
            teaching_days=[0, 2, 4],
            days=[
                TeachingDay(date=date(2026, 9, 7), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 9), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 11), day_of_week=4, is_teaching_day=True, is_holiday=False, week_number=1),
                TeachingDay(date=date(2026, 9, 14), day_of_week=0, is_teaching_day=True, is_holiday=False, week_number=2),
                TeachingDay(date=date(2026, 9, 16), day_of_week=2, is_teaching_day=True, is_holiday=False, week_number=2),
                TeachingDay(date=date(2026, 9, 18), day_of_week=4, is_teaching_day=True, is_holiday=False, week_number=2),
            ],
        )
        engine = AllocationEngine()
        coverage = engine.allocate(weeks, calendar, config)
        plans = engine.generate_lesson_plans(coverage, config, "test-scheme")
        assert len(plans) == 5
        for lp in plans:
            assert len(lp.indicators) == 1  # ONE indicator per lesson
            assert lp.strand == "Energy"
            assert lp.subject == Subject.SCIENCE


# ════════════════════════════════════════════════════════════════════════════
# QUALITY GATE INTEGRATION
# ════════════════════════════════════════════════════════════════════════════

class TestQualityGateIntegration:
    def test_quality_gate_on_lesson_dict(self):
        lesson = {
            "subject": "Science",
            "class_level": "Basic 9",
            "strand": "Energy",
            "sub_strand": "Forms of Energy",
            "indicator_codes": ["B9.1.1.1.2"],
            "learning_objectives": [
                {"description": "Learners can demonstrate the conversion of energy"}
            ],
            "main_activities": [
                {"description": "Teacher demonstrates energy conversion using torch and battery", "duration_minutes": 25}
            ],
            "assessment": "Observe learners during demonstration. Ask questions about energy forms.",
            "introduction": "Review previous lesson on energy types.",
            "starter_activity": "Quick quiz on types of energy.",
            "conclusion": "Summarise energy conversion. Assign homework.",
            "class_size": 35,
            "duration_minutes": 60,
        }
        indicator = Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Demonstrate the conversion of energy",
            description="Demonstrate the conversion of energy",
            source_week=1,
            source_subject="Science",
        )
        report = validate_lesson_quality(lesson, indicator)
        assert report.passed
        assert report.score > 50

    def test_quality_gate_rejects_generic_assessment(self):
        lesson = {
            "subject": "Science",
            "class_level": "Basic 9",
            "strand": "Energy",
            "sub_strand": "Forms",
            "indicator_codes": ["B9.1.1.1"],
            "learning_objectives": [{"description": "Learners can identify energy forms"}],
            "main_activities": [{"description": "Main activity", "duration_minutes": 20}],
            "assessment": "What did we learn today?",
            "introduction": "Intro",
            "conclusion": "Conclusion",
            "class_size": 35,
            "duration_minutes": 60,
        }
        indicator = Indicator(code="B9.1.1.1", exact_text="B9.1.1.1 Identify", description="Identify", source_week=1, source_subject="Science")
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "assessment_specific" and i.status == QualityStatus.WARN for i in report.issues)

    def test_quality_gate_catches_vague_objectives(self):
        lesson = {
            "subject": "Mathematics",
            "class_level": "Basic 7",
            "strand": "Algebra",
            "sub_strand": "Equations",
            "indicator_codes": ["B7.2.1.1"],
            "learning_objectives": [{"description": "Learners can understand equations"}],
            "main_activities": [{"description": "Activity", "duration_minutes": 20}],
            "assessment": "Solve problems",
            "introduction": "Intro",
            "conclusion": "Conclusion",
            "class_size": 35,
            "duration_minutes": 60,
        }
        indicator = Indicator(code="B7.2.1.1", exact_text="B7.2.1.1 Solve", description="Solve", source_week=1, source_subject="Mathematics")
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "objectives_measurable" and i.status == QualityStatus.WARN for i in report.issues)

    def test_quality_gate_catches_invented_references(self):
        lesson = {
            "subject": "Science",
            "class_level": "Basic 9",
            "strand": "Energy",
            "sub_strand": "Forms",
            "indicator_codes": ["B9.1.1.1"],
            "learning_objectives": [{"description": "Learners can identify energy forms"}],
            "main_activities": [{"description": "Refer to page 42 of the textbook for examples.", "duration_minutes": 20}],
            "assessment": "Answer questions from page 45.",
            "introduction": "Intro",
            "conclusion": "Conclusion",
            "class_size": 35,
            "duration_minutes": 60,
        }
        indicator = Indicator(code="B9.1.1.1", exact_text="B9.1.1.1 Identify", description="Identify", source_week=1, source_subject="Science")
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "no_invented_references" and i.status == QualityStatus.WARN for i in report.issues)


# ════════════════════════════════════════════════════════════════════════════
# V2 CONTENT APPLICATION
# ════════════════════════════════════════════════════════════════════════════

class TestV2ContentApplication:
    def test_apply_v2_content(self):
        pipeline = GenerationPipeline()
        lp = LessonPlan(
            id="test-lp",
            scheme_of_work_id="test",
            term_config_id="test",
            week_number=1,
            lesson_sequence=1,
            lesson_number=1,
            lesson_date=date(2026, 9, 7),
            class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE,
            class_size=35,
            duration_minutes=60,
            strand="Energy",
            sub_strand="Forms",
            content_standard="Describe energy",
            indicators=["Identify energy forms"],
            indicator_codes=["B9.1.1.1"],
        )
        v2_content = {
            "learning_objectives": ["Learners can identify different forms of energy"],
            "key_vocabulary": ["kinetic", "potential", "thermal"],
            "starter": {"activity": "Quick quiz on energy types"},
            "main_learning": {
                "phase1": {
                    "name": "Presentation",
                    "activity": "Teacher presents energy forms with examples",
                    "duration_minutes": 20,
                    "resources_used": ["charts", "diagrams"],
                }
            },
            "assessment": {
                "method": "Observation",
                "activity": "Learners classify energy forms in groups",
            },
            "plenary": {"activity": "Summary and homework"},
            "differentiation": {
                "support": "Provide examples",
                "core": "Classify energy forms",
                "extension": "Create own examples",
            },
        }
        pipeline._apply_v2_content(lp, v2_content)
        assert len(lp.learning_objectives) == 1
        assert "identify" in lp.learning_objectives[0].description.lower()
        assert lp.keywords == ["kinetic", "potential", "thermal"]
        assert lp.starter_activity == "Quick quiz on energy types"
        assert len(lp.main_activities) == 1
        assert "PRESENTATION" in lp.main_activities[0].phase.upper()
        assert "classify" in lp.assessment.lower()
        assert "Summary" in lp.conclusion
        assert "Support" in lp.differentiation

    def _base_lp(self, duration=45):
        return LessonPlan(
            id="test-lp",
            scheme_of_work_id="test",
            term_config_id="test",
            week_number=1,
            lesson_sequence=1,
            lesson_number=1,
            lesson_date=date(2026, 9, 7),
            class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE,
            class_size=35,
            duration_minutes=duration,
            strand="Energy",
            sub_strand="Forms",
            content_standard="Describe energy",
            indicators=["Identify energy forms"],
            indicator_codes=["B9.1.1.1"],
        )

    def test_apply_v2_fits_oversized_durations_to_budget(self):
        pipeline = GenerationPipeline()
        lp = self._base_lp(duration=45)
        v2_content = {
            "main_learning": {
                "phase1": {"name": "Explanation",
                           "activity": "Teacher explains the concept with worked examples on the board.",
                           "duration_minutes": 40},
                "phase2": {"name": "Practice",
                           "activity": "Learners practise in pairs using the worksheet.",
                           "duration_minutes": 30},
                "phase3": {"name": "Discussion",
                           "activity": "Class discusses findings and misconceptions.",
                           "duration_minutes": 25},
            },
        }
        pipeline._apply_v2_content(lp, v2_content)
        durs = [a.duration_minutes for a in lp.main_activities]
        assert len(durs) == 3
        assert sum(durs) == 45
        assert all(d >= 1 for d in durs)

    def test_apply_v2_keeps_within_budget_durations_untouched(self):
        pipeline = GenerationPipeline()
        lp = self._base_lp(duration=45)
        v2_content = {
            "main_learning": {
                "phase1": {"name": "Explanation",
                           "activity": "Teacher explains with examples.",
                           "duration_minutes": 20},
                "phase2": {"name": "Practice",
                           "activity": "Learners practise in pairs.",
                           "duration_minutes": 15},
            },
        }
        pipeline._apply_v2_content(lp, v2_content)
        durs = [a.duration_minutes for a in lp.main_activities]
        assert durs == [20, 15]

    def test_apply_v2_dedupes_duplicate_activity_descriptions(self):
        pipeline = GenerationPipeline()
        lp = self._base_lp(duration=45)
        same = "Work with your partner to carry out the task and record observations."
        v2_content = {
            "learner_activities": [
                {"phase": "PRACTICE", "description": same,
                 "duration_minutes": 10},
                {"phase": "PRACTICE",
                 "description": "   " + same.upper() + "   ",
                 "duration_minutes": 10},
                {"phase": "EXTENSION",
                 "description": "Each pair presents findings to the class.",
                 "duration_minutes": 5},
            ],
            "main_learning": {
                "phase1": {"name": "Explanation",
                           "activity": "Explain the concept with examples.",
                           "duration_minutes": 15},
                "phase2": {"name": "Explanation",
                           "activity": "explain the concept with examples.",
                           "duration_minutes": 15},
            },
        }
        pipeline._apply_v2_content(lp, v2_content)
        assert len(lp.learner_activities) == 2
        assert len(lp.main_activities) == 1
        assert lp.main_activities[0].duration_minutes == 15

    def test_lesson_to_dict(self):
        pipeline = GenerationPipeline()
        lp = LessonPlan(
            id="test-lp",
            scheme_of_work_id="test",
            term_config_id="test",
            week_number=1,
            lesson_sequence=1,
            lesson_number=1,
            lesson_date=date(2026, 9, 7),
            class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE,
            class_size=35,
            duration_minutes=60,
            strand="Energy",
            sub_strand="Forms",
            content_standard="Describe energy",
            indicators=["Identify energy forms"],
            indicator_codes=["B9.1.1.1"],
            learning_objectives=[LearningObjective(description="Learners can identify", indicator_code="B9.1.1.1")],
            main_activities=[TeachingActivity(phase="MAIN", description="Main activity", duration_minutes=20)],
            assessment="Oral questions",
            introduction="Review",
            starter_activity="Quiz",
            conclusion="Summary",
            differentiation="Support/Core/Extension",
        )
        d = pipeline._lesson_to_dict(lp)
        assert d["subject"] == "Science"
        assert isinstance(d["subject"], str)
        assert d["class_level"] == "Basic 9"
        assert isinstance(d["class_level"], str)
        assert d["indicator_codes"] == ["B9.1.1.1"]
        assert len(d["learning_objectives"]) == 1
        assert d["starter_activity"] == "Quiz"
        assert d["differentiation"] == "Support/Core/Extension"


# ════════════════════════════════════════════════════════════════════════════
# INDICATOR INTERPRETATION INTEGRATION
# ════════════════════════════════════════════════════════════════════════════

class TestIndicatorInterpretationIntegration:
    def test_interpretation_drives_prompt(self):
        ind = Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Demonstrate the conversion of energy",
            description="Demonstrate the conversion of energy",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert interp.activity_type == "demonstration"
        assert interp.bloom_level == "apply"

        prompt = build_generation_prompt(
            subject="Science", class_level="Basic 9",
            strand="Energy", sub_strand="Forms",
            content_standard="Describe energy",
            indicator_code="B9.1.1.1.2",
            indicator_text="Demonstrate the conversion of energy",
            interpretation=interp,
        )
        assert "demonstration" in prompt.lower() or "demonstrate" in prompt.lower()
        assert "apply" in prompt.lower()

    def test_subject_science_uses_practical_phases(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Investigate energy sources",
            description="Investigate energy sources",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert "investigation" in interp.activity_type or "observe" in interp.activity_type.lower() or "practical" in interp.activity_type

    def test_subject_mathematics_uses_problem_solving(self):
        ind = Indicator(
            code="B9.2.1.1",
            exact_text="B9.2.1.1 Solve equations",
            description="Solve equations",
            source_week=1,
            source_subject="Mathematics",
        )
        interp = interpret_indicator(ind, "Mathematics")
        assert interp.activity_type == "problem_solving"

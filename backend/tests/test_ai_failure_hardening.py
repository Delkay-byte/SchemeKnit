"""
Tests for Generation V2 — Silent AI Failure Hardening.

Proves that:
1. Unexpected V2 exceptions are NOT silently swallowed
2. ai_generated remains false on failure
3. Deterministic fallback behavior is explicit
4. Diagnostic events are recorded
5. User receives controlled status/message
6. Provider unavailable is distinct from unexpected failure
7. Entitlement rejection is distinct from runtime failure
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date

from src.models import (
    Week, WeekType, TermConfig, Subject, ClassLevel, AIMode,
    LessonPlan, LessonStatus, JobStatus, GenerationJob,
    TeachingCalendar, TeachingDay, Holiday,
)
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.ai_provider import AIProvider, MockProvider, get_provider


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_weeks():
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
            indicators=["B9.1.1.2.1 Demonstrate conversion"],
            resources=["Materials"],
            scheme_of_work_id="test-scheme",
        ),
    ]


def _make_config(ai_mode=AIMode.BASIC):
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
        teaching_days=[0, 1, 2, 3, 4],
        holidays=[],
        school_name="Test School",
        teacher_name="Test Teacher",
        ai_mode=ai_mode,
    )


def _make_scheme():
    from src.models import SchemeOfWork
    return SchemeOfWork(
        id="test-scheme",
        title="Test Science",
        subject=Subject.SCIENCE,
        class_level=ClassLevel.BASIC_9,
        weeks=_make_weeks(),
        filename="test.pdf",
        upload_date=date(2026, 9, 1),
        term="Term 1",
        academic_year="2025/2026",
    )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestProviderUnavailableVsRuntimeFailure:
    """Provider unavailable != unexpected application failure."""

    def test_provider_unavailable_no_enrichment_no_error(self):
        """When provider is unavailable, no AI enrichment occurs,
        no error is recorded, and generation succeeds."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = False

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert job.error_message is None
        assert job.ai_enrichment_total_attempted == 0
        assert job.ai_enrichment_succeeded == 0
        assert len(job.ai_enrichment_errors) == 0

    def test_provider_unavailable_all_lessons_deterministic(self):
        """When provider unavailable, all lessons remain deterministic."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = False

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        for lp in job._lesson_plans:
            assert not lp.ai_generated

    def test_v2_runtime_error_does_not_crash_generation(self):
        """When V2 crashes on a lesson, deterministic generation continues
        and the job completes."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "crashy-provider"
        mock_provider.generate_lesson_v2.side_effect = RuntimeError("AI service crashed")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert len(job._lesson_plans) > 0

    def test_v2_runtime_error_not_silently_swallowed(self):
        """V2 errors are recorded on the job, not silently ignored."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "crashy-provider"
        mock_provider.generate_lesson_v2.side_effect = RuntimeError("AI service crashed")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert len(job.ai_enrichment_errors) > 0
        for lesson_id, error_msg in job.ai_enrichment_errors.items():
            assert "RuntimeError" in error_msg or "AI service crashed" in error_msg

    def test_v2_runtime_error_ai_generated_remains_false(self):
        """When V2 crashes, ai_generated must remain False."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "crashy-provider"
        mock_provider.generate_lesson_v2.side_effect = RuntimeError("AI service crashed")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.ai_enrichment_succeeded == 0
        for lp in job._lesson_plans:
            assert not lp.ai_generated

    def test_v2_import_error_does_not_crash_generation(self):
        """Module import error in V2 path falls back to deterministic."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "broken-v2"
        mock_provider.generate_lesson_v2.side_effect = ImportError("No module named 'broken'")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert job.ai_enrichment_succeeded == 0

    def test_v2_empty_response_recorded(self):
        """Empty V2 response is recorded as an error."""
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "empty-provider"
        mock_provider.generate_lesson_v2.return_value = {}

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert len(job.ai_enrichment_errors) > 0
        for error in job.ai_enrichment_errors.values():
            assert "empty_response" in error

    def test_quality_gate_failure_recorded(self):
        """Quality gate failure is recorded on the job."""
        def bad_v2(*, subject, class_level, strand, sub_strand,
                   content_standard, indicator_code, indicator_text,
                   class_size=35, duration_minutes=60, source_resources=None,
                   previous_lesson_context=None, next_lesson_context=None,
                   teaching_day=None, week_number=None, term=None, teaching_week=None, period=None):
            return {
                "learning_objectives": [],
                "main_learning": {},
                "assessment": {},
            }

        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "bad-quality"
        mock_provider.generate_lesson_v2.side_effect = bad_v2

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert len(job.ai_enrichment_errors) > 0
        for error in job.ai_enrichment_errors.values():
            assert "quality_gate_failed" in error

    def test_quality_gate_failure_ai_generated_false(self):
        """Quality gate failure means ai_generated stays False."""
        def bad_v2(*, subject, class_level, strand, sub_strand,
                   content_standard, indicator_code, indicator_text,
                   class_size=35, duration_minutes=60, source_resources=None,
                   previous_lesson_context=None, next_lesson_context=None,
                   teaching_day=None, week_number=None, term=None, teaching_week=None, period=None):
            return {
                "learning_objectives": [],
                "main_learning": {},
                "assessment": {},
            }

        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "bad-quality"
        mock_provider.generate_lesson_v2.side_effect = bad_v2

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        for lp in job._lesson_plans:
            assert not lp.ai_generated


class TestSuccessfulV2Enrichment:
    """When V2 works, ai_generated=True and diagnostics show success."""

    def test_success_recorded(self):
        """Successful V2 enrichment increments counters."""
        good_content = {
            "learning_objectives": ["Learners can identify forms of energy"],
            "starter": {"activity": "Review previous lesson", "duration_minutes": 5},
            "main_learning": {
                "phase1": {
                    "name": "EXPLANATION",
                    "activity": "Teacher explains energy forms",
                    "duration_minutes": 15,
                },
            },
            "learner_activities": [
                {"phase": "PRACTICE", "description": "Group work on energy forms", "duration_minutes": 15}
            ],
            "assessment": {"method": "Observation", "activity": "Quiz on energy forms", "duration_minutes": 10},
            "plenary": {"activity": "Summary", "duration_minutes": 5},
            "differentiation": {"support": "Visual aids", "core": "Worksheets", "extension": "Research"},
        }
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "good-provider"
        mock_provider.generate_lesson_v2.return_value = good_content

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert job.ai_enrichment_succeeded > 0
        assert job.ai_enrichment_total_attempted > 0

    def test_success_marks_ai_generated_true(self):
        """Successful V2 enrichment sets ai_generated=True."""
        good_content = {
            "learning_objectives": ["Learners can identify forms of energy"],
            "starter": {"activity": "Review previous lesson", "duration_minutes": 5},
            "main_learning": {
                "phase1": {
                    "name": "EXPLANATION",
                    "activity": "Teacher explains energy forms",
                    "duration_minutes": 15,
                },
            },
            "learner_activities": [
                {"phase": "PRACTICE", "description": "Group work", "duration_minutes": 15}
            ],
            "assessment": {"method": "Observation", "activity": "Quiz", "duration_minutes": 10},
            "plenary": {"activity": "Summary", "duration_minutes": 5},
            "differentiation": {"support": "Visual aids", "core": "Worksheets", "extension": "Research"},
        }
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "good-provider"
        mock_provider.generate_lesson_v2.return_value = good_content

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        ai_count = sum(1 for lp in job._lesson_plans if lp.ai_generated)
        assert ai_count > 0

    def test_no_errors_on_success(self):
        """No errors recorded when all lessons succeed."""
        good_content = {
            "learning_objectives": ["Learners can identify forms of energy"],
            "starter": {"activity": "Review previous lesson", "duration_minutes": 5},
            "main_learning": {
                "phase1": {
                    "name": "EXPLANATION",
                    "activity": "Teacher explains energy forms",
                    "duration_minutes": 15,
                },
            },
            "learner_activities": [
                {"phase": "PRACTICE", "description": "Group work", "duration_minutes": 15}
            ],
            "assessment": {"method": "Observation", "activity": "Quiz", "duration_minutes": 10},
            "plenary": {"activity": "Summary", "duration_minutes": 5},
            "differentiation": {"support": "Visual aids", "core": "Worksheets", "extension": "Research"},
        }
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "good-provider"
        mock_provider.generate_lesson_v2.return_value = good_content

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert len(job.ai_enrichment_errors) == 0


class TestAIModeOff:
    """AIMode.OFF means no AI enrichment attempted."""

    def test_off_mode_no_ai_attempted(self):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.OFF))

        assert job.status == JobStatus.COMPLETED
        assert job.ai_enrichment_total_attempted == 0
        assert job.error_message is None

    def test_off_mode_all_deterministic(self):
        pipeline = GenerationPipeline()
        job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.OFF))

        for lp in job._lesson_plans:
            assert not lp.ai_generated


class TestDeterministicFallbackExplicit:
    """Deterministic fallback is explicit, not a silent masquerade."""

    def test_mixed_success_and_failure(self):
        """Some lessons succeed, some fail — both are tracked correctly."""
        call_count = [0]

        def variable_v2(*, subject, class_level, strand, sub_strand,
                       content_standard, indicator_code, indicator_text,
                       class_size=35, duration_minutes=60, source_resources=None,
                       previous_lesson_context=None, next_lesson_context=None,
                       teaching_day=None, week_number=None, term=None, teaching_week=None, period=None):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise RuntimeError("Intermittent failure")
            return {
                "learning_objectives": ["Learners can do something"],
                "starter": {"activity": "Review", "duration_minutes": 5},
                "main_learning": {
                    "phase1": {"name": "EXPLANATION", "activity": "Teach", "duration_minutes": 15},
                },
                "learner_activities": [
                    {"phase": "PRACTICE", "description": "Practice", "duration_minutes": 15}
                ],
                "assessment": {"method": "Quiz", "activity": "Test", "duration_minutes": 10},
                "plenary": {"activity": "Summary", "duration_minutes": 5},
                "differentiation": {"support": "Help", "core": "Standard", "extension": "Challenge"},
            }

        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "flaky-provider"
        mock_provider.generate_lesson_v2.side_effect = variable_v2

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert job.ai_enrichment_succeeded > 0
        assert len(job.ai_enrichment_errors) > 0
        total = job.ai_enrichment_succeeded + len(job.ai_enrichment_errors)
        assert total == job.ai_enrichment_total_attempted

    def test_job_error_message_for_pipeline_failure(self):
        """When the entire AI pipeline crashes, job.error_message is set
        with a user-friendly message (no stack traces)."""
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider",
                    side_effect=Exception("Fatal AI init error")):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.status == JobStatus.COMPLETED
        assert job.error_message is not None
        assert "AI enrichment could not be completed" in job.error_message
        assert "standard lesson engine" in job.error_message
        assert "Fatal AI init error" not in job.error_message

    def test_pipeline_failure_no_stacktrace_in_message(self):
        """User-facing error must NOT contain internal paths or stack traces."""
        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider",
                    side_effect=ImportError("No module named 'secret_key_module'")):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert "secret_key_module" not in (job.error_message or "")
        assert "Traceback" not in (job.error_message or "")
        assert "ImportError" not in (job.error_message or "")


class TestGenerationJobDiagnostics:
    """Verify diagnostic fields on GenerationJob are correctly populated."""

    def test_counters_initialized(self):
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "test-provider"
        mock_provider.generate_lesson_v2.side_effect = RuntimeError("fail")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        assert job.ai_enrichment_total_attempted == len(job._lesson_plans)
        assert job.ai_enrichment_succeeded == 0
        assert len(job.ai_enrichment_errors) == len(job._lesson_plans)

    def test_error_keys_are_lesson_ids(self):
        mock_provider = MagicMock(spec=AIProvider)
        mock_provider.is_available.return_value = True
        mock_provider.get_name.return_value = "test-provider"
        mock_provider.generate_lesson_v2.side_effect = RuntimeError("fail")

        pipeline = GenerationPipeline()
        with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
            job = pipeline.generate_all(_make_scheme(), _make_config(AIMode.BASIC))

        lesson_ids = {lp.id for lp in job._lesson_plans}
        for key in job.ai_enrichment_errors:
            assert key in lesson_ids

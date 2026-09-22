"""
AI-Enriched Generation V2 Tests — Real V2 Pipeline Path

Exercises the real V2 generation path:
  Curriculum IR → build_generation_prompt() → provider → structured JSON
  → _apply_v2_content() → quality gate → LessonPlan

Uses a mock provider that returns realistic structured JSON, exercising the
full V2 pipeline without requiring a live Ollama/OpenAI endpoint.
"""
import sys; sys.path.insert(0, '.')
import json
from pathlib import Path
from datetime import date
from typing import Dict, Any, Optional
from unittest.mock import patch

from src.parsers.pdf_parser import PDFParser
from src.models import (
    WeekType, Subject, TermConfig, AIMode, Holiday, TeachingCalendar, TeachingDay,
)
from src.engines.generation_pipeline import GenerationPipeline
from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.engines.ai_provider import AIProvider, _build_v2_prompt_from_context, _parse_json_response
from src.curriculum import Indicator
from src.curriculum.quality_gate import validate_lesson_quality, QualityStatus

REAL_DOCS = Path(__file__).parent.parent / "real_documents"
BASIC7_PDF = REAL_DOCS / "BASIC 7 TERM 1.pdf"
BASIC9_PDF = REAL_DOCS / "BASIC 9 TERM 1.pdf"


class RealisticV2MockProvider(AIProvider):
    """Mock provider that returns realistic V2 structured JSON.

    This exercises the full V2 pipeline: prompt building, JSON parsing,
    content application, and quality gate validation.
    """

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           term=None, teaching_week=None, period=None):
        # Build the real V2 prompt (proves prompt construction works)
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
            previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
        )
        # Verify prompt contains the indicator (debug check)
        prompt_ok = indicator_code in prompt or indicator_text in prompt
        if not prompt_ok:
            print(f"  WARNING: Prompt missing indicator: code={indicator_code}")

        topic = indicator_text.split('.')[0] if '.' in indicator_text else indicator_text
        verb = indicator_text.split(' ', 1)[-1] if ' ' in indicator_text else indicator_text

        return {
            "learning_objectives": [
                f"Learners can {verb}"
            ],
            "key_vocabulary": [f"{sub_strand}", "classification", "properties"],
            "starter": {
                "activity": f"Teacher displays two contrasting examples of {sub_strand}. "
                           f"Learners observe in pairs and identify similarities and differences. "
                           f"This activates prior knowledge about {strand}.",
                "duration_minutes": 8,
                "resources": ["chart", "real objects"],
                "teacher_action": "Display contrasting examples and guide observation",
                "learner_action": "Observe, discuss in pairs, and share findings",
            },
            "main_learning": {
                "phase1": {
                    "name": "EXPLANATION",
                    "activity": f"Teacher explains the concept of {topic} "
                              f"using diagrams and real-life examples from the Ghanaian context. "
                              f"Teacher draws a labelled diagram on the board showing key components.",
                    "duration_minutes": 15,
                    "teacher_action": "Explain with diagrams and board work",
                    "learner_action": "Listen, take notes, ask questions",
                    "resources_used": ["chalkboard", "diagrams"],
                },
                "phase2": {
                    "name": "MODELLING",
                    "activity": f"Teacher demonstrates the process step by step. "
                              f"Learners observe and take notes. "
                              f"Teacher asks guiding questions to check understanding.",
                    "duration_minutes": 12,
                    "teacher_action": "Demonstrate and question",
                    "learner_action": "Observe, take notes, respond to questions",
                    "resources_used": ["real materials", "chart"],
                },
            },
            "learner_activities": [
                {
                    "phase": "PRACTICE",
                    "description": f"Working in pairs, learners examine provided samples and "
                                  f"complete a structured worksheet recording their observations about {sub_strand}. "
                                  f"Each pair presents their findings to the class.",
                    "duration_minutes": 15,
                    "resources": ["worksheet", "samples"],
                },
            ],
            "assessment": {
                "method": "Observation and worksheet evaluation",
                "activity": f"Teacher observes pair work and records which learners can correctly identify and explain {topic}. "
                           f"Each pair presents their observation sheet — teacher checks for accuracy of key concepts related to {sub_strand}.",
                "success_criteria": f"Learners can correctly identify and explain {topic}.",
                "duration_minutes": 10,
            },
            "plenary": {
                "activity": f"Teacher leads a class discussion summarising the key points about {sub_strand}. "
                           f"Learners share one thing they learned and one question they still have.",
                "duration_minutes": 5,
                "teacher_action": "Facilitate discussion",
                "learner_action": "Share reflections and questions",
            },
            "differentiation": {
                "support": f"Provide partially completed diagrams and a word bank for learners who need support with {sub_strand}.",
                "core": f"All learners complete the observation worksheet with teacher guidance.",
                "extension": f"Advanced learners research an additional real-world application of {sub_strand} in Ghana and present findings next lesson.",
            },
            "homework_or_extension": f"Write a short paragraph describing how the concept of {sub_strand} applies in everyday life in Ghana.",
            "teacher_notes": f"Ensure all learners participate in the hands-on activity. "
                            f"Use local examples relevant to the Ghanaian context.",
        }

    def is_available(self):
        return True


def _make_term_config(scheme_id="ai-test"):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7),
        term_end_date=date(2026, 12, 18),
        semester=1,
        lessons_per_week=3,
        lesson_duration_minutes=45,
        teaching_days=[0, 1, 2, 3, 4],
        holidays=[Holiday(name="Founder's Day", date=date(2026, 11, 20))],
        ai_mode=AIMode.BASIC,
    )


def test_ai_enriched_basic7_science():
    """Generate AI-enriched lessons from real Basic 7 Science and inspect quality."""
    parser = PDFParser()
    scheme = asyncio.run(
        parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
    )
    config = _make_term_config()

    # Generate deterministic baseline first
    pipeline = GenerationPipeline()
    job_det = pipeline.generate_all(scheme, config)
    if hasattr(job_det, '_lesson_plans'):
        det_lessons = job_det._lesson_plans
    else:
        print(f"  DET ERROR: status={job_det.status} msg={job_det.error_message}")
        det_lessons = []

    # Now generate with AI enrichment (mock provider)
    pipeline_ai = GenerationPipeline()
    mock_provider = RealisticV2MockProvider()

    with patch("src.engines.generation_pipeline.get_provider", return_value=mock_provider):
        job_ai = pipeline_ai.generate_all(scheme, config)

    if job_ai.status.value != "completed":
        print(f"  AI ERROR: Generation failed: {job_ai.error_message}")

    if hasattr(job_ai, '_lesson_plans'):
        ai_lessons = job_ai._lesson_plans
    else:
        print(f"  AI ERROR: status={job_ai.status} msg={job_ai.error_message}")
        ai_lessons = []

    print(f"\n{'='*80}")
    print(f"BASIC 7 SCIENCE — AI-ENRICHED GENERATION")
    print(f"{'='*80}")
    print(f"Deterministic lessons: {len(det_lessons)}")
    print(f"AI-enriched lessons: {len(ai_lessons)}")

    ai_count = sum(1 for lp in ai_lessons if lp.ai_generated)
    print(f"Lessons marked ai_generated: {ai_count}/{len(ai_lessons)}")

    # Compare first 3 lessons in detail
    for i in range(min(3, len(ai_lessons))):
        det = det_lessons[i]
        ai = ai_lessons[i]
        print(f"\n{'='*80}")
        print(f"LESSON {i+1}: Week {ai.week_number} | Seq {ai.lesson_sequence}")
        print(f"  Strand: {ai.strand}")
        print(f"  Sub-strand: {ai.sub_strand}")
        print(f"  Indicator: {ai.indicator_codes}")
        print(f"  ai_generated: {ai.ai_generated}")

        print(f"\n  OBJECTIVES:")
        for o in ai.learning_objectives:
            print(f"    - {o.description[:80]}")

        print(f"\n  STARTER: {(getattr(ai, 'starter_activity', '') or '')[:120]}...")

        print(f"\n  MAIN ACTIVITIES ({len(ai.main_activities)}):")
        for a in ai.main_activities:
            print(f"    [{a.phase}] {a.description[:100]}...")

        print(f"\n  LEARNER ACTIVITIES ({len(ai.learner_activities)}):")
        for a in ai.learner_activities:
            print(f"    [{a.phase}] {a.description[:100]}...")

        print(f"\n  ASSESSMENT: {(ai.assessment or '')[:150]}...")

        print(f"\n  CONCLUSION: {(ai.conclusion or '')[:120]}...")

        # Compare with deterministic
        print(f"\n  DETERMINISTIC vs AI:")
        det_obj = det.learning_objectives[0].description if det.learning_objectives else ""
        ai_obj = ai.learning_objectives[0].description if ai.learning_objectives else ""
        print(f"    Det objectives: {det_obj[:80]}")
        print(f"    AI objectives:  {ai_obj[:80]}")
        print(f"    Det activities: {len(det.main_activities)} main, {len(det.learner_activities)} learner")
        print(f"    AI activities:  {len(ai.main_activities)} main, {len(ai.learner_activities)} learner")

    # Quality gate on AI-enriched lessons
    from src.curriculum.quality_gate import validate_lesson_quality
    print(f"\n{'='*80}")
    print(f"QUALITY GATE - AI-ENRICHED LESSONS")
    print(f"{'='*80}")
    passed = 0
    for lp in ai_lessons[:3]:
        indicator = Indicator(
            code=lp.indicator_codes[0] if lp.indicator_codes else "unknown",
            exact_text=lp.indicators[0] if lp.indicators else "",
            description=lp.indicators[0] if lp.indicators else "",
            source_week=lp.week_number, source_subject="Science",
        )
        lesson_dict = {
            "indicator_codes": lp.indicator_codes,
            "learning_objectives": [{"text": o.description, "indicator_code": o.indicator_code}
                                    for o in lp.learning_objectives],
            "main_activities": [{"phase": a.phase, "description": a.description,
                                "duration_minutes": a.duration_minutes}
                               for a in lp.main_activities],
            "learner_activities": [{"phase": a.phase, "description": a.description,
                                   "duration_minutes": a.duration_minutes}
                                  for a in lp.learner_activities],
            "assessment": lp.assessment,
            "introduction": getattr(lp, 'introduction', '') or '',
            "conclusion": lp.conclusion,
            "subject": "Science",
            "strand": lp.strand,
            "duration_minutes": config.lesson_duration_minutes,
            "resources": [],
        }
        report = validate_lesson_quality(lesson_dict, indicator)
        status_icon = "PASS" if report.overall_status in ("pass", "warn") else "FAIL"
        if status_icon == "PASS":
            passed += 1
        print(f"  Wk{lp.week_number} Seq{lp.lesson_sequence}: {status_icon} (score={report.score}, status={report.overall_status})")
        for issue in report.issues:
            if issue.status in ("fail", "warn"):
                print(f"    [{issue.status.upper()}] {issue.message}")

    print(f"\nQuality Gate: {passed}/{min(3, len(ai_lessons))} passed (first 3 lessons)")
    print(f"ai_generated count: {sum(1 for lp in ai_lessons if lp.ai_generated)}/{len(ai_lessons)}")

    # Variation check
    print(f"\n{'='*80}")
    print(f"VARIATION CHECK")
    print(f"{'='*80}")
    starters = [(getattr(lp, 'starter_activity', '') or '')[:80] for lp in ai_lessons[:5]]
    assessments = [(getattr(lp, 'assessment', '') or '')[:80] for lp in ai_lessons[:5]]
    objectives = [" ".join(o.description[:40] for o in lp.learning_objectives) for lp in ai_lessons[:5]]

    print(f"  Starter variation: {len(set(starters))} unique out of {len(starters)}")
    for i, s in enumerate(starters):
        print(f"    [{i+1}] {s}...")
    print(f"  Assessment variation: {len(set(assessments))} unique out of {len(assessments)}")
    print(f"  Objective variation: {len(set(objectives))} unique out of {len(objectives)}")

    assert len(set(starters)) >= 2, "Starters appear repetitive"
    assert len(set(objectives)) >= 2, "Objectives appear repetitive"


import asyncio

if __name__ == "__main__":
    lessons = test_ai_enriched_basic7_science()
    print(f"\n{'='*80}")
    print(f"SUMMARY: Generated {len(lessons)} AI-enriched lessons")
    print(f"{'='*80}")

"""
Generation Engine V3 quality tests (PART W — GENERATION QUALITY).

Deterministic generation must produce a lesson that is visibly about the
uploaded indicator, uses subject-appropriate pedagogy, forms one coherent
three-phase story, respects the configured time, and passes the quality gate.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import (
    Week, WeekType, SchemeOfWork, TermConfig, Subject, ClassLevel, AIMode,
)
from src.engines.generation_pipeline import GenerationPipeline
from src.curriculum.quality_gate import validate_lesson_quality, QualityStatus
from src.curriculum import Indicator


def _weeks(indicator_codes, strand, sub_strand, content_standard="B7.1.1.1 Standard"):
    """Build instruction weeks, 3 indicators per week."""
    weeks = []
    counter = 1
    for code in indicator_codes:
        wn = (counter - 1) // 3 + 1
        if not weeks or weeks[-1].week_number != wn:
            weeks.append(Week(
                week_number=wn, start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 11), week_type=WeekType.INSTRUCTION,
                strand=strand, sub_strand=sub_strand,
                content_standards=[content_standard], indicators=[],
                resources=[], scheme_of_work_id="s",
            ))
        weeks[-1].indicators.append(code)
        counter += 1
    return weeks


def _config(subject, duration=60):
    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_7, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=duration,
        teaching_days=[0, 1, 2], holidays=[], ai_mode=AIMode.OFF,
        school_name="Test School", teacher_name="Test Teacher",
    )


def _run(subject, indicator_codes, strand, sub_strand, duration=60,
         selected=None):
    weeks = _weeks(indicator_codes, strand, sub_strand)
    scheme = SchemeOfWork(
        id="s", filename="x.docx", class_level=ClassLevel.BASIC_7,
        subject=subject, term="First Term", academic_year="2026/2027",
        weeks=weeks, upload_date=date.today(),
    )
    config = _config(subject, duration)
    if selected is not None:
        config.selected_indicator_codes = selected
    job = GenerationPipeline().generate_all(scheme, config)
    return scheme, config, job


MATH_CODES = [
    "B7.1.1.1.1 Add whole numbers up to 1000",
    "B7.1.1.1.2 Subtract whole numbers up to 1000",
    "B7.1.1.1.3 Solve word problems involving addition",
]
SCI_CODES = [
    "B7.2.1.1.1 Describe the characteristics of living things",
    "B7.2.1.1.2 Classify materials into solids and liquids",
]
ENG_CODES = [
    "B7.3.1.1.1 Use adjectives correctly in sentences",
]
SOC_CODES = [
    "B7.4.1.1.1 Discuss the roles of members of the family",
]
CRE_CODES = [
    "B7.5.1.1.1 Create a simple pattern using local materials",
]


class TestIndicatorFidelity:
    def test_lesson_carries_exactly_the_uploaded_indicator(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        assert job.total_lessons == 3
        first = sorted(job._lesson_plans, key=lambda lp: lp.lesson_sequence)[0]
        assert first.indicator_codes == ["B7.1.1.1.1"]
        assert "Add whole numbers" in first.indicators[0]

    def test_objective_is_learner_centred_and_about_the_indicator(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        assert len(lp.learning_objectives) == 1
        obj = lp.learning_objectives[0].description
        assert obj.lower().startswith("learners can")
        assert "whole numbers" in obj.lower()
        assert lp.learning_objectives[0].indicator_code == "B7.1.1.1.1"


class TestSubjectPedagogy:
    def test_mathematics_uses_worked_example_and_practice(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        text = " ".join(a.description for a in lp.main_activities).lower()
        assert "example" in text
        assert any(w in text for w in ("practice", "problem"))

    def test_science_uses_inquiry_and_evidence(self):
        scheme, config, job = _run(
            Subject.SCIENCE, SCI_CODES, "Diversity", "Living Things")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        text = " ".join(a.description for a in lp.main_activities).lower()
        assert any(w in text for w in ("demonstrat", "observe", "evidence", "predict"))

    def test_english_uses_model_and_production(self):
        scheme, config, job = _run(
            Subject.ENGLISH, ENG_CODES, "Grammar", "Adjectives")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        text = " ".join(a.description for a in lp.main_activities).lower()
        assert any(w in text for w in ("model", "language", "produ"))
        assert "adjectives" in (lp.starter_activity + lp.assessment).lower()

    def test_subject_strategy_differs_between_subjects(self):
        _, _, math_job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        _, _, sci_job = _run(
            Subject.SCIENCE, SCI_CODES, "Diversity", "Living Things")
        math_text = " ".join(
            a.description for a in math_job._lesson_plans[0].main_activities).lower()
        sci_text = " ".join(
            a.description for a in sci_job._lesson_plans[0].main_activities).lower()
        assert math_text != sci_text

    def test_phases_are_coherent_and_time_is_respected(self):
        scheme, config, job = _run(
            Subject.CREATIVE_ARTS, CRE_CODES, "Visual Arts", "Patterns",
            duration=50)
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        assert lp.starter_activity
        assert lp.introduction
        assert lp.conclusion
        assert len(lp.main_activities) >= 3
        main_total = sum(a.duration_minutes for a in lp.main_activities)
        assert 0 < main_total < lp.duration_minutes
        assert lp.duration_minutes == 50

    def test_differentiation_is_relevant(self):
        scheme, config, job = _run(
            Subject.SOCIAL_STUDIES, SOC_CODES, "Our Nation", "Family")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        text = lp.differentiation.lower()
        assert "support" in text or "extension" in text
        assert "family" in " ".join(a.description for a in lp.main_activities).lower()

    def test_previous_and_next_context_used(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        ordered = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)
        # First lesson previews the next; second references the previous.
        assert "next lesson" in ordered[0].conclusion.lower()
        assert "previous lesson" in (ordered[1].introduction
                                     + ordered[1].previous_knowledge).lower()

    def test_resources_are_realistic(self):
        scheme, config, job = _run(
            Subject.SCIENCE, SCI_CODES, "Diversity", "Living Things")
        expensive = ["projector", "internet", "smartboard", "tablet",
                     "laboratory equipment", "laptop"]
        for lp in job._lesson_plans:
            blob = " ".join(lp.teaching_learning_resources).lower() + " " + \
                   " ".join(a.description for a in lp.main_activities).lower()
            assert not any(e in blob for e in expensive)


class TestQualityGate:
    def _lesson_dict(self, lp):
        return {
            "subject": lp.subject, "class_level": lp.class_level,
            "strand": lp.strand, "sub_strand": lp.sub_strand,
            "lesson_topic": lp.lesson_topic, "indicators": lp.indicators,
            "indicator_codes": lp.indicator_codes,
            "learning_objectives": [{"description": o.description}
                                    for o in lp.learning_objectives],
            "main_activities": [{"description": a.description,
                                 "duration_minutes": a.duration_minutes}
                                for a in lp.main_activities],
            "learner_activities": [{"description": a.description}
                                   for a in lp.learner_activities],
            "assessment": lp.assessment, "introduction": lp.introduction,
            "starter_activity": lp.starter_activity, "conclusion": lp.conclusion,
            "differentiation": lp.differentiation, "class_size": lp.class_size,
            "duration_minutes": lp.duration_minutes,
        }

    def test_valid_deterministic_lesson_passes(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        ind = Indicator(
            code=lp.indicator_codes[0], exact_text=lp.indicators[0],
            description=lp.indicators[0], source_week=lp.week_number,
            source_subject=lp.subject)
        report = validate_lesson_quality(self._lesson_dict(lp), ind)
        assert report.passed, report.summary()

    def test_broken_lesson_is_rejected(self):
        scheme, config, job = _run(
            Subject.MATHEMATICS, MATH_CODES, "Number", "Whole Numbers")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        broken = self._lesson_dict(lp)
        broken["indicator_codes"] = ["B7.9.9.9.9"]
        broken["learning_objectives"] = []
        broken["main_activities"] = []
        broken["assessment"] = ""
        ind = Indicator(
            code="B7.1.1.1.1", exact_text=lp.indicators[0],
            description=lp.indicators[0], source_week=1,
            source_subject=lp.subject)
        report = validate_lesson_quality(broken, ind)
        assert report.overall_status == QualityStatus.FAIL
        assert report.failures

    def test_offscreen_indicator_fails_exactness(self):
        scheme, config, job = _run(
            Subject.SCIENCE, SCI_CODES, "Diversity", "Living Things")
        lp = sorted(job._lesson_plans, key=lambda x: x.lesson_sequence)[0]
        ind = Indicator(
            code="B7.1.1.1.1", exact_text="Add fractions with unlike denominators",
            description="Add fractions with unlike denominators", source_week=1,
            source_subject="Mathematics")
        report = validate_lesson_quality(self._lesson_dict(lp), ind)
        # Content is not about this unrelated indicator.
        assert any(f.check_name == "indicator_exactness" for f in report.failures)


class TestSelectionPreservesCurriculum:
    def _twenty(self):
        return [f"B7.1.1.1.{i} Indicator number {i}" for i in range(1, 21)]

    def test_selection_of_two_of_twenty_generates_two(self):
        codes = self._twenty()
        # Selection is by indicator CODE (what the API sends), not full text.
        selected = [c.split()[0] for c in codes[:2]]
        scheme, config, job = _run(
            Subject.MATHEMATICS, codes, "Number", "Whole Numbers",
            selected=selected)
        assert job.total_lessons == 2
        generated = {lp.indicator_codes[0] for lp in job._lesson_plans}
        assert generated == set(selected)

    def test_full_scheme_remains_intact_after_selection(self):
        codes = self._twenty()
        selected = [c.split()[0] for c in codes[:2]]
        scheme, config, job = _run(
            Subject.MATHEMATICS, codes, "Number", "Whole Numbers",
            selected=selected)
        # Every indicator is still present in the uploaded curriculum.
        remaining = [i for w in scheme.weeks for i in w.indicators]
        assert len(remaining) == 20
        # Source week / sequence / indicator text are preserved on the lessons.
        for lp in job._lesson_plans:
            assert lp.week_number == 1
            assert lp.indicators[0] in remaining

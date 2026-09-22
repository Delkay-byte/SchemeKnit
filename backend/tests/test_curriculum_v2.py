"""
Tests for SchemeKnit V2 Curriculum Normalization, Indicator Interpretation,
Quality Gate, and Generation Prompt Builder.
"""

import pytest
from datetime import date

from src.curriculum import (
    CurriculumDocument, SubjectSection, CurriculumWeek, CurriculumEntry,
    Indicator, CurriculumWeekType, ExtractionMethod,
    SectionDetectionConfidence, split_indicator_text, classify_week_type,
    INDICATOR_CODE_RE,
)
from src.curriculum.indicator_interpreter import (
    interpret_indicator, interpret_indicators,
    _extract_verbs, _determine_bloom_level, _determine_activity_type,
    BLOOM_CATEGORIES, SUBJECT_STRATEGIES, SUBJECT_TO_STRATEGY,
)
from src.curriculum.quality_gate import (
    validate_lesson_quality, QualityStatus, QualityReport,
)
from src.curriculum.generation_prompt import (
    build_generation_prompt, build_section_regeneration_prompt,
    SYSTEM_PROMPT, LESSON_OUTPUT_SCHEMA,
)


# ════════════════════════════════════════════════════════════════════════════
# CURRICULUM NORMALIZATION MODEL
# ════════════════════════════════════════════════════════════════════════════

class TestIndicator:
    def test_code_and_description_split(self):
        ind = Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Discuss the formation of Igneous rocks",
            description="Discuss the formation of Igneous rocks",
            source_week=1,
            source_subject="Science",
        )
        assert ind.code == "B9.1.1.1.2"
        assert "Igneous" in ind.description

    def test_indicator_defaults(self):
        ind = Indicator(code="B7.4.3.1", exact_text="B7.4.3.1 Identify", description="Identify", source_week=1, source_subject="Mathematics")
        assert ind.primary_action is None
        assert ind.activity_type is None


class TestSplitIndicatorText:
    def test_code_and_text(self):
        code, desc = split_indicator_text("B9.1.1.1.2 Discuss the formation of Igneous rocks")
        assert code == "B9.1.1.1.2"
        assert desc == "Discuss the formation of Igneous rocks"

    def test_code_with_colon(self):
        code, desc = split_indicator_text("B9.1.1.1.2: Discuss the formation")
        assert code == "B9.1.1.1.2"
        assert "Discuss" in desc

    def test_no_code(self):
        code, desc = split_indicator_text("Discuss the formation of rocks")
        assert code == ""
        assert "Discuss" in desc

    def test_empty_text(self):
        code, desc = split_indicator_text("")
        assert code == ""
        assert desc == ""

    def test_multiple_dots(self):
        code, desc = split_indicator_text("B9.1.1.1.2 Advanced indicator")
        assert code == "B9.1.1.1.2"
        assert "Advanced" in desc


class TestClassifyWeekType:
    def test_revision_week(self):
        entries = [CurriculumEntry(strand="Revision", sub_strand="", content_standard="")]
        assert classify_week_type(13, entries) == CurriculumWeekType.REVISION

    def test_assessment_week(self):
        entries = [CurriculumEntry(strand="End of Term Assessment", sub_strand="", content_standard="")]
        assert classify_week_type(14, entries) == CurriculumWeekType.ASSESSMENT

    def test_sba_week(self):
        entries = [CurriculumEntry(strand="SBA Activities and Vacation", sub_strand="", content_standard="")]
        assert classify_week_type(15, entries) == CurriculumWeekType.SBA_VACATION

    def test_instructional_week(self):
        ind = Indicator(code="B9.1.1.1", exact_text="B9.1.1.1 Identify", description="Identify", source_week=1, source_subject="Science")
        entries = [CurriculumEntry(strand="Energy", sub_strand="Forms of Energy", content_standard="Describe energy", indicators=[ind])]
        assert classify_week_type(1, entries) == CurriculumWeekType.INSTRUCTION

    def test_empty_week(self):
        entries = []
        assert classify_week_type(1, entries) == CurriculumWeekType.OTHER

    def test_header_text_override(self):
        entries = []
        assert classify_week_type(13, entries, header_text="Week 13: Revision") == CurriculumWeekType.REVISION


class TestCurriculumWeek:
    def test_all_indicators(self):
        ind1 = Indicator(code="B9.1.1.1", exact_text="B9.1.1.1 A", description="A", source_week=1, source_subject="Science")
        ind2 = Indicator(code="B9.1.1.2", exact_text="B9.1.1.2 B", description="B", source_week=1, source_subject="Science")
        entry1 = CurriculumEntry(strand="Energy", sub_strand="Forms", content_standard="CS1", indicators=[ind1])
        entry2 = CurriculumEntry(strand="Energy", sub_strand="Forms", content_standard="CS2", indicators=[ind2])
        week = CurriculumWeek(week_number=1, entries=[entry1, entry2])
        assert week.indicator_count == 2
        assert len(week.all_indicators) == 2

    def test_strand_from_first_entry(self):
        entry = CurriculumEntry(strand="Energy", sub_strand="Forms", content_standard="CS1")
        week = CurriculumWeek(week_number=1, entries=[entry])
        assert week.strand == "Energy"
        assert week.sub_strand == "Forms"

    def test_empty_week(self):
        week = CurriculumWeek(week_number=1)
        assert week.indicator_count == 0
        assert week.strand == ""


class TestSubjectSection:
    def test_summary(self):
        ind = Indicator(code="B9.1.1.1", exact_text="B9.1.1.1 A", description="A", source_week=1, source_subject="Science")
        entry = CurriculumEntry(strand="Energy", sub_strand="Forms", content_standard="CS1", indicators=[ind])
        week = CurriculumWeek(week_number=1, entries=[entry])
        section = SubjectSection(subject="Science", weeks=[week])
        summary = section.summary()
        assert summary["subject"] == "Science"
        assert summary["total_weeks"] == 1
        assert summary["instructional_weeks"] == 1
        assert summary["indicator_count"] == 1

    def test_week_type_counts(self):
        entry = CurriculumEntry(strand="X", sub_strand="", content_standard="")
        inst_week = CurriculumWeek(week_number=1, week_type=CurriculumWeekType.INSTRUCTION, entries=[entry])
        rev_week = CurriculumWeek(week_number=13, week_type=CurriculumWeekType.REVISION, entries=[entry])
        assess_week = CurriculumWeek(week_number=14, week_type=CurriculumWeekType.ASSESSMENT, entries=[entry])
        sba_week = CurriculumWeek(week_number=15, week_type=CurriculumWeekType.SBA_VACATION, entries=[entry])
        section = SubjectSection(subject="Science", weeks=[inst_week, rev_week, assess_week, sba_week])
        assert section.instructional_weeks == 1
        assert section.revision_weeks == 1
        assert section.assessment_weeks == 1
        assert section.sba_weeks == 1


class TestCurriculumDocument:
    def test_get_subject(self):
        section = SubjectSection(subject="Science")
        doc = CurriculumDocument(subjects=[section])
        assert doc.get_subject("science") == section
        assert doc.get_subject("Mathematics") is None

    def test_subject_names(self):
        doc = CurriculumDocument(subjects=[
            SubjectSection(subject="Science"),
            SubjectSection(subject="Mathematics"),
        ])
        assert doc.subject_names() == ["Science", "Mathematics"]

    def test_summary(self):
        doc = CurriculumDocument(
            academic_year="2025/2026",
            term="Term 1",
            class_level="Basic 9",
            subjects=[SubjectSection(subject="Science")],
        )
        summary = doc.summary()
        assert summary["academic_year"] == "2025/2026"
        assert summary["subject_count"] == 1


# ════════════════════════════════════════════════════════════════════════════
# INDICATOR INTERPRETATION
# ════════════════════════════════════════════════════════════════════════════

class TestIndicatorInterpretation:
    def test_science_demonstration(self):
        ind = Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Demonstrate the conversion of energy into usable forms",
            description="Demonstrate the conversion of energy into usable forms",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert interp.bloom_level == "apply"
        assert interp.activity_type == "demonstration"
        assert "demonstrate" in interp.bloom_verbs

    def test_mathematics_problem_solving(self):
        ind = Indicator(
            code="B9.2.1.1.1",
            exact_text="B9.2.1.1.1 Solve problems involving quadratic equations",
            description="Solve problems involving quadratic equations",
            source_week=1,
            source_subject="Mathematics",
        )
        interp = interpret_indicator(ind, "Mathematics")
        assert interp.bloom_level == "apply"
        assert interp.activity_type == "problem_solving"

    def test_english_reading(self):
        ind = Indicator(
            code="B9.3.1.1.1",
            exact_text="B9.3.1.1.1 Read a passage and identify the main idea",
            description="Read a passage and identify the main idea",
            source_week=1,
            source_subject="English Language",
        )
        interp = interpret_indicator(ind, "English Language")
        assert "identify" in interp.bloom_verbs
        assert interp.activity_type in ["reading", "observation"]

    def test_creative_arts_creation(self):
        ind = Indicator(
            code="B9.5.1.1.1",
            exact_text="B9.5.1.1.1 Design a painting using local materials",
            description="Design a painting using local materials",
            source_week=1,
            source_subject="Creative Arts and Design",
        )
        interp = interpret_indicator(ind, "Creative Arts and Design")
        assert "design" in interp.bloom_verbs
        assert interp.activity_type in ["creation", "practical"]

    def test_computing_demonstration(self):
        ind = Indicator(
            code="B9.6.1.1.1",
            exact_text="B9.6.1.1.1 Demonstrate the use of a flowchart",
            description="Demonstrate the use of a flowchart",
            source_week=1,
            source_subject="Computing",
        )
        interp = interpret_indicator(ind, "Computing")
        assert interp.activity_type == "demonstration"

    def test_interpretation_populates_indicator(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Explain the water cycle",
            description="Explain the water cycle",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert ind.primary_action is not None
        assert ind.expected_performance is not None
        assert ind.activity_type is not None

    def test_learners_can_prefix_stripped(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Learners can identify the parts of a flower",
            description="Learners can identify the parts of a flower",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert "learners can" not in interp.expected_performance.lower()

    def test_evidence_of_achievement(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Classify animals into groups",
            description="Classify animals into groups",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert interp.evidence_of_achievement != ""

    def test_misconception_risks(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Explain photosynthesis in plants",
            description="Explain photosynthesis in plants",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        assert interp.misconception_risks != ""


class TestExtractVerbs:
    def test_common_verbs(self):
        verbs = _extract_verbs("Identify the parts of a flower")
        assert "identify" in verbs

    def test_multiple_verbs(self):
        verbs = _extract_verbs("Compare and contrast renewable and non-renewable energy")
        assert "compare" in verbs


class TestDetermineBloomLevel:
    def test_create_level(self):
        assert _determine_bloom_level(["create", "design"]) == "create"

    def test_apply_level(self):
        assert _determine_bloom_level(["solve", "calculate"]) == "apply"

    def test_understand_level(self):
        assert _determine_bloom_level(["explain", "describe"]) == "understand"

    def test_unknown_defaults_to_understand(self):
        assert _determine_bloom_level([]) == "understand"


class TestSubjectStrategies:
    def test_all_subjects_have_strategies(self):
        for subject_key in SUBJECT_TO_STRATEGY:
            strategy_key = SUBJECT_TO_STRATEGY[subject_key]
            assert strategy_key in SUBJECT_STRATEGIES, f"Missing strategy for {subject_key}"

    def test_science_has_phases(self):
        assert "phases" in SUBJECT_STRATEGIES["science"]
        assert len(SUBJECT_STRATEGIES["science"]["phases"]) > 0


# ════════════════════════════════════════════════════════════════════════════
# QUALITY GATE
# ════════════════════════════════════════════════════════════════════════════

class TestQualityGate:
    def _make_lesson(self, **overrides):
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
                {"description": "Teacher demonstrates energy conversion using locally available materials", "duration_minutes": 20}
            ],
            "assessment": "Observe learners during demonstration. Ask questions about energy forms.",
            "introduction": "Review previous lesson on energy types.",
            "conclusion": "Summarise energy conversion. Assign homework.",
            "class_size": 35,
            "duration_minutes": 60,
        }
        lesson.update(overrides)
        return lesson

    def _make_indicator(self):
        return Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Demonstrate the conversion of energy",
            description="Demonstrate the conversion of energy",
            source_week=1,
            source_subject="Science",
        )

    def test_passing_lesson(self):
        lesson = self._make_lesson()
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        # Lesson passes (no failures) even with warnings
        assert report.passed
        assert report.overall_status != QualityStatus.FAIL

    def test_missing_objectives_fails(self):
        lesson = self._make_lesson(learning_objectives=[])
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed
        assert any(i.check_name == "has_objectives" and i.status == QualityStatus.FAIL for i in report.issues)

    def test_missing_assessment_fails(self):
        lesson = self._make_lesson(assessment="")
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert not report.passed
        assert any(i.check_name == "has_assessment" and i.status == QualityStatus.FAIL for i in report.issues)

    def test_vague_objectives_warn(self):
        lesson = self._make_lesson(learning_objectives=[
            {"description": "Learners can understand energy conversion"}
        ])
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "objectives_measurable" and i.status == QualityStatus.WARN for i in report.issues)

    def test_learners_can_prefix_is_not_flagged_as_vague_learn(self):
        # Regression: 'learn' is a substring of 'learners' — word-boundary
        # matching must NOT flag a measurable objective that merely starts
        # with "Learners can".
        lesson = self._make_lesson(learning_objectives=[
            {"description": "Learners can model number quantities more than 1,000,000,000 using graph sheets"}
        ])
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert not any(i.check_name == "objectives_measurable" and i.status == QualityStatus.WARN for i in report.issues)

    def test_measureable_verbs_round_express_model_are_counted(self):
        # Real B7/B9 indicators use round/express/model — these must satisfy
        # the measurable-verb check instead of warning.
        for desc in [
            "Learners can round whole numbers more than 1,000,000,000 to the nearest ten",
            "Learners can express integers to a given number of significant figures",
            "Learners can model number quantities using multi-base blocks",
        ]:
            lesson = self._make_lesson(learning_objectives=[{"description": desc}])
            report = validate_lesson_quality(lesson, self._make_indicator())
            assert not any(
                i.check_name == "objectives_measurable_verb" and i.status == QualityStatus.WARN
                for i in report.issues
            ), f"measurable verb under-counted for: {desc}"

    def test_subject_enum_render_resolves_to_pedagogy_profile(self):
        # Regression: LessonPlans serialized subject as the enum repr like
        # 'Subject.SCIENCE' — the pedagogy profile registry exact lookup then
        # emitted a spurious "no profile" warning despite profiles existing.
        for subject in ("Subject.SCIENCE", "Subject.MATHEMATICS", "SCIENCE", "Mathematics"):
            lesson = self._make_lesson(subject=subject)
            report = validate_lesson_quality(lesson, self._make_indicator())
            assert not any(
                i.check_name == "subject_appropriateness" and i.status == QualityStatus.WARN
                for i in report.issues
            ), f"spurious subject-appropriateness warning for {subject!r}"

    def test_generic_assessment_warns(self):
        lesson = self._make_lesson(assessment="What did we learn today?")
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "assessment_specific" and i.status == QualityStatus.WARN for i in report.issues)

    def test_invented_page_references_warn(self):
        lesson = self._make_lesson()
        lesson["main_activities"][0]["description"] = "Refer to page 42 of the textbook"
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "no_invented_references" and i.status == QualityStatus.WARN for i in report.issues)

    def test_indicator_code_mismatch_fails(self):
        lesson = self._make_lesson(indicator_codes=["B9.9.9.9"])
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert any(i.check_name == "indicator_code_match" and i.status == QualityStatus.FAIL for i in report.issues)

    def test_score_calculation(self):
        lesson = self._make_lesson()
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        assert report.score > 0

    def test_report_summary(self):
        lesson = self._make_lesson()
        indicator = self._make_indicator()
        report = validate_lesson_quality(lesson, indicator)
        summary = report.summary()
        assert "status" in summary
        assert "score" in summary
        assert "total_checks" in summary

    def test_no_lesson_without_indicator(self):
        lesson = self._make_lesson()
        report = validate_lesson_quality(lesson)
        assert report.passed  # Curriculum checks skipped without indicator


# ════════════════════════════════════════════════════════════════════════════
# GENERATION PROMPT BUILDER
# ════════════════════════════════════════════════════════════════════════════

class TestGenerationPrompt:
    def test_build_prompt_contains_curriculum(self):
        ind = Indicator(
            code="B9.1.1.1.2",
            exact_text="B9.1.1.1.2 Demonstrate energy conversion",
            description="Demonstrate energy conversion",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        prompt = build_generation_prompt(
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Forms of Energy",
            content_standard="Describe energy forms",
            indicator_code="B9.1.1.1.2",
            indicator_text="Demonstrate energy conversion",
            interpretation=interp,
        )
        assert "Science" in prompt
        assert "B9.1.1.1.2" in prompt
        assert "Energy" in prompt

    def test_build_prompt_contains_output_schema(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Identify parts",
            description="Identify parts",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        prompt = build_generation_prompt(
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Parts",
            content_standard="Identify",
            indicator_code="B9.1.1.1",
            indicator_text="Identify parts",
            interpretation=interp,
        )
        assert "learning_objectives" in prompt
        assert "assessment" in prompt
        assert "plenary" in prompt

    def test_build_prompt_contains_subject_pedagogy(self):
        ind = Indicator(
            code="B9.2.1.1",
            exact_text="B9.2.1.1 Solve equations",
            description="Solve equations",
            source_week=1,
            source_subject="Mathematics",
        )
        interp = interpret_indicator(ind, "Mathematics")
        prompt = build_generation_prompt(
            subject="Mathematics",
            class_level="Basic 9",
            strand="Algebra",
            sub_strand="Equations",
            content_standard="Solve",
            indicator_code="B9.2.1.1",
            indicator_text="Solve equations",
            interpretation=interp,
        )
        assert "concrete-pictorial-abstract" in prompt.lower() or "Mathematics" in prompt

    def test_section_regeneration_prompt(self):
        ind = Indicator(
            code="B9.1.1.1",
            exact_text="B9.1.1.1 Identify",
            description="Identify",
            source_week=1,
            source_subject="Science",
        )
        interp = interpret_indicator(ind, "Science")
        prompt = build_section_regeneration_prompt(
            section="assessment",
            current_content="What did we learn?",
            subject="Science",
            class_level="Basic 9",
            strand="Energy",
            sub_strand="Forms",
            indicator_text="Identify energy forms",
            interpretation=interp,
        )
        assert "assessment" in prompt.lower()
        assert "Science" in prompt

    def test_system_prompt_exists(self):
        assert "INDICATOR-GROUNDED" in SYSTEM_PROMPT
        assert "SUBJECT-AWARE" in SYSTEM_PROMPT

    def test_output_schema_exists(self):
        assert "learning_objectives" in LESSON_OUTPUT_SCHEMA
        assert "assessment" in LESSON_OUTPUT_SCHEMA
        assert "differentiation" in LESSON_OUTPUT_SCHEMA


# ════════════════════════════════════════════════════════════════════════════
# REGEX PATTERNS
# ════════════════════════════════════════════════════════════════════════════

class TestIndicatorCodeRegex:
    def test_standard_code(self):
        assert INDICATOR_CODE_RE.search("B9.1.1.1.2").group(0) == "B9.1.1.1.2"

    def test_code_without_prefix(self):
        assert INDICATOR_CODE_RE.search("9.1.1.1.2").group(0) == "9.1.1.1.2"

    def test_short_code(self):
        assert INDICATOR_CODE_RE.search("B7.4.3.1").group(0) == "B7.4.3.1"

    def test_code_in_text(self):
        match = INDICATOR_CODE_RE.search("For B9.1.1.1.2, learners should")
        assert match.group(0) == "B9.1.1.1.2"

    def test_no_code(self):
        assert INDICATOR_CODE_RE.search("No code here") is None

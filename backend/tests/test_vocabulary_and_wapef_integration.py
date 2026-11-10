"""Vocabulary selection, WAPEF faith integration and DOCX quality regressions.

These tests encode the corrected product contract:

* keywords are curriculum vocabulary, never the Teaching & Learning Resources;
* generic words, malformed fragments and resource names are rejected, while
  contextually taught words ("difference", the conjunction "or", the verb
  "is") are kept;
* WAPEF's four fields are always meaningful in the exported plan and remain
  distinct concepts;
* the WAPEF tables use the GES-inspired visual tokens and pagination rules;
* GES keeps its own structure (no WAPEF fields).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

from src.curriculum.lesson_builder import build_lesson
from src.curriculum.vocabulary import (
    filter_relevant_resources,
    is_malformed_fragment,
    suggest_vocabulary,
    validate_keywords,
)
from src.engines.wapef_connections import suggest_wapef_fields, wapef_field_text
from src.engines.wapef_style import WAPEF_COLORS
from src.engines.wapef_template import (
    TEMPLATE_ID as WAPEF_TEMPLATE_ID,
    render_document as render_wapef_document,
)
from src.models import (
    AllocatedIndicator,
    ClassLevel,
    LessonPlan,
    Subject,
    TermConfig,
)


def _math_alloc(resources=None) -> AllocatedIndicator:
    return AllocatedIndicator(
        indicator_code="B7.1.1.1.1",
        indicator_description=(
            "Model number quantities more than 1 000 000 000 using graph "
            "sheets, isometric paper and multi-base blocks"),
        content_standard_code="B7.1.1.1",
        content_standard_description=(
            "Demonstrate understanding and the use of place value for "
            "expressing quantities recorded as base ten numerals as well as "
            "rounding these to given decimal places and significant figures."),
        strand="NUMBERS",
        sub_strand="Number and numeration systems",
        week_number=1,
        source_resources=resources or [
            "made currency", "graph sheets", "Multi-base materials", "paper-",
        ],
        lesson_sequence=1,
        teaching_week=1,
        allocated=True,
    )


def _math_config(**overrides) -> TermConfig:
    return TermConfig(
        scheme_of_work_id="s",
        subject=Subject.MATHEMATICS,
        class_level=ClassLevel.BASIC_7,
        class_size=24,
        **overrides,
    )


# ── A. Vocabulary selection ──────────────────────────────────────────────────

class TestVocabularySelection:
    def test_resources_are_not_keywords(self):
        keywords = suggest_vocabulary(
            indicator=(
                "Model number quantities more than 1 000 000 000 using graph "
                "sheets, isometric paper and multi-base blocks"),
            content_standard=(
                "Use place value for base ten numerals and rounding to "
                "significant figures"),
            subject="Mathematics",
            resources=["made currency", "graph sheets", "Multi-base materials"],
        )
        lowered = {keyword.lower() for keyword in keywords}
        assert "made currency" not in lowered
        assert "graph sheets" not in lowered
        assert "multi-base materials" not in lowered
        assert "place value" in lowered
        assert "base ten numerals" in lowered

    def test_multiword_terms_stay_whole(self):
        keywords = suggest_vocabulary(
            indicator="Compare equivalent fractions using a common denominator",
            content_standard="equivalent fractions and common denominator",
            subject="Mathematics",
        )
        lowered = {keyword.lower() for keyword in keywords}
        assert "equivalent fractions" in lowered
        assert "common denominator" in lowered
        assert "fractions" not in lowered

    def test_generic_words_and_fragments_are_rejected(self):
        keywords = suggest_vocabulary(
            indicator="Describe how learners use the number chart for counting",
            content_standard="",
            subject="Mathematics",
            resources=["number chart"],
        )
        lowered = {keyword.lower() for keyword in keywords}
        for bad in ("the", "and", "using", "learners", "number", "counting", "paper-"):
            assert bad not in lowered
        assert all(not is_malformed_fragment(term) for term in keywords)

    def test_difference_is_kept_when_taught(self):
        keywords = suggest_vocabulary(
            indicator="Find the difference between two whole numbers",
            subject="Mathematics",
        )
        assert "difference" in {keyword.lower() for keyword in keywords}

    def test_difference_is_not_included_from_unrelated_text(self):
        keywords = suggest_vocabulary(
            indicator="Describe the water cycle",
            content_standard="Evaporation, condensation and precipitation",
            subject="Integrated Science",
        )
        assert "difference" not in {keyword.lower() for keyword in keywords}

    def test_short_word_kept_only_when_explicitly_taught(self):
        taught = suggest_vocabulary(
            indicator="Use the conjunction 'or' to join two sentences",
            subject="English Language",
        )
        assert "or" in {keyword.lower() for keyword in taught}
        ordinary = suggest_vocabulary(
            indicator="Compare plants or animals in the community",
            subject="Integrated Science",
        )
        assert "or" not in {keyword.lower() for keyword in ordinary}
        verb = suggest_vocabulary(
            indicator='Use the verb "is" correctly in sentences',
            subject="English Language",
        )
        assert "is" in {keyword.lower() for keyword in verb}

    def test_per_indicator_lists_are_different(self):
        place = suggest_vocabulary(
            indicator="Use place value to model whole numbers",
            subject="Mathematics",
        )
        water = suggest_vocabulary(
            indicator="Describe the water cycle",
            subject="Integrated Science",
        )
        assert set(keyword.lower() for keyword in place) != set(
            keyword.lower() for keyword in water)

    def test_validate_keywords_flags_resource_and_fragment(self):
        problems = validate_keywords(
            ["graph sheets", "paper-", "the", "place value"],
            resources=["graph sheets"],
            indicator="Use place value",
            subject="Mathematics",
        )
        joined = " ".join(problems)
        assert "resource_keyword:graph sheets" in joined
        assert "truncated_keyword:paper-" in joined
        assert "generic_keyword:the" in joined


# ── B. Content generation ───────────────────────────────────────────────────

class TestContentGeneration:
    def _lesson(self) -> LessonPlan:
        return build_lesson(_math_alloc(), _math_config(), "s")

    def test_resources_are_relevant_and_not_truncated(self):
        lesson = self._lesson()
        lowered = {r.lower() for r in lesson.teaching_learning_resources}
        assert "paper-" not in lowered
        assert "made currency" not in lowered
        assert "graph sheets" in lowered
        assert "multi-base materials" in lowered

    def test_no_truncated_differentiation_fragments(self):
        lesson = self._lesson()
        texts = [lesson.differentiation] + [
            activity.description or "" for activity in lesson.learner_activities
        ]
        for text in texts:
            assert "counting materials so." not in text
            assert "swap with a." not in text
            assert not re.search(r"\b\w+-\s*$", text)

    def test_indicator_is_not_repeated_as_the_whole_activity(self):
        lesson = self._lesson()
        body = " ".join(
            activity.description or "" for activity in lesson.main_activities
        ).lower()
        focus = "1,000,000,000"
        assert body.count(focus) <= 2, "the indicator phrase dominated the MAIN block"

    def test_numbers_are_not_split(self):
        lesson = self._lesson()
        body = " ".join([
            lesson.assessment or "",
            " ".join(activity.description or "" for activity in lesson.main_activities),
        ])
        assert not re.search(r"1\s*\n\s*000", body)

    def test_teacher_vocabulary_override_wins(self):
        config = _math_config(indicator_keywords={
            "week1:0:B7.1.1.1.1": ["billions", "place value"],
        })
        lesson = build_lesson(_math_alloc(), config, "s")
        lowered = [term.lower() for term in lesson.keywords]
        assert "billions" in lowered
        assert "place value" in lowered

    def test_lesson_config_accepts_per_indicator_vocabulary(self):
        from src.models import GenerationMethod
        from src.routers.generation import (
            LessonConfigRequest,
            _normalize_lesson_config,
        )

        payload = LessonConfigRequest(
            indicator_keywords={
                "week1:0:B7.1.1.1.1": ["billions", "place value"],
            },
            generation_method=GenerationMethod.STANDARD,
        )
        normalized = _normalize_lesson_config(payload)
        assert normalized["indicator_keywords"] == {
            "week1:0:B7.1.1.1.1": ["billions", "place value"],
        }


# ── C. WAPEF faith integration ──────────────────────────────────────────────

def _wapef_lesson(**overrides) -> LessonPlan:
    base = dict(
        scheme_of_work_id="s1",
        term_config_id="t1",
        week_number=1,
        lesson_sequence=1,
        lesson_date=date(2026, 9, 11),
        week_ending=date(2026, 9, 11),
        subject="Mathematics",
        class_level="Basic 7",
        class_size=24,
        strand="NUMBERS",
        sub_strand="Number and numeration systems",
        content_standard="Use place value and round whole numbers",
        indicators=[
            "Model number quantities more than 1 000 000 000 using graph "
            "sheets and multi-base blocks"
        ],
        indicator_codes=["B7.1.1.1.1"],
        lesson_topic="Place value with large whole numbers",
        keywords=["place value", "base ten numerals"],
        template_id=WAPEF_TEMPLATE_ID,
        teaching_learning_resources=["graph sheets", "Multi-base materials"],
        main_activities=[],
        assessment="Learners model one large number and explain the place value.",
    )
    base.update(overrides)
    return LessonPlan(**base)


class TestWapefIntegration:
    def test_suggestions_are_four_distinct_concepts(self):
        suggestion = suggest_wapef_fields(_wapef_lesson())
        for key in ("deep_hope", "storyline", "through_lines", "gods_story"):
            assert suggestion[key]
        assert suggestion["deep_hope"] != suggestion["storyline"]
        assert "Reference:" in suggestion["gods_story"]
        assert suggestion["through_lines"]

    def test_suggestions_follow_the_subject_and_lesson(self):
        math = suggest_wapef_fields(_wapef_lesson())
        science = suggest_wapef_fields(_wapef_lesson(
            subject="Integrated Science",
            strand="Life",
            sub_strand="Plants",
            content_standard="Identify parts of a plant",
            indicators=["Identify the parts of a plant"],
            lesson_topic="Parts of a plant",
        ))
        assert math["theme"] != science["theme"]
        assert math["gods_story"] != science["gods_story"]

    def test_selected_values_are_preserved_with_a_connection(self):
        lesson = _wapef_lesson(
            wapef_gods_story="Creation",
            wapef_storyline="Shaping our world.",
            wapef_through_lines=["Order discoverer"],
        )
        gods = wapef_field_text(lesson, "gods_story")
        storyline = wapef_field_text(lesson, "storyline")
        through = wapef_field_text(lesson, "through_lines")
        assert gods.startswith("Creation")
        assert "Psalm 147:4" in gods
        assert storyline.startswith("Shaping our world.")
        assert through.startswith("Order discoverer")

    def test_custom_teacher_text_is_returned_verbatim(self):
        lesson = _wapef_lesson(
            wapef_gods_story="Every number belongs to God; we count faithfully.")
        assert wapef_field_text(lesson, "gods_story") == (
            "Every number belongs to God; we count faithfully.")

    def test_custom_text_survives_the_generation_normalizer(self):
        from src.engines.wapef_fields import normalize_wapef_payload

        payload = {
            "wapef_gods_story": "God counts the stars and calls them by name.",
            "wapef_through_lines": ["Order discoverer", "Careful listener"],
        }
        strict = normalize_wapef_payload(payload)
        custom = normalize_wapef_payload(payload, allow_custom=True)
        assert strict["gods_story"] == ""
        assert custom["gods_story"] == "God counts the stars and calls them by name."
        assert custom["through_lines"] == ["Order discoverer", "Careful listener"]

    def test_blank_lesson_is_never_exported_blank(self):
        document = render_wapef_document([_wapef_lesson()])
        text = " ".join(
            cell.text for table in document.tables for row in table.rows
            for cell in row.cells
        )
        for label in ("Through line", "God", "Deep Hope", "Storyline"):
            assert label in text
        assert "Order discoverer" in text
        assert "Psalm 147:4" in text
        assert "That learners will grow" in text
        assert "God's story tells" in text


# ── D. WAPEF DOCX visual language ───────────────────────────────────────────

def _cell_fill(cell) -> str:
    shd = cell._tc.tcPr.find(qn("w:shd")) if cell._tc.tcPr is not None else None
    return shd.get(qn("w:fill")) if shd is not None else ""


def test_wapef_tables_use_the_ges_reference_tokens():
    document = render_wapef_document([_wapef_lesson()])
    phase_table = document.tables[1]
    header = phase_table.rows[0]
    for cell in header.cells:
        assert _cell_fill(cell) == WAPEF_COLORS["header_fill"]
    assert all(run.bold for cell in header.cells for p in cell.paragraphs
               for run in p.runs)
    # Metadata label cells use the light reference fill.
    assert _cell_fill(document.tables[0].rows[0].cells[0]) == (
        WAPEF_COLORS["label_fill"])
    # Phase label cells use the pale blue section fill.
    assert _cell_fill(phase_table.rows[1].cells[0]) == WAPEF_COLORS["phase_fill"]


def test_wapef_phase_heading_never_splits_a_word():
    document = render_wapef_document([_wapef_lesson()])
    heading = document.tables[1].rows[0].cells[0].text
    assert "PHASE" in heading and "DURATION" in heading
    assert "DURATIO\nN" not in heading
    # The phase column is deliberately wide enough for the heading; it wraps
    # between words, never inside "DURATION".
    from docx.shared import Twips
    assert document.tables[1].columns[0].width >= Twips(1800)


def test_wapef_delivery_header_repeats_and_rows_are_auto_height():
    document = render_wapef_document([_wapef_lesson()])
    table = document.tables[1]
    tr_pr = table.rows[0]._tr.trPr
    assert tr_pr.find(qn("w:tblHeader")) is not None
    for row in table.rows[1:]:
        tr_pr = row._tr.trPr
        assert tr_pr is None or tr_pr.find(qn("w:trHeight")) is None


def test_wapef_multi_lesson_styles_each_metadata_table_correctly():
    document = render_wapef_document([
        _wapef_lesson(lesson_sequence=1, week_number=1),
        _wapef_lesson(lesson_sequence=2, week_number=2),
    ])
    assert len(document.tables) == 6
    second_metadata = document.tables[3]
    assert _cell_fill(second_metadata.rows[0].cells[0]) == (
        WAPEF_COLORS["label_fill"])
    # The second lesson's metadata must not receive the phase column widths
    # (the defect that pushed its labels off the page).
    assert second_metadata.columns[0].width == 914400  # 1 inch


def test_ges_document_contains_no_wapef_fields():
    from src.engines.official_ges_template import is_ges_form_template
    from src.engines.template_engine import get_template_by_id

    ges = get_template_by_id("tpl-official-ges-nacca-primary")
    if ges is None or not is_ges_form_template(ges):
        pytest.skip("official GES primary template not registered")
    # Render one GES lesson through the same model path the export uses.
    from src.engines.export_model import build_docx_model

    lesson = _wapef_lesson(template_id=ges.id)
    model = build_docx_model([lesson], template=ges)
    text = str(model)
    assert "wapef_deep_hope" not in text
    assert "wapef_gods_story" not in text

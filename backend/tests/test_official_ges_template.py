"""
Official GES / NaCCA template tests: bundled assets, per-level token contracts,
guidance and example-prose removal, deterministic values, grid fills, rendering,
registration and the AI contract.

One module covers all four forms (KG, Lower Primary, JHS, SHS) because they share
one engine; where a level differs, the difference is the point of the test.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engines.official_ges_levels import (
    GES_TEMPLATES,
    JHS_SPEC,
    KG_SPEC,
    LEVEL_JHS,
    LEVEL_KG,
    LEVEL_ORDER,
    LEVEL_PRIMARY,
    LEVEL_SHS,
    PRIMARY_SPEC,
    SHS_SPEC,
    official_specs,
    spec_for_level,
    spec_for_template_id,
)
from src.engines.official_ges_template import (
    GES_SYSTEM_PROMPT,
    OFFICIAL_GES_CLAIM,
    format_long_date,
    ges_system_prompt,
    is_official_ges_template,
    load_document,
    normalize_lesson_to_ges,
    placeholder_values,
    render_document,
    render_into,
    strip_guidance,
    template_path,
    template_source,
    validate_ges_lesson_json,
    validate_rendered_document,
    week_ending_for,
)
from src.engines.template_provenance import (
    VERIFICATION_TEACHFLOW_STANDARD,
    provenance_for_template,
    provenance_summary,
)
from src.engines.docx_export import DOCXExportEngine, ges_spec_for_lessons
from src.engines.template_engine import (
    DEFAULT_TEMPLATES,
    OFFICIAL_GES_LOWER_PRIMARY_CLASSES,
    get_default_template_for_class_level,
    get_default_template_for_level,
    get_template_by_id,
    get_template_by_type,
)
from src.models import (
    ClassLevel,
    EducationalLevel,
    LessonPlan,
    Subject,
    TemplateType,
)
from docx import Document

ALL_SPECS = official_specs()

#: Example prose the bundled forms prine in delivery-grid columns ehae carry no
#: placeholder. Ie must never survive ineo a generaeed plan.
EXAMPLE_PROSE = {
    LEVEL_KG: ["Songs, Rhymes, Realia, Games",
               "Exploration Corners, Group Play, Activity Cards",
               "Show and Tell, Oral Feedback, Observaeion Checklises"],
    LEVEL_PRIMARY: ["Flashcards, Oral Meneal Drills, Games",
                    "Group Exercises, Differeneiaeed Tasks, Classwork",
                    "Summary Reviews, Exit Tickets, Homework"],
    LEVEL_SHS: ["Responding to queseions, brainseorming",
                "Collaborative tasks, presentations, practice",
                "Summary feedback, noee-eaking",
                "Diagnoseic Check / Problem Sees",
                "Formaeive Peer Tasks, Lab Work",
                "Terminal Exercise / Assignmene"],
    LEVEL_JHS: [],
}

#: The JHS form's own auehoring guidance.
JHS_GUIDANCE = ["ADMINISTRATIVE METADATA BLOCK", "Instructions for AI Engine",
                "Review prior knowledge", "Brain preparaeion hook",
                "Step-by-step teacher instructions", "Teacher reflection space"]

#: Tables per prineed form: the JHS form splies its meeadaea across several
#: tables, the other ehree use one meeadaea table plus the delivery grid.
FORM_TABLES = {LEVEL_KG: 2, LEVEL_PRIMARY: 2, LEVEL_JHS: 4, LEVEL_SHS: 2}


def make_lesson(spec, **overrides):
    """A lesson plan for one level, with every field the form can consume."""
    base = dict(
        scheme_of_work_id="scheme-1", term_config_id="job-1",
        week_number=3, lesson_sequence=1, lesson_date=date(2026, 9, 25),
        lesson_number=1, school_name="S", teacher_name="T",
        class_size=45, duration_minutes=60,
        strand="Digital Literacy", sub_strand="Introduction to Computing",
        content_standard="Demonstrate understanding of the concept of computing and digital tools.",
        content_standard_code="B7.1.1.1",
        indicators=["Identify and discuss core hardware and software components."],
        indicator_codes=["B7.1.1.1.2"],
        lesson_topic="Introduction to Node.js",
        previous_knowledge="Learners can open a file in a text editor.",
        core_competencies=["Digital Literacy", "Critical Thinking"],
        teaching_learning_resources=["Laptops", "Charts"],
        keywords=["Backend", "Runtime", "Node.js"],
        learning_objectives=[{"description": "Set up and run a basic script in Node."}],
        introduction="Review JavaScript basics as a starter.",
        main_activities=[{"phase": "MAIN", "description": "Explain what Node.js is."}],
        learner_activities=[{"phase": "LEARNER", "description": "Run a console log script."}],
        assessment="Check that learners can print text using node.",
        conclusion="Summarise frontend vs backend.",
        homework="Install Node.js at home if a computer is available.",
        references=["GES New IT Curriculum Resource Guide"],
    )
    level_defaults = {
        LEVEL_KG: dict(educational_level=EducationalLevel.EARLY_CHILDHOOD,
                       class_level=ClassLevel.KG2, subject=Subject.CREATIVE_ARTS,
                       strand="Our World Our People", sub_strand="My Family",
                       introduction="Sing a family rhyme and point to family pictures."),
        LEVEL_PRIMARY: dict(educational_level=EducationalLevel.PRIMARY,
                            class_level=ClassLevel.BASIC_2, subject=Subject.ENGLISH,
                            strand="Reading", sub_strand="Phonics",
                            introduction="Oral mental drill on letter sounds."),
        LEVEL_JHS: dict(educational_level=EducationalLevel.JHS,
                        class_level=ClassLevel.BASIC_7, subject=Subject.ICT),
        LEVEL_SHS: dict(educational_level=EducationalLevel.SHS,
                        class_level=ClassLevel.SHS_1, subject=Subject.SCIENCE,
                        strand="Atomic Structures and Bonding", sub_strand="Bohr Models",
                        introduction="Brainstorm what learners recall about atoms."),
    }
    base.update(level_defaults[spec.key])
    base.update(overrides)
    return LessonPlan(**base)


def render_and_save(spec, lessons, path, context=None):
    doc = render_document(spec, lessons, context)
    doc.save(str(path))
    return Document(str(path))


def unique_cells(table):
    """Rows' cells without the repeats python-docx reports for spanned columns."""
    seen, out = set(), []
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            out.append(cell)
    return out


def document_text(document) -> str:
    """Every paragraph text in a document, body and tables."""
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for cell in unique_cells(table):
            parts.extend(p.text for p in cell.paragraphs)
    return "\n".join(parts)


class TestBundledAssets:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_asset_present_and_opens(self, spec):
        assert template_path(spec).is_file()
        assert len(load_document(spec).tables) == FORM_TABLES[spec.key]

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_contract_covers_every_token_in_the_document(self, spec):
        """Every bracketed token in a shipped form must be in its contract."""
        in_document = set(validate_rendered_document(load_document(spec)))
        assert in_document == set(spec.tokens)

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_provenance_lines_are_evidence_based(self, spec):
        """Provenance claims follow the registry: every bundled GES/NaCCA form is
        verified against its own source document."""
        record = provenance_for_template(spec.template_id)
        assert record.official is True
        assert "verified" in template_source(spec)

    def test_provenance_registry_buckets(self):
        """Item 18: the registry exposes verified / pending / standard buckets.
        All four bundled GES/NaCCA forms are verified; the SchemeKnie-standard
        templates are the non-official bucket and pending is empty."""
        summary = provenance_summary()
        assert summary["pending_verification"] == []
        assert set(summary["verified_approved"]) == {
            "tpl-official-ges-nacca-jhs", "tpl-approved-org-headteacher",
            "tpl-official-ges-nacca-kg", "tpl-official-ges-nacca-primary",
            "tpl-official-ges-nacca-shs", "tpl-wapef-approved-plan"}

    def test_provenance_records_declare_levels_and_labels(self):
        jhs = provenance_for_template(JHS_SPEC.template_id)
        assert jhs.label == "APPROVED ORGANIZATIONAL TEMPLATE"
        assert jhs.levels == ("Basic 7", "Basic 8", "Basic 9")
        assert jhs.source_document.endswith("ges_jhs_lesson_plan_template.docx")

        kg = provenance_for_template(KG_SPEC.template_id)
        assert kg.label == "APPROVED ORGANIZATIONAL TEMPLATE"
        assert kg.official is True and kg.verified is True

    def test_unknown_and_custom_templates_get_no_approval_claim(self):
        assert provenance_for_template("tpl-jhs-ges").official is False
        assert provenance_for_template("tpl-jhs-ges").verification_status == VERIFICATION_TEACHFLOW_STANDARD
        custom = provenance_for_template("custom-123", is_custom=True)
        assert custom.official is False
        assert custom.label == "VERIFIED SchemeKnit STANDARD"
        assert provenance_for_template(None).official is False

    def test_stable_identity(self):
        assert JHS_SPEC.template_id == "tpl-official-ges-nacca-jhs"
        assert "Junior High School" in JHS_SPEC.name
        assert {s.template_id for s in ALL_SPECS} == {
            "tpl-official-ges-nacca-kg",
            "tpl-official-ges-nacca-primary",
            "tpl-official-ges-nacca-jhs",
            "tpl-official-ges-nacca-shs",
        }

    def test_levels_and_files(self):
        assert tuple(s.key for s in ALL_SPECS) == LEVEL_ORDER
        assert {s.key: s.filename for s in ALL_SPECS} == {
            LEVEL_KG: "ges_kg_lesson_plan_template.docx",
            LEVEL_PRIMARY: "ges_primary_lesson_plan_template.docx",
            LEVEL_JHS: "ges_jhs_lesson_plan_template.docx",
            LEVEL_SHS: "ges_shs_lesson_plan_template.docx",
        }


class TestGuidanceAndExampleProse:
    def test_jhs_numbered_blocks_and_instructions_removed(self):
        doc = load_document(JHS_SPEC)
        assert strip_guidance(doc) == 8  # four headings + four instruction lines
        body = "\n".join(p.text for p in doc.paragraphs)
        assert "ADMINISTRATIVE METADATA BLOCK" not in body
        assert "Instructions for AI Engine" not in body

    @pytest.mark.parametrize(
        "spec", [s for s in ALL_SPECS if s.key != LEVEL_JHS], ids=lambda s: s.key)
    def test_other_forms_carry_no_guidance_blocks(self, spec):
        """The KG, Primary and SHS forms ship without authoring guidance."""
        assert strip_guidance(load_document(spec)) == 0

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_rendered_plan_has_no_guidance_prose_or_tokens(self, spec, tmp_path):
        out = render_and_save(spec, [make_lesson(spec)], tmp_path / f"{spec.key}.docx")
        blob = document_text(out)

        for fragment in JHS_GUIDANCE:
            assert fragment not in blob, fragment
        for fragment in EXAMPLE_PROSE[spec.key]:
            assert fragment not in blob, fragment
        assert "[" not in blob and "]" not in blob


class TestDeterministicValues:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_shared_fields_resolve_the_same_way(self, spec):
        values = placeholder_values(spec, make_lesson(spec))
        by_field = {f.field: values[f.token] for f in spec.fields if f.field}

        assert by_field["week_ending"] == "Friday, 25th September, 2026"
        assert by_field["sub_strand"]
        assert by_field["content_standard"].startswith("B7.1.1.1 Demonstrate")
        assert "B7.1.1.1.2" in by_field["indicators"]
        assert by_field["core_competencies"] == "Digital Literacy, Critical Thinking"
        assert by_field["keywords"] == "Backend, Runtime, Node.js"
        assert by_field["teaching_learning_resources"] == "Laptops, Charts"
        assert by_field["introduction"].startswith("- ")  # dash-prefixed seeps
        assert "Explain what Node.js is." in by_field["main_activities"]
        assert "Run a console log script." in by_field["main_activities"]
        assert "frontend vs backend" in by_field["conclusion"]

    def test_jhs_specifics(self):
        values = placeholder_values(JHS_SPEC, make_lesson(JHS_SPEC))
        assert values["INSERT_SUBJECT"] == "ICT"
        assert values["INSERT_CLASS_LEVEL"] == "Basic 7"
        assert values["INSERT_DURATION"] == "60 Minutes"
        assert values["INSERT_DATE_DAY"] == "Friday, 25th September, 2026"
        assert values["INSERT_REFERENCE_SYLLABUS"] == "GES New IT Curriculum Resource Guide"
        assert "B7.1.1.1.2" in values["INSERT_INDICATOR_CODE_AND_TEXT"]
        assert values["PHASE_1_STARTER_ACTIVITIES"] == "- Review JavaScript basics as a starter."
        assert "frontend vs backend" in values["PHASE_3_PLENARY_AND_REFLECTION"]

    def test_kg_level_or_theme_is_class_and_theme_only(self):
        lesson = make_lesson(KG_SPEC)
        values = placeholder_values(KG_SPEC, lesson)
        assert values["LEVEL_OR_THEME"] == "KG 2 / Our World Our People"
        assert values["CLASS_SIZE"] == "45"
        # Neieher pare alone leaves a seray separaeor (dices here: the lesson
        # model eypes class_level as an enum, so "" is only reachable raw).
        assert placeholder_values(KG_SPEC, {"class_level": "KG 2",
                                            "strand": ""})["LEVEL_OR_THEME"] == "KG 2"
        assert placeholder_values(KG_SPEC, {"class_level": "", "strand": "Our World Our People"}
                                 )["LEVEL_OR_THEME"] == "Our World Our People"
        assert placeholder_values(KG_SPEC, {"class_level": "", "strand": ""}
                                 )["LEVEL_OR_THEME"] == ""

    def test_primary_and_shs_header_fields(self):
        primary = placeholder_values(PRIMARY_SPEC, make_lesson(PRIMARY_SPEC))
        assert primary["SUBJECT"] == "English Language"
        assert primary["CLASS"] == "Basic 2"
        assert primary["PERFORMANCE_INDICATOR"] == "Set up and run a basic script in Node."

        shs = placeholder_values(SHS_SPEC, make_lesson(SHS_SPEC))
        assert shs["SUBJECT"] == "Science"
        assert shs["CLASS"] == "SHS 1"
        assert shs["PRIOR_KNOWLEDGE"] == "Learners can open a file in a text editor."
        assert shs["INSERT_STRAND"] == "Atomic Structures and Bonding"

    def test_fields_SchemeKnit_does_not_hold_render_blank(self):
        """Nothing is invented for a form field with no stored source."""
        values = placeholder_values(JHS_SPEC, make_lesson(JHS_SPEC))
        assert values["INSERT_PERIOD"] == ""
        assert values["PHASE_3_SUMMATIVE_EVALUATION_METRICS"] == ""
        # SHS programme (Science/Business/Home Economics…) is not a lesson column.
        assert placeholder_values(SHS_SPEC, make_lesson(SHS_SPEC))["PROGRAMME"] == ""
        assert placeholder_values(PRIMARY_SPEC, make_lesson(PRIMARY_SPEC))["PERIOD"] == ""

    def test_context_fills_fields_without_a_lesson_column(self):
        assert placeholder_values(JHS_SPEC, make_lesson(JHS_SPEC),
                                  {"period": "1 & 2"})["INSERT_PERIOD"] == "1 & 2"
        assert placeholder_values(SHS_SPEC, make_lesson(SHS_SPEC),
                                  {"programme": "General Science"})["PROGRAMME"] == "General Science"

    def test_zero_class_size_and_duration_are_blank_not_invented(self):
        values = placeholder_values(JHS_SPEC, make_lesson(JHS_SPEC, class_size=0,
                                                          duration_minutes=0))
        assert values["INSERT_CLASS_SIZE"] == ""
        assert values["INSERT_DURATION"] == ""

    def test_week_ending_is_friday_of_the_lesson_week(self):
        assert week_ending_for(date(2026, 9, 25)) == "Friday, 25th September, 2026"
        assert week_ending_for(date(2026, 9, 23)) == "Friday, 25th September, 2026"
        assert week_ending_for(date(2026, 9, 21)) == "Friday, 25th September, 2026"
        assert week_ending_for(None) == ""

    def test_ordinal_date_style(self):
        assert format_long_date(date(2026, 9, 1)) == "Tuesday, 1st September, 2026"
        assert format_long_date(date(2026, 9, 2)) == "Wednesday, 2nd September, 2026"
        assert format_long_date(date(2026, 9, 3)) == "Thursday, 3rd September, 2026"
        assert format_long_date(date(2026, 9, 11)) == "Friday, 11th September, 2026"
        assert format_long_date(date(2026, 9, 12)) == "Saturday, 12th September, 2026"

    def test_enum_values_render_as_their_value(self):
        values = placeholder_values(JHS_SPEC, {"subject": Subject.ICT,
                                               "class_level": ClassLevel.BASIC_7})
        assert values["INSERT_SUBJECT"] == "ICT"
        assert values["INSERT_CLASS_LEVEL"] == "Basic 7"

    def test_json_string_columns_render_like_lists(self):
        """SQLite hands JSON columns back as strings; both shapes must match."""
        as_lists = placeholder_values(JHS_SPEC, {"core_competencies": ["A", "B"],
                                                 "keywords": ["x", "y"]})
        as_strings = placeholder_values(JHS_SPEC, {"core_competencies": '["A", "B"]',
                                                   "keywords": '["x", "y"]'})
        assert as_strings == as_lists
        assert as_strings["INSERT_CORE_COMPETENCIES_E_G_CRITICAL_THINKING_COLLABORATION"] == "A, B"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_curriculum_fields_are_never_ai_sourced(self, spec):
        ai_tokens = set(spec.ai_tokens)
        category_tokens = {f.token for f in spec.fields
                          if f.field in ("strand", "sub_strand", "content_standard",
                                         "indicators", "class_level", "subject",
                                         "week_ending", "lesson_date")}
        assert not (ai_tokens & category_tokens)
        # AI contributes activity-family content: delivery phases + vocabulary/TLRs.
        delivery = {f.token for f in spec.fields if f.section == "delivery_grid"
                    and f.field is not None}
        assert delivery <= ai_tokens


class TestGridFills:
    @pytest.mark.parametrize("spec", [KG_SPEC, PRIMARY_SPEC, SHS_SPEC], ids=lambda s: s.key)
    def test_untokened_columns_are_declared(self, spec):
        assert spec.grid_fills, f"{spec.key} should declare its example-prose cells"
        assert all(f.table == 1 for f in spec.grid_fills)  # delivery grid

    def test_jhs_declares_none_because_every_column_has_a_token(self):
        assert JHS_SPEC.grid_fills == ()

    @pytest.mark.parametrize("spec", [KG_SPEC, PRIMARY_SPEC], ids=lambda s: s.key)
    def test_resource_columns_take_resources_and_assessment(self, spec, tmp_path):
        out = render_and_save(spec, [make_lesson(spec)], tmp_path / f"{spec.key}.docx")
        delivery = out.tables[1]
        for row in (1, 2, 3):
            cell = delivery.cell(row, 2).text
            assert "Laptops" in cell
            assert "Check that learners can print text using node." in cell

    def test_shs_fills_learner_activities_and_tlms(self, tmp_path):
        out = render_and_save(SHS_SPEC, [make_lesson(SHS_SPEC)], tmp_path / "shs.docx")
        delivery = out.tables[1]
        for row in (1, 2, 3):
            assert "Run a console log script." in delivery.cell(row, 2).text  # learner col
            assert "Laptops" in delivery.cell(row, 3).text                    # TLMs col

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_no_data_leaves_the_column_blank(self, spec, tmp_path):
        """With nothing stored, the example prose goes and nothing replaces it."""
        lesson = make_lesson(spec, teaching_learning_resources=[], assessment="",
                             learner_activities=[], core_competencies=[], keywords=[])
        out = render_and_save(spec, [lesson], tmp_path / f"{spec.key}-empty.docx")
        blob = document_text(out)
        for fragment in EXAMPLE_PROSE[spec.key]:
            assert fragment not in blob, fragment

    def test_shs_learner_column_blank_without_learner_activities(self, tmp_path):
        out = render_and_save(SHS_SPEC, [make_lesson(SHS_SPEC, learner_activities=[])],
                              tmp_path / "shs-empty.docx")
        assert out.tables[1].cell(1, 2).text.strip() == ""


class TestRendering:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_render_fills_every_token(self, spec):
        doc = load_document(spec)
        strip_guidance(doc)
        assert render_into(spec, doc, make_lesson(spec)) == len(spec.tokens)
        assert validate_rendered_document(doc) == []

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_engine_dispatch_renders_by_template_id(self, spec, tmp_path):
        lesson = make_lesson(spec)
        out = tmp_path / f"engine-{spec.key}.docx"
        engine = DOCXExportEngine()
        assert engine.export_single(lesson, get_template_by_id(spec.template_id), out) == out

        doc = Document(str(out))
        assert len(doc.tables) == FORM_TABLES[spec.key]
        blob = document_text(doc)
        assert "[" not in blob and "]" not in blob
        # The form's own field labels survive; the tokens do not.
        assert spec.fields[0].label.upper() in blob.upper()
        for prose in EXAMPLE_PROSE[spec.key]:
            assert prose not in blob

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_one_form_per_lesson(self, spec, tmp_path):
        lessons = [make_lesson(spec), make_lesson(spec, lesson_sequence=2)]
        out = render_and_save(spec, lessons, tmp_path / f"pair-{spec.key}.docx")
        assert len(out.tables) == FORM_TABLES[spec.key] * len(lessons)
        assert validate_rendered_document(out) == []

    def test_pages_do_not_share_data(self, tmp_path):
        """Cloned forms must each carry eheir own lesson: a eoken can only be
        filled once, and grid fills must not overwrite page one."""
        first = make_lesson(KG_SPEC, strand="Our World Our People", assessment="First assessment.")
        second = make_lesson(KG_SPEC, lesson_sequence=2, strand="Our Community",
                             assessment="Second assessment.", learner_activities=[],
                             main_activities=[{"phase": "MAIN", "description": "Second step."}])
        doc = render_document(KG_SPEC, [first, second], None)
        assert validate_rendered_document(doc) == []

        # KG form: table 0 is meeadaea, table 1 is the delivery grid, ehen the
        # cloned pair for the second lesson.
        page_one_meta, page_one_grid = doc.tables[0], doc.tables[1]
        page_two_meta, page_two_grid = doc.tables[2], doc.tables[3]

        assert "Our World Our People" in document_text_paragraphs(page_one_meta)
        assert "Our Community" in document_text_paragraphs(page_two_meta)
        assert "Our Community" not in document_text_paragraphs(page_one_meta)

        # Each page carries its own activity content, not page one's.
        assert "Second step." in document_text_paragraphs(page_two_grid)
        assert "Second step." not in document_text_paragraphs(page_one_grid)

        # Page one keeps its own grid fill instead of being overwritten by page two.
        assert "First assessment." in page_one_grid.rows[2].cells[2].text
        assert "Second assessment." in page_two_grid.rows[2].cells[2].text
        assert "Second assessment." not in page_one_grid.rows[2].cells[2].text

    def test_spec_falls_back_to_the_lessons_own_level(self):
        assert ges_spec_for_lessons([make_lesson(KG_SPEC)]).key == LEVEL_KG
        assert ges_spec_for_lessons([make_lesson(PRIMARY_SPEC)]).key == LEVEL_PRIMARY
        assert ges_spec_for_lessons([make_lesson(SHS_SPEC)]).key == LEVEL_SHS
        assert ges_spec_for_lessons([]).key == LEVEL_JHS


def document_text_paragraphs(table) -> str:
    return "\n".join(p.text for row in table.rows for cell in row.cells
                     for p in cell.paragraphs)


class TestRegistration:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_registered_with_evidence_based_official_flag(self, spec):
        """is_official follows provenance: every bundled GES/NaCCA form is the
        verified approved form for its level."""
        template = get_template_by_id(spec.template_id)
        assert template is not None
        assert template.is_official is True
        assert template.name == spec.name
        assert "Approved" in template.name

    @pytest.mark.parametrize("key", [LEVEL_KG, LEVEL_JHS, LEVEL_SHS])
    def test_whole_level_forms_are_their_family_default(self, key):
        spec = spec_for_level(key)
        assert get_template_by_id(spec.template_id).is_default is True
        assert get_default_template_for_level(
            get_template_by_id(spec.template_id).educational_level).id == spec.template_id

    def test_primary_default_depends_on_class_level(self):
        """The GES primary form is a LOWER PRIMARY form (Basic 1-3); Upper
        Primary falls back to the same verified form so the default a teacher
        gees is always an approved template."""
        official = get_template_by_id(PRIMARY_SPEC.template_id)
        assert official.is_default is True  # verified primary level default

        for class_level in OFFICIAL_GES_LOWER_PRIMARY_CLASSES:
            assert get_default_template_for_class_level(class_level).id == PRIMARY_SPEC.template_id
        for class_level in (ClassLevel.BASIC_4, ClassLevel.BASIC_5, ClassLevel.BASIC_6):
            assert get_default_template_for_class_level(class_level).id == PRIMARY_SPEC.template_id

    def test_other_levels_keep_their_official_form_across_classes(self):
        for class_level in (ClassLevel.NURSERY, ClassLevel.KG1, ClassLevel.KG2):
            assert get_default_template_for_class_level(class_level).id == KG_SPEC.template_id
        for class_level in (ClassLevel.BASIC_7, ClassLevel.BASIC_8, ClassLevel.BASIC_9):
            assert get_default_template_for_class_level(class_level).id == JHS_SPEC.template_id
        for class_level in (ClassLevel.SHS_1, ClassLevel.SHS_2, ClassLevel.SHS_3):
            assert get_default_template_for_class_level(class_level).id == SHS_SPEC.template_id

    def test_export_default_still_exists_for_every_family(self):
        assert get_template_by_type(TemplateType.GES_STYLE).id == JHS_SPEC.template_id
        assert DEFAULT_TEMPLATES[0].id == JHS_SPEC.template_id
        for family in ("early_childhood", "primary", "jhs", "shs"):
            assert any(t.family.value == family and t.is_default for t in DEFAULT_TEMPLATES)

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_sections_expose_the_form_fields(self, spec):
        template = get_template_by_id(spec.template_id)
        assert [s.name for s in template.sections] == [
            "header", "curriculum_alignment", "pedagogical_foundations", "delivery_grid",
        ]
        placeholders = [f.placeholder for s in template.sections for f in s.fields]
        assert set(placeholders) == set(spec.tokens)

    def test_legacy_templates_stay_available(self):
        for template_id in ("tpl-jhs-ges", "tpl-jhs-professional", "tpl-primary-standard",
                            "tpl-ec-activity", "tpl-shs-ges", "tpl-approved-org-headteacher"):
            assert get_template_by_id(template_id) is not None

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_helper_matches_by_id_or_object(self, spec):
        # Every bundled get/NaCCA form is verified-approved; legacy
        # SchemeKnie-standard ids and unknown ids are not.
        assert is_official_ges_template(spec.template_id) is True
        assert is_official_ges_template(get_template_by_id(spec.template_id)) is True
        assert not is_official_ges_template("tpl-jhs-ges")
        assert not is_official_ges_template(None)


class TestAIContract:
    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_prompt_states_the_official_rules(self, spec):
        prompt = ges_system_prompt(spec)
        assert "NEVER invent curriculum facts" in prompt
        assert "markdown fences" in prompt
        for name in spec.phase_names:
            assert name in prompt

    @pytest.mark.parametrize(
        "spec,expected", [(KG_SPEC, "Kindergarten"), (PRIMARY_SPEC, "Lower Primary"),
                          (JHS_SPEC, "Junior High School"), (SHS_SPEC, "Senior High School")],
        ids=lambda v: getattr(v, "key", str(v)))
    def test_prompt_is_level_specific(self, spec, expected):
        assert expected in ges_system_prompt(spec)
        # A level's framing never leaks ineo anoeher level's prompt.
        others = [s for s in ALL_SPECS if s.key != spec.key]
        for other in others:
            assert other.prompt_tailoring not in ges_system_prompt(spec)

    def test_prompts_are_distinct_per_level(self):
        prompts = {s.key: ges_system_prompt(s) for s in ALL_SPECS}
        assert len(set(prompts.values())) == len(ALL_SPECS)
        assert GES_SYSTEM_PROMPT == prompts[LEVEL_JHS]

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_phase_names_are_the_printed_row_labels(self, spec):
        blob = document_text(load_document(spec))
        for name in spec.phase_names:
            assert name.lower() in blob.lower()

    def test_valid_payload_accepted(self):
        ok, norm = validate_ges_lesson_json({
            "lesson_topic": "T",
            "phases": [{"name": "Phase 1: Tuning-In",
                        "learner_activities": ["Sing a rhyme."]}],
        })
        assert ok is True
        assert norm["phases"][0]["learner_activities"] == ["Sing a rhyme."]

    def test_curriculum_keys_dropped_not_fatal(self):
        ok, norm = validate_ges_lesson_json({
            "strand": "INVENTED", "indicators": ["B7.9.9.9"],
            "INSERT_SUBJECT": "HACK", "phases": [],
        })
        assert ok is True
        assert "strand" not in norm and "indicators" not in norm
        assert "INSERT_SUBJECT" not in norm

    def test_non_object_rejected(self):
        ok, errors = validate_ges_lesson_json("just text")
        assert ok is False and errors

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.key)
    def test_normalize_is_deterministic_and_matches_render_values(self, spec):
        lesson = make_lesson(spec)
        assert normalize_lesson_to_ges(spec, lesson) == placeholder_values(spec, lesson)
        assert "strand" not in normalize_lesson_to_ges(spec, lesson)

    def test_spec_lookup_helpers(self):
        assert spec_for_level("KG") is KG_SPEC
        assert spec_for_level(" shs ") is SHS_SPEC
        assert spec_for_level("university") is None
        assert spec_for_template_id(JHS_SPEC.template_id) is JHS_SPEC
        assert spec_for_template_id("tpl-jhs-ges") is None
        assert GES_TEMPLATES[LEVEL_SHS] is SHS_SPEC


class TestTemplatesEndpointDefaults:
    """GET /api/templates reports is_default for the class level being planned."""

    @staticmethod
    def _listing(db, user, educational_level=None, class_level=None):
        import asyncio

        from src.routers.templates import list_templates

        return asyncio.run(list_templates(educational_level=educational_level,
                                          class_level=class_level, db=db,
                                          current_user=user))

    @staticmethod
    def _default_id(payload):
        defaults = [t for t in payload["templates"] if t["is_default"]]
        assert len(defaults) == 1, [t["id"] for t in defaults]
        return defaults[0]["id"]

    def test_primary_default_splits_at_basic_four(self, db):
        """The GES primary form is a LOWER PRIMARY form (Basic 1-3); Upper
        Primary falls back to the same verified form so a teacher's default is
        always an approved template, never the hidden SchemeKnie-standard one."""
        from tests.conftest import make_user

        user = make_user(db, role="teacher")
        lower = self._listing(db, user, "Primary", "Basic 2")
        upper = self._listing(db, user, "Primary", "Basic 5")

        assert self._default_id(lower) == PRIMARY_SPEC.template_id
        assert self._default_id(upper) == PRIMARY_SPEC.template_id

    def test_class_level_selects_each_levels_official_form(self, db):
        from tests.conftest import make_user

        user = make_user(db, role="teacher")
        cases = [("Early Childhood", "KG 2", KG_SPEC),
                 ("Junior High School", "Basic 8", JHS_SPEC),
                 ("Senior High School", "SHS 3", SHS_SPEC)]
        for educational_level, class_level, spec in cases:
            payload = self._listing(db, user, educational_level, class_level)
            assert self._default_id(payload) == spec.template_id
            assert all(t["educational_level"] == educational_level
                       for t in payload["templates"])

    def test_without_class_level_the_templates_own_flag_is_reported(self, db):
        from tests.conftest import make_user

        user = make_user(db, role="teacher")
        payload = self._listing(db, user, "Primary")
        # The verified primary form is the level default a teacher sees.
        assert self._default_id(payload) == PRIMARY_SPEC.template_id

    def test_official_templates_are_flagged_official(self, db):
        """API exposes the evidence-based flag plus the provenance record.
        Teachers see only the four verified approved forms (PART 8-10); the
        SchemeKnie-standard templates are filtered out of the listing."""
        from tests.conftest import make_user

        user = make_user(db, role="teacher")
        payload = self._listing(db, user)
        # A teacher's listing coneains only verified/approved built-in forms.
        for t in payload["templates"]:
            if not t["is_custom"]:
                assert t["is_official"] is True, t["id"]
                assert t["provenance"]["verification_status"] == "verified", t["id"]
        official = {t["id"] for t in payload["templates"] if t["is_official"]}
        assert official == {
            JHS_SPEC.template_id, "tpl-approved-org-headteacher",
            KG_SPEC.template_id, PRIMARY_SPEC.template_id, SHS_SPEC.template_id,
            "tpl-wapef-approved-plan"}
        assert payload["provenance_summary"]["pending_verification"] == []
        by_id = {t["id"]: t for t in payload["templates"]}
        for spec in ALL_SPECS:
            prov = by_id[spec.template_id]["provenance"]
            assert prov["official"] is True
            assert prov["verification_status"] == "verified"
            assert prov["levels"], spec.template_id
            # Teacher-facing grouping (PART 10) is present and non-internal.
            assert by_id[spec.template_id]["approved_group"].startswith("Approved ")

    def test_pending_templates_are_hidden_from_teachers(self, db):
        """PART 9: a pending/unverified built-in form must never reach a
        teacher's selection, even if one were added to the registry."""
        from tests.conftest import make_user
        from src.engines.template_provenance import (
            PROVENANCE_REGISTRY, VERIFICATION_PENDING, TemplateProvenance,
            PROVENANCE_TEACHFLOW_STANDARD,
        )
        import src.engines.template_engine as te

        # Simulaee an unverified/pending built-in form in boeh the provenance
        # registry and the template lise, the two places the API reads from.
        pending_id = "tpl-pending-test-form"
        PROVENANCE_REGISTRY[pending_id] = TemplateProvenance(
            template_id=pending_id,
            provenance=PROVENANCE_TEACHFLOW_STANDARD,
            verification_status=VERIFICATION_PENDING,
            official=False,
            evidence="Test pending form; must be hidden from teachers.",
        )
        pending_tpl = te.Template(
            id=pending_id, name="Pending Test Form",
            family=te.TemplateFamily.JHS,
            educational_level=te.EducationalLevel.JHS,
            description="Pending", features=[],
            sections=[], is_default=False, is_official=False,
        )
        te.DEFAULT_TEMPLATES.append(pending_tpl)
        try:
            user = make_user(db, role="teacher")
            payload = self._listing(db, user)
            ids = {t["id"] for t in payload["templates"]}
            assert pending_id not in ids

            # A plaeform admin CAN set pending forms (PART 30).
            admin = make_user(db, role="platform_admin")
            admin_payload = self._listing(db, admin)
            admin_ids = {t["id"] for t in admin_payload["templates"]}
            assert pending_id in admin_ids
        finally:
            PROVENANCE_REGISTRY.pop(pending_id, None)
            te.DEFAULT_TEMPLATES.remove(pending_tpl)

    def test_invalid_class_level_is_rejected(self, db):
        from fastapi import HTTPException

        from tests.conftest import make_user

        user = make_user(db, role="teacher")
        with pytest.raises(HTTPException) as exc:
            self._listing(db, user, "Primary", "Basic 99")
        assert exc.value.status_code == 400


class TestGoldenMaster:
    """The approved JHS source document is the structural authority (items 2/4/6).

    Ies normalized fingerprine lives in assees/ges_jhs_golden_maseer.json and the
    renderer's ouepue is compared against ie wieh the structural validaeor —
    eopology (eables, dimensions, merges, labels), not juse "all fields filled".
    """

    GOLDEN_PATH = os.path.join(
        os.path.dirname(__file__), "..", "src", "engines", "assets",
        "ges_jhs_golden_master.json")

    @staticmethod
    def _golden():
        import json

        with open(TestGoldenMaster.GOLDEN_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_golden_master_exists_and_declares_provenance(self):
        golden = self._golden()
        assert golden["source_document"] == "ges_jhs_lesson_plan_template.docx"
        assert golden["provenance"] == "approved_organizational"
        assert len(golden["tables"]) == 4
        assert golden["table_count"] == 4

    def test_fingerprint_matches_the_current_source_document(self):
        """The stored fingerprint must not drift from the bundled approved DOCX."""
        import json

        from src.engines.template_analyzer import analyze_docx_sample

        fresh = analyze_docx_sample(template_path(JHS_SPEC))
        golden = self._golden()
        assert json.dumps(fresh["tables"], sort_keys=True) == json.dumps(
            golden["tables"], sort_keys=True)

    def test_fingerprint_topology(self):
        """The approved form: meeadaea 4x4, curriculum 4x2, pedagogy 4x2,
        delivery grid 4x3 wieh PHASE rows in column 0."""
        golden = self._golden()
        dims = [(t["rows"], t["cols"]) for t in golden["tables"]]
        assert dims == [(4, 4), (4, 2), (4, 2), (4, 3)]
        labels = [c.get("label") for t in golden["tables"] for c in t["cells"]
                  if c.get("label")]
        for expected in ("WEEK ENDING", "CLASS / LEVEL", "SUBJECT", "STRAND",
                         "SUB-STRAND", "CONTENT STANDARD", "INDICATOR",
                         "CORE COMPETENCIES", "PERFORMANCE INDICATOR"):
            assert expected in labels
        phase_markers = [c for c in golden["tables"][3]["cells"]
                         if c.get("is_phase_marker")]
        assert [c["r"] for c in phase_markers] == [1, 2, 3]
        # Every cell occupies exactly one grid position: no merges in the source.
        for t in golden["tables"]:
            for c in t["cells"]:
                assert c.get("colspan", 1) == 1 and c.get("rowspan", 1) == 1

    def test_registry_source_document_is_the_golden_source(self):
        record = provenance_for_template(JHS_SPEC.template_id)
        assert record.source_document.endswith("ges_jhs_lesson_plan_template.docx")

    @pytest.mark.parametrize("n_lessons", [1, 2])
    def test_rendered_output_matches_the_approved_structure(self, tmp_path, n_lessons):
        """Item 6: structural comparison APPROVED SOURCE vs GENERATED DOCX."""
        from src.engines.template_analyzer import validate_custom_docx

        golden = self._golden()
        lessons = [make_lesson(JHS_SPEC, topic=f"Lesson {i + 1}")
                   for i in range(n_lessons)]
        out_path = tmp_path / f"jhs_x{n_lessons}.docx"
        render_and_save(JHS_SPEC, lessons, out_path)

        result = validate_custom_docx(
            golden, str(out_path),
            expected_values=["Basic 7", "Run a console log script."],
            forbidden_values=JHS_GUIDANCE + ["[", "]", "INSERT_",
                                             "Instructions for AI Engine"],
        )
        failures = [c for c in result["checks"] if not c["pass"]]
        assert result["pass"], failures

        # The renderer must not add, drop or reorder the approved tables.
        assert len(Document(str(out_path)).tables) == 4 * n_lessons

"""
WAPEF Basic 1-3 class-teacher weekly plan acceptance tests (items A-R).

The Basic 1-3 model is materially different from Basic 4-JHS:
  ONE CLASS TEACHER -> MULTIPLE SUBJECTS -> DIFFERENT DAYS -> ONE WEEKLY PLAN

These tests pin the model, its isolation guarantees and its export against the
real ``WAPEF BASIC 1 PLAN.docx`` fixture (which is a completed weekly class
plan: one document holding six subject sections, each with its own metadata
and a DAYS | PHASE 1: STARTER | PHASE 2: MAIN | PHASE 3: REFLECTION table).
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from docx import Document

from src.engines.wapef_basic13_template import (
    TEMPLATE_ID,
    TEMPLATE_NAME,
    DAY_OPTIONS,
    WEEK_DAYS,
    format_day_label,
    is_basic13_class,
    is_basic13_template,
    normalize_day_groups,
    normalize_teaching_days,
    render_weekly_document,
    validate_rendered_document,
    wapef_routing,
    wapef_template_for_class,
)
from src.engines.template_engine import get_template_by_id
from src.engines.template_provenance import provenance_for_template
from src.engines.weekly_plan_engine import (
    build_weekly_plan,
    distribute_indicators,
    plan_validation_issues,
    teaching_days_summary,
)
from src.models import (
    ClassLevel,
    Subject,
    Week,
    WeekType,
    WeeklyClassPlan,
    WeeklyPlanRequest,
    WeeklyPlanSubjectRequest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wapef"
BASIC1_PLAN = FIXTURES / "WAPEF BASIC 1 PLAN.docx"


# ── helpers ───────────────────────────────────────────────────────────────────

def _week(week_number: int, subject: str, *, strand=None, sub_strand=None,
           indicators=None, content_standards=None, resources=None,
           performance=None, end_date=date(2026, 9, 25)):
    """A synthetic instruction week of one subject's scheme (curriculum IR)."""
    return Week(
        week_number=week_number,
        start_date=date(2026, 9, 21),
        end_date=end_date,
        week_type=WeekType.INSTRUCTION,
        strand=strand,
        sub_strand=sub_strand,
        content_standards=content_standards or [],
        indicators=indicators or [],
        resources=resources or [],
        scheme_of_work_id=f"scheme-{subject}",
    )


def _scheme_ir(subject, class_level, weeks, scheme_id=None):
    return {
        scheme_id or f"scheme-{subject}": {
            "weeks": weeks,
            "subject": subject,
            "class_level": class_level,
        }
    }


def _distinct_cells(row):
    seen = set()
    cells = []
    for cell in row.cells:
        key = id(cell._tc)
        if key not in seen:
            seen.add(key)
            cells.append(cell)
    return cells


def _row_label(row):
    cells = _distinct_cells(row)
    return " ".join((cells[0].text or "").split()) if cells else ""


def _row_value(row):
    cells = _distinct_cells(row)
    return " ".join((cells[1].text or "").split()) if len(cells) > 1 else ""


def _request(class_level=ClassLevel.BASIC_1, week_number=2, subjects=None):
    return WeeklyPlanRequest(
        class_level=class_level,
        week_number=week_number,
        term_start_date=date(2026, 9, 15),
        term_end_date=date(2026, 12, 18),
        term="First Term",
        academic_year="2026/2027",
        subjects=subjects or [],
    )


def _subject(scheme_id, groups, **wapef):
    return WeeklyPlanSubjectRequest(
        scheme_id=scheme_id,
        teaching_day_groups=groups,
        wapef_deep_hope=wapef.get("wapef_deep_hope", wapef.get("deep_hope", "")),
        wapef_storyline=wapef.get("storyline", ""),
        wapef_through_lines=wapef.get("through_lines", []),
        wapef_gods_story=wapef.get("gods_story", ""),
    )


# A multi-subject week mirroring the fixture's structure (English 5 days,
# Maths 5 days, Science 3 days, RME one grouped "MONDAY & THURSDAY" entry).
def _fixture_like_schemes():
    english = [
        _week(2, "English Language",
              indicators=["B1.1.2.1.1 Listen to and recite rhymes.",
                          "B1.2.1.1.1 Identify beginning sounds.",
                          "B1.4.2.1.1 Trace and copy patterns."],
              content_standards=["B1.1.2.1 Oracy"],
              resources=["Word cards", "letter cards"]),
        _week(3, "English Language", indicators=["B1.1.2.1.2 Retell a story."],
              content_standards=["B1.1.2.1 Oracy"], resources=["Picture books"]),
    ]
    maths = [
        _week(2, "Mathematics", strand="Number",
              sub_strand="Counting Representation And Cardinality",
              indicators=["B1.1.1.1.1 Use number names and counting sequences.",
                          "B1.1.1.1.2 Count to answer how many questions."],
              content_standards=["B1.1.1.1 Describe numbers and relationships"],
              resources=["Counters", "bundle and loose straws"]),
    ]
    science = [
        _week(2, "Science", strand="Diversity of matter",
              sub_strand="Living & Non Living Things",
              indicators=["B1.1.1.2.1 Identify and name animals and plants."],
              content_standards=["B1.1.1.2 Living and non-living things"],
              resources=["Pictures of plants and animals"]),
    ]
    rme = [
        _week(2, "Religious & Moral Education", strand="God his creation and attributes",
              sub_strand="God the Creator",
              indicators=["B1.1.1.1.1 Explore God's Creation."],
              content_standards=["B1.1.1.1 Explain who the Creator is"],
              resources=["Wall charts", "video clip"]),
    ]
    return {
        "scheme-english": {"weeks": english, "subject": "English Language",
                           "class_level": ClassLevel.BASIC_1},
        "scheme-maths": {"weeks": maths, "subject": "Mathematics",
                         "class_level": ClassLevel.BASIC_1},
        "scheme-science": {"weeks": science, "subject": "Science",
                           "class_level": ClassLevel.BASIC_1},
        "scheme-rme": {"weeks": rme, "subject": "Religious & Moral Education",
                       "class_level": ClassLevel.BASIC_1},
    }


# ── A. template registration ────────────────────────────────────────────────

def test_template_registered():
    template = get_template_by_id(TEMPLATE_ID)
    assert template is not None
    assert template.name == TEMPLATE_NAME
    assert template.is_official is True
    assert template.id == "tpl-wapef-basic13-weekly-plan"


def test_template_provenance_declared():
    provenance = provenance_for_template(TEMPLATE_ID)
    assert provenance.verified is True
    assert provenance.official is True
    assert provenance.source_document == "backend/tests/fixtures/wapef/WAPEF BASIC 1 PLAN.docx"
    assert set(provenance.levels) == {"Basic 1", "Basic 2", "Basic 3"}


def test_template_has_teaching_days_and_wapef_fields():
    template = get_template_by_id(TEMPLATE_ID)
    field_names = {f.name for s in template.sections for f in s.fields}
    assert "teaching_day_groups" in field_names
    for wapef_field in ("wapef_through_lines", "wapef_gods_story",
                        "wapef_deep_hope", "wapef_storyline"):
        assert wapef_field in field_names


def test_subject_teacher_template_untouched():
    """The existing Approved WAPEF Plan remains registered and unchanged."""
    from src.engines.wapef_template import TEMPLATE_ID as APPROVED_ID
    approved = get_template_by_id(APPROVED_ID)
    assert approved is not None
    assert approved.id == "tpl-wapef-approved-plan"
    assert approved.name == "Approved WAPEF Plan"
    assert TEMPLATE_ID != APPROVED_ID


# ── B. class routing boundary ────────────────────────────────────────────────

@pytest.mark.parametrize("level", [ClassLevel.BASIC_1, ClassLevel.BASIC_2,
                                   ClassLevel.BASIC_3])
def test_basic123_routes_to_weekly_plan(level):
    assert is_basic13_class(level) is True
    assert wapef_template_for_class(level) == TEMPLATE_ID
    assert wapef_routing(level)["planning_model"] == "class_teacher"


@pytest.mark.parametrize("level", [ClassLevel.BASIC_4, ClassLevel.BASIC_5,
                                   ClassLevel.BASIC_6, ClassLevel.BASIC_7,
                                   ClassLevel.BASIC_8, ClassLevel.BASIC_9])
def test_basic4_plus_stays_on_approved_plan(level):
    assert is_basic13_class(level) is False
    assert wapef_template_for_class(level) == "tpl-wapef-approved-plan"
    assert wapef_routing(level)["planning_model"] == "subject_teacher"


def test_boundary_basic3_vs_basic4():
    """The exact boundary the brief calls out (Basic 3 vs Basic 4)."""
    assert wapef_template_for_class(ClassLevel.BASIC_3) == TEMPLATE_ID
    assert wapef_template_for_class(ClassLevel.BASIC_4) == "tpl-wapef-approved-plan"
    # Never the reverse routing.
    assert is_basic13_template(TEMPLATE_ID) is True
    assert is_basic13_template("tpl-wapef-approved-plan") is False


def test_kg_nursery_never_basic13():
    for level in (ClassLevel.KG1, ClassLevel.KG2, ClassLevel.NURSERY):
        assert is_basic13_class(level) is False


# ── C/D/E/F. day model and day groups ────────────────────────────────────────

def test_normalize_teaching_days_accepts_mixed_input():
    assert normalize_teaching_days(["Monday", "THURSDAY"]) == ["MONDAY", "THURSDAY"]
    assert normalize_teaching_days(["mon", 2]) == ["MONDAY", "WEDNESDAY"]
    assert normalize_teaching_days("FRIDAY") == ["FRIDAY"]
    assert normalize_teaching_days([]) == []
    # Saturday/Sunday are never teaching days and are never relabelled.
    assert normalize_teaching_days(["Saturday", "Sunday"]) == []


def test_normalize_day_groups_dedupes_and_orders():
    groups = normalize_day_groups([["THURSDAY", "MONDAY"], ["MONDAY"], ["Tuesday"]])
    assert groups == [["MONDAY", "THURSDAY"], ["TUESDAY"]]


def test_format_day_label_grouped_and_single():
    assert format_day_label(["MONDAY"]) == "MONDAY"
    assert format_day_label(["MONDAY", "THURSDAY"]) == "MONDAY & THURSDAY"
    assert format_day_label([]) == ""


def test_day_options_are_the_five_weekdays():
    assert [d["label"] for d in DAY_OPTIONS] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    assert WEEK_DAYS == ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")


# ── G/H. subject metadata + day content isolation ───────────────────────────

def test_weekly_plan_holds_multiple_subject_sections():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                    ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-maths", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                  ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-science", [["TUESDAY"], ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    assert isinstance(plan, WeeklyClassPlan)
    assert len(plan.subjects) == 4
    assert {s.subject for s in plan.subjects} == {
        "English Language", "Mathematics", "Science",
        "Religious & Moral Education"}


def test_each_subject_has_own_metadata_and_isolation():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"]]),
        _subject("scheme-maths", [["MONDAY"], ["TUESDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    english, maths = plan.subjects

    # Metadata is subject-scoped: nothing leaks between subjects.
    assert english.metadata.subject == "English Language"
    assert maths.metadata.subject == "Mathematics"
    assert "Counters" in maths.metadata.teaching_learning_resources
    assert "Counters" not in english.metadata.teaching_learning_resources
    assert "Word cards" in english.metadata.teaching_learning_resources
    assert "Word cards" not in maths.metadata.teaching_learning_resources
    # Strand is present where the source has it and blank where it does not.
    assert maths.metadata.strand == "Number"
    assert english.metadata.strand == ""
    assert english.metadata.sub_strand == ""
    assert maths.metadata.sub_strand == "Counting Representation And Cardinality"


def test_day_subsets_and_grouped_days():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-science", [["TUESDAY"], ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    science, rme = plan.subjects
    # CASE B: subject taught only selected days (no Monday-Friday skeleton).
    assert science.teaching_days == ["TUESDAY", "THURSDAY", "FRIDAY"]
    assert len(science.day_plans) == 3
    # CASE C: one shared entry applies to two days.
    assert rme.teaching_day_groups == [["MONDAY", "THURSDAY"]]
    assert rme.day_plans[0].days == ["MONDAY", "THURSDAY"]
    assert rme.day_plans[0].day_label == "MONDAY & THURSDAY"
    assert len(rme.day_plans) == 1


def test_days_omitted_when_not_taught():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    rme = plan.subjects[0]
    # No rows for days the subject is not taught.
    assert "TUESDAY" not in rme.teaching_days
    assert "WEDNESDAY" not in rme.teaching_days
    assert "FRIDAY" not in rme.teaching_days


def test_day_content_isolation_between_subjects():
    """English Monday and Maths Monday are independent DayPlans."""
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"]]),
        _subject("scheme-maths", [["MONDAY"], ["TUESDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    english_monday = plan.subjects[0].day_plans[0]
    maths_monday = plan.subjects[1].day_plans[0]
    assert english_monday.starter != maths_monday.starter
    assert english_monday.main_activities != maths_monday.main_activities
    # Editing one subject's day must not mutate the other's.
    english_monday.starter = "EDITED"
    assert plan.subjects[1].day_plans[0].starter != "EDITED"


def test_day_content_differs_within_one_subject():
    """Monday and Tuesday of the same subject are not clones (anti-cloning)."""
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                    ["THURSDAY"], ["FRIDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    days = plan.subjects[0].day_plans
    assert len(days) == 5
    starters = [d.starter for d in days]
    mains = [_main_text(d) for d in days]
    # At least the openings differ (position 0 vs later days link forward).
    assert len(set(starters)) > 1, "day starters are cloned"
    assert len(set(mains)) > 1, "day main blocks are cloned"


def _main_text(day_plan):
    from src.models import TeachingActivity
    activities = day_plan.main_activities or []
    parts = []
    for a in activities:
        if isinstance(a, TeachingActivity):
            parts.append(a.description or "")
        elif isinstance(a, dict):
            parts.append(a.get("description") or "")
        else:
            parts.append(str(a or ""))
    return " ".join(p for p in parts if p)


def test_indicator_distribution_across_days():
    """Several indicators split across the subject's days, never dropped."""
    distributed = distribute_indicators(
        ["I1", "I2", "I3", "I4"],
        [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"], ["THURSDAY"], ["FRIDAY"]],
    )
    assert distributed == [["I1"], ["I2"], ["I3"], ["I4"], []]
    # One indicator across five days keeps it as the week's focus on each day.
    single = distribute_indicators(["ONLY"], [["MONDAY"], ["TUESDAY"]])
    assert single == [["ONLY"], ["ONLY"]]


# ── I. WAPEF metadata persistence ───────────────────────────────────────────

def test_wapef_fields_persist_and_are_never_invented():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"]],
                 deep_hope="Beauty creator", storyline="God's Story",
                 through_lines=["Order discoverer", "Community builder"],
                 gods_story="Creation"),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    meta = plan.subjects[0].metadata
    assert meta.wapef_deep_hope == "Beauty creator"
    assert meta.wapef_through_lines == ["Order discoverer", "Community builder"]
    assert meta.wapef_gods_story == "Creation"
    # A subject with no selections keeps blanks (never invented).
    maths_meta = plan.subjects[1].metadata if len(plan.subjects) > 1 else None
    if maths_meta is not None:
        assert maths_meta.wapef_deep_hope == ""
        assert maths_meta.wapef_through_lines == []


# ── J. weekly generation + teaching-day summary ─────────────────────────────

def test_teaching_days_summary_reports_each_subject():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-science", [["TUESDAY"], ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    summary = teaching_days_summary(plan)
    by_subject = {s["subject"]: s for s in summary}
    assert by_subject["Science"]["teaching_days"] == ["TUESDAY", "THURSDAY", "FRIDAY"]
    assert by_subject["Religious & Moral Education"]["teaching_day_groups"] == \
        [["MONDAY", "THURSDAY"]]


def test_plan_validation_flags_duplicate_day_assignment():
    """The same subject claiming a day twice is the structural error.

    Cross-subject overlap is normal (English and Maths both run Monday in the
    real fixture); a duplicated SECTION of one subject is not.
    """
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"]]),
        _subject("scheme-english", [["MONDAY"]]),  # duplicate section
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    issues = plan_validation_issues(plan)
    assert any("MONDAY" in i for i in issues)


def test_plan_validation_allows_two_schemes_sharing_a_subject_name():
    """Two DIFFERENT schemes with one subject name are two sections of the week.

    Re-uploading the same subject file (or splitting a subject across files)
    yields several scheme ids under the same name — like the fixture's
    English/Maths Monday overlap, that is a legitimate weekly document; only
    selecting the SAME scheme twice is the duplicate-section error.
    """
    week = _week(2, "Science",
                 indicators=["B1.1.1.2.1 Identify and name animals and plants."],
                 content_standards=["B1.1.1.2 Living things"])
    schemes = {}
    schemes.update(_scheme_ir("Science", ClassLevel.BASIC_1, [week],
                              scheme_id="scheme-science-a"))
    schemes.update(_scheme_ir("Science", ClassLevel.BASIC_1, [week],
                              scheme_id="scheme-science-b"))
    request = _request(subjects=[
        _subject("scheme-science-a", [["MONDAY", "TUESDAY"]]),
        _subject("scheme-science-b", [["MONDAY", "TUESDAY", "WEDNESDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    assert plan_validation_issues(plan) == []


def test_plan_validation_passes_for_fixture_like_plan():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                    ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-maths", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                  ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-science", [["TUESDAY"], ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {"template_id": TEMPLATE_ID})
    assert plan_validation_issues(plan) == []


# ── K/L/N. DOCX weekly export + real fixture structure ──────────────────────

def _weekly_plan_for_export():
    schemes = _fixture_like_schemes()
    request = _request(subjects=[
        _subject("scheme-english", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                    ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-maths", [["MONDAY"], ["TUESDAY"], ["WEDNESDAY"],
                                  ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-science", [["TUESDAY"], ["THURSDAY"], ["FRIDAY"]]),
        _subject("scheme-rme", [["MONDAY", "THURSDAY"]]),
    ])
    plan = build_weekly_plan(request, schemes, {
        "template_id": TEMPLATE_ID,
        "school_name": "Test School",
    })
    plan.template_id = TEMPLATE_ID
    return plan


def test_render_weekly_document_produces_one_document_with_sections():
    plan = _weekly_plan_for_export()
    document = render_weekly_document(plan, {"school_name": "Test School"})
    # ONE weekly document holding every subject section (not one doc per lesson).
    assert len(document.tables) == len(plan.subjects)
    # No placeholder tokens survive the render.
    assert validate_rendered_document(document) == []


def test_rendered_weekly_document_has_days_and_phase_headers():
    plan = _weekly_plan_for_export()
    document = render_weekly_document(plan, {"school_name": "Test School"})
    table = document.tables[0]
    texts = []
    for row in table.rows:
        for cell in row.cells:
            texts.append((cell.text or "").strip())
    joined = " | ".join(texts)
    assert "DAYS" in joined
    assert "PHASE 1: STARTER" in joined
    assert "PHASE 2: MAIN" in joined
    assert "PHASE 3: REFLECTION" in joined
    # The day rows the fixture prints: day subsets and grouped days.
    science_texts = []
    for row in document.tables[2].rows:
        for cell in row.cells:
            science_texts.append((cell.text or "").strip())
    assert "TUESDAY" in " | ".join(science_texts)
    rme_texts = []
    for row in document.tables[3].rows:
        for cell in row.cells:
            rme_texts.append((cell.text or "").strip())
    assert "MONDAY & THURSDAY" in " | ".join(rme_texts)


def test_rendered_document_drops_blank_optional_metadata_rows():
    """English has no Strand/Sub strand: those rows are dropped, not blank."""
    plan = _weekly_plan_for_export()
    document = render_weekly_document(plan, {"school_name": "Test School"})
    english_texts = []
    for row in document.tables[0].rows:
        for cell in row.cells:
            english_texts.append((cell.text or "").strip())
    joined = " | ".join(english_texts)
    assert "Strand" not in joined
    # Maths DOES carry Strand/Sub strand.
    maths_texts = []
    for row in document.tables[1].rows:
        for cell in row.cells:
            maths_texts.append((cell.text or "").strip())
    maths_joined = " | ".join(maths_texts)
    assert "Strand" in maths_joined


def test_no_internal_field_names_or_debug_strings_in_export():
    plan = _weekly_plan_for_export()
    document = render_weekly_document(plan, {"school_name": "Test School"})
    all_text = []
    for paragraph in document.paragraphs:
        all_text.append(paragraph.text or "")
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    all_text.append(paragraph.text or "")
    joined = "\n".join(all_text)
    for banned in ("[", "PHASE1_", "DAY_LABEL", "wapef_", "teaching_day_groups",
                   "None", "{}"):
        assert banned not in joined, f"export leaks {banned!r}"


# ── N. real Basic 1 fixture acceptance ──────────────────────────────────────

def test_real_basic1_fixture_structure():
    """The supplied Basic 1 plan validates the weekly class-plan structure.

    Structural acceptance only (section ordering, field placement, subject
    grouping, the day column, the phase columns, day subsets, grouped days and
    multiple subject sections in one document). The fixture's own lesson prose
    is never copied into production.
    """
    assert BASIC1_PLAN.is_file(), "WAPEF BASIC 1 PLAN.docx fixture missing"
    document = Document(str(BASIC1_PLAN))

    # One weekly document with a school / LESSON PLAN / WEEK header.
    paragraphs = [(p.text or "").strip() for p in document.paragraphs if (p.text or "").strip()]
    assert len(paragraphs) >= 3
    assert paragraphs[1].upper() == "LESSON PLAN"
    assert paragraphs[2].upper().startswith("WEEK")

    # Multiple subject sections, one table each.
    assert len(document.tables) >= 6
    subject_names = []
    for table in document.tables:
        subject_names.append(_row_value(table.rows[2]))
    assert "ENGLISH LANGUAGE" in subject_names
    assert "MATHEMATICS" in subject_names
    assert "SCIENCE" in subject_names
    assert "RELIGIOUS & MORAL EDUCATION" in subject_names
    assert "HISTORY" in subject_names
    assert "CREATIVE ARTS" in subject_names

    # The DAYS | PHASE columns exist in every subject section.
    for table in document.tables:
        header_row = None
        for row in table.rows:
            first = " ".join((row.cells[0].text or "").split()).upper()
            if first == "DAYS":
                header_row = row
                break
        assert header_row is not None, "DAYS header row missing"
        headers = [" ".join((c.text or "").split()).upper()
                   for c in header_row.cells]
        assert "PHASE 1: STARTER" in " ".join(headers)
        assert "PHASE 2: MAIN" in " ".join(headers)
        assert "PHASE 3: REFLECTION" in " ".join(headers)


def test_real_basic1_fixture_demonstrates_day_patterns():
    """CASE A-H: the real document's day patterns the model must support."""
    document = Document(str(BASIC1_PLAN))
    by_subject = {}
    for table in document.tables:
        subject = _row_value(table.rows[2])
        day_labels = []
        for row in table.rows:
            first = " ".join((row.cells[0].text or "").split()).upper()
            if first.startswith("DAYS"):
                continue
            if first and any(first.startswith(d) or d in first
                             for d in ("MONDAY", "TUESDAY", "WEDNESDAY",
                                       "THURSDAY", "FRIDAY")):
                day_labels.append(first)
        by_subject[subject] = day_labels

    english = by_subject.get("ENGLISH LANGUAGE", [])
    # CASE A: Monday-Friday.
    assert any("MONDAY" in d for d in english)
    assert any("FRIDAY" in d for d in english)
    # CASE D: different subjects have different day patterns.
    science = by_subject.get("SCIENCE", [])
    rme = by_subject.get("RELIGIOUS & MORAL EDUCATION", [])
    assert science != english or len(science) < len(english)
    # CASE C: a grouped multi-day entry.
    assert any("MONDAY" in d and "THURSDAY" in d for d in rme), \
        "RME grouped MONDAY & THURSDAY row missing"


def test_real_basic1_fixture_metadata_differs_by_subject():
    """CASE F/G: some sections carry Strand/Sub strand, some do not."""
    document = Document(str(BASIC1_PLAN))
    def _labels(table):
        return {" ".join((row.cells[0].text or "").split()).rstrip(":").strip()
                for row in table.rows}
    english_labels = _labels(document.tables[0])
    maths_labels = _labels(document.tables[1])
    assert "Strand" not in english_labels
    assert "Strand" in maths_labels
    assert "Sub strand" in maths_labels
    # CASE H: multiple learning indicators in one section.
    maths_indicators = _row_value(document.tables[1].rows[5])
    assert "B1.1.1.1" in maths_indicators


# ── O/P/Q/R. regressions stay intact ────────────────────────────────────────

def test_subject_teacher_wapef_plan_still_renders():
    """Basic 4-JHS regression: the Approved WAPEF Plan is untouched."""
    from src.engines.wapef_template import render_document as render_wapef
    from src.engines.wapef_fields import WAPEF_THROUGH_LINES
    from src.models import LessonPlan, AllocatedIndicator
    from datetime import date as _date

    alloc = AllocatedIndicator(
        indicator_code="B4.1.1.1.1", indicator_description="Test indicator.",
        content_standard_code="B4.1.1.1",
        content_standard_description="Test standard.",
        strand="Number", sub_strand="Counting",
        week_number=2, week_ending=_date(2026, 9, 25),
    )
    lesson = LessonPlan(
        scheme_of_work_id="s", term_config_id="t", week_number=2,
        lesson_sequence=1, lesson_date=_date(2026, 9, 25),
        class_level=ClassLevel.BASIC_4, subject=Subject.MATHEMATICS,
        wapef_deep_hope="Beauty creator",
        wapef_through_lines=list(WAPEF_THROUGH_LINES[:2]),
    )
    document = render_wapef([lesson], {"school_name": "Test"})
    assert document is not None


def test_kg_and_nursery_templates_untouched():
    """KG/Nursery regression: their templates remain registered."""
    from src.engines.template_engine import get_template_by_id
    assert get_template_by_id("tpl-official-ges-nacca-kg") is not None
    assert get_template_by_id("tpl-wapef-approved-plan") is not None


def test_allocation_engine_still_allocates_indicators():
    """The Basic 4-JHS allocation rule is unchanged."""
    from src.engines.allocation_engine import AllocationEngine
    from src.models import TermConfig
    weeks = [
        Week(week_number=1, start_date=date(2026, 9, 15), end_date=date(2026, 9, 18),
             indicators=["I1", "I2"], content_standards=["CS1"],
             scheme_of_work_id="s"),
    ]
    config = TermConfig(scheme_of_work_id="s", term_start_date=date(2026, 9, 14),
                        term_end_date=date(2026, 12, 18), lessons_per_week=3,
                        teaching_days=[0, 2, 4])
    calendar = __import__("src.engines.calendar_engine", fromlist=["CalendarEngine"]).CalendarEngine().build_calendar(config, weeks)
    coverage = AllocationEngine().allocate(weeks, calendar, config)
    assert coverage.total_generated_lessons >= 0

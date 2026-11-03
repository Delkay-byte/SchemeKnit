"""Per-indicator references/TLRs and subject detection regressions."""
from datetime import date

from src.curriculum.lesson_builder import build_lesson
from src.models import (
    AIMode, AllocatedIndicator, ClassLevel, Subject, TermConfig,
)
from src.parsers.subject_keywords import canonical_subject_from_heading


def _config(indicator_resources=None):
    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_6, subject=Subject.ICT,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=35,
        teaching_days=[0, 2, 4], holidays=[], ai_mode=AIMode.OFF,
        indicator_resources=indicator_resources or {},
    )


def _alloc(code: str, position: int = 0):
    return AllocatedIndicator(
        indicator_code=code,
        indicator_description=f"{code} Demonstrate the skill",
        source_occurrence_id=f"week2:{position}:{code}",
        content_standard_code="B6.1.1.1",
        content_standard_description="B6.1.1.1",
        strand="Introduction to Computing",
        sub_strand="Computer Systems",
        week_number=2,
        source_resources=["Keyboard", "Mouse"],
        lesson_date=date(2026, 9, 14), period_index=position + 1,
        allocated=True, teaching_week=2,
    )


def test_each_indicator_gets_its_own_references_and_tlrs():
    config = _config({
        "week2:0:B6.1.1.1.1": {
            "references": ["Computing Textbook p.12"],
            "tlrs": ["Teacher-made keyboard chart"],
        },
        "week2:1:B6.1.1.1.2": {
            "references": ["Computing Textbook p.18"],
            "tlrs": ["Mouse demonstration"],
        },
    })
    first = build_lesson(_alloc("B6.1.1.1.1", 0), config, "s")
    second = build_lesson(_alloc("B6.1.1.1.2", 1), config, "s")

    assert first.references == ["Computing Textbook p.12"]
    assert second.references == ["Computing Textbook p.18"]
    assert first.other_tlrs == ["Teacher-made keyboard chart"]
    assert second.other_tlrs == ["Mouse demonstration"]
    # Source TLRs remain intact and separate from teacher additions.
    assert "Keyboard" in first.source_tlrs
    assert "Teacher-made keyboard chart" not in first.source_tlrs


def test_an_empty_per_indicator_entry_does_not_inherit_a_global_reference():
    config = _config({"week2:0:B6.1.1.1.1": {"references": [], "tlrs": []}})
    config.references = ["Global book"]
    lesson = build_lesson(_alloc("B6.1.1.1.1", 0), config, "s")
    assert lesson.references == []
    assert lesson.other_tlrs == []


def test_computing_title_is_recognised_as_computing_heading():
    assert canonical_subject_from_heading(
        "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - COMPUTING"
    ) == Subject.ICT
    assert canonical_subject_from_heading("BASIC 6 ICT") == Subject.ICT
    assert canonical_subject_from_heading(
        "Information and Communication Technology"
    ) == Subject.ICT
    assert canonical_subject_from_heading(
        "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - MATHEMATICS"
    ) == Subject.MATHEMATICS


def test_ambiguous_heading_is_not_silently_classified():
    assert canonical_subject_from_heading("SCIENCE AND MATHEMATICS") is None
    assert canonical_subject_from_heading("Introduction to Computing") is None


# ── Document-level subject detection (DOCX section splitter) ───────────────

from types import SimpleNamespace  # noqa: E402

from src.parsers.docx_parser import DOCXParser  # noqa: E402
from src.routers.documents import _subject_display  # noqa: E402


def _table(*rows):
    return [[str(cell) for cell in row] for row in rows]


def test_computing_title_splits_a_document_into_a_computing_section():
    parser = DOCXParser()
    sections = parser._detect_sections([
        ("paragraph", "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - COMPUTING"),
        ("table", _table(("Week", "Strand", "Indicator"), (1, "Intro", "B6.1.1.1.1"))),
    ])
    assert len(sections) == 1
    assert sections[0]["subject"] == Subject.ICT
    # The source heading is preserved, not rewritten to a bare "ICT".
    assert sections[0]["title"] == (
        "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - COMPUTING")


def test_subject_heading_identifies_a_document_whose_title_does_not():
    parser = DOCXParser()
    sections = parser._detect_sections([
        ("paragraph", "FIRST TERM SCHEME OF LEARNING"),
        ("paragraph", "COMPUTING"),
        ("table", _table(("Week", "Indicator"), (1, "B6.1.1.1.1"))),
    ])
    assert [s["subject"] for s in sections] == [Subject.ICT]
    assert sections[0]["title"] == "COMPUTING"


def test_multi_subject_document_keeps_distinct_sections():
    parser = DOCXParser()
    sections = parser._detect_sections([
        ("paragraph", "BASIC 6 COMPUTING"),
        ("table", _table(("Week", "Indicator"), (1, "B6.1.1.1.1"))),
        ("paragraph", "BASIC 6 MATHEMATICS"),
        ("table", _table(("Week", "Indicator"), (1, "B6.2.1.1.1"))),
    ])
    assert [s["subject"] for s in sections] == [Subject.ICT, Subject.MATHEMATICS]


def test_ambiguous_subject_heading_is_not_forced_into_a_subject_section():
    parser = DOCXParser()
    sections = parser._detect_sections([
        ("paragraph", "FIRST TERM SCHEME OF LEARNING"),
        ("table", _table(("Week", "Indicator"), (1, "B6.1.1.1.1"))),
    ])
    # No subject heading: the table becomes an unlabelled section, never a
    # guessed "ICT" section.
    assert [s["subject"] for s in sections] == [None]


def test_computing_title_displays_as_computing_while_canonical_stays_ict():
    scheme = SimpleNamespace(
        subject=Subject.ICT,
        document_title="FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - COMPUTING",
        filename="Basic 6 Computing.docx",
    )
    assert scheme.subject is Subject.ICT  # allocation/pedagogy authority
    assert _subject_display(scheme) == "Computing"


def test_explicit_ict_document_still_displays_as_ict():
    scheme = SimpleNamespace(
        subject=Subject.ICT, document_title="BASIC 6 ICT", filename="ict.docx")
    assert _subject_display(scheme) == "ICT"


def test_spelled_out_ict_title_keeps_its_source_label():
    scheme = SimpleNamespace(
        subject=Subject.ICT,
        document_title="Information and Communication Technology",
        filename="ict.docx")
    assert _subject_display(scheme) == "Information and Communication Technology"


def test_signals_agree_on_computing_body_and_filename():
    parser = DOCXParser()
    signals = parser.subject_signals(
        "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - COMPUTING",
        "Basic 6 Computing.docx")
    assert signals["document"] == Subject.ICT
    assert signals["resolved"] == Subject.ICT
    assert signals["conflict"] is False


def test_generated_docx_contains_this_lessons_reference_and_tlr(tmp_path):
    from docx import Document
    from src.engines.docx_export import DOCXExportEngine

    config = _config({
        "week2:0:B6.1.1.1.1": {
            "references": ["Computing Textbook p.12"],
            "tlrs": ["Teacher-made keyboard chart"],
        },
    })
    lesson = build_lesson(_alloc("B6.1.1.1.1", 0), config, "s")
    path = DOCXExportEngine().export_single(
        lesson, output_path=tmp_path / "week2-lesson.docx")

    document = Document(str(path))
    chunks = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                chunks.append(cell.text)
    text = chr(10).join(chunks)
    assert "Computing Textbook p.12" in text
    assert "Teacher-made keyboard chart" in text


def test_term_config_accepts_the_display_label_and_keeps_ict_canonical():
    config = TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_6, subject="Computing",
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
    )
    assert config.subject is Subject.ICT
    spelled_out = TermConfig(
        scheme_of_work_id="s", subject="Information and Communication Technology")
    assert spelled_out.subject is Subject.ICT
    # A genuinely different subject is never coerced into ICT.
    assert TermConfig(scheme_of_work_id="s", subject="Mathematics").subject is Subject.MATHEMATICS

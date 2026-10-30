"""DOCX -> PDF fidelity through the supported LibreOffice converter.

This is the acceptance path for real DOCX-to-PDF conversion. Microsoft Word
COM is only an optional desktop fallback and is deliberately not exercised
here: the host Word installation is unstable, while LibreOffice is the
cross-platform converter the application supports and the desktop build can
bundle.

The test is skipped when LibreOffice is genuinely absent (for example on a
bare CI container). It does not silently fall back to Word or to the unrelated
structured ReportLab renderer: doing either would make a fidelity claim that
was never tested.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.engines.pdf_export import (
    PDFExportEngine,
    _is_real_pdf,
    _resolve_libreoffice,
)


def _normalise(text: str) -> str:
    """Collapse PDF line wrapping so content assertions survive layout."""
    return " ".join((text or "").split())


@pytest.fixture(scope="module")
def konverter_available():
    if _resolve_libreoffice() is None:
        pytest.skip(
            "LibreOffice is not installed on this host; the supported "
            "DOCX->PDF converter cannot be exercised. Word COM is not a "
            "substitute."
        )


def _representative_lesson():
    """A generated Creative Arts lesson with long, edited, Ghanaian content."""
    from tests.test_phase3_assessment_dok import _model_with_structure

    lp = _model_with_structure()
    lp.lesson_topic = (
        "Investigating locally available materials and their properties in a "
        "Ghanaian classroom: designing a useful object for the school community"
    )
    lp.introduction = (
        "Teacher-edited starter: in pairs, learners compare a calabash, a "
        "plastic bottle and a piece of kente brought from home. They describe "
        "one property of each material and predict which one will hold water "
        "without leaking. The teacher records their words on the board, "
        "including the local names learners use in class."
    )
    lp.conclusion = (
        "Teacher-edited conclusion: each group names one local material and "
        "one property they observed. A group representative explains why that "
        "property makes the material suitable for the object they designed. "
        "This deliberately long sentence also exercises wrapping, page flow "
        "and the transition into the assessment section without truncation."
    )
    lp.homework = (
        "Ask an adult at home to name one local material used for cooking and "
        "explain one property that makes it suitable. Write two sentences and "
        "bring them to the next lesson."
    )
    lp.home_assignment = lp.homework

    from src.models import TeachingActivity

    lp.main_activities.append(TeachingActivity(
        phase="Phase 2: Main Learning",
        description=(
            "Learners visit the craft corner and handle samples of calabash, "
            "clay, raffia and recycled plastic. They measure length with a "
            "metre rule, mass with a kitchen scale and cost with a price tag "
            "of GHS 2.50. In mixed-ability groups they record results in a "
            "table, then justify which material is best for a pencil holder "
            "that must survive a school bag. The teacher moves between groups, "
            "asks one probing question per group and notes misconceptions for "
            "the plenary."
        ),
        duration_minutes=25,
    ))
    lp.learner_activities.append(TeachingActivity(
        phase="Phase 2: Main Learning",
        description=(
            "Group task: design a pencil holder using at least two local "
            "materials. Label each material, state one property it contributes "
            "and explain one trade-off (for example, clay is strong but heavy). "
            "Present the design on manila paper with a simple sketch and a "
            "three-step making plan."
        ),
        duration_minutes=15,
    ))
    return lp


def test_libreoffice_conversion_preserves_representative_lesson(
        tmp_path, konverter_available):
    """Real conversion: valid PDF, page order, assessment, edits, no truncation."""
    pypdf = pytest.importorskip("pypdf")
    from src.engines.docx_export import (
        DOCXExportEngine, default_template_for_lessons,
    )

    lp = _representative_lesson()
    docx = DOCXExportEngine().export_combined(
        [lp],
        default_template_for_lessons([lp]),
        tmp_path / "representative_lesson.docx",
    )
    assert docx.is_file() and docx.stat().st_size > 10_000

    engine = PDFExportEngine()
    pdf = engine._try_libreoffice(docx, tmp_path / "representative_lesson.pdf")

    assert _is_real_pdf(pdf), "LibreOffice did not produce a real PDF"
    assert pdf.stat().st_size > 20_000

    reader = pypdf.PdfReader(str(pdf))
    pages = [(page.extract_text() or "") for page in reader.pages]
    assert len(pages) >= 4, (
        f"representative multi-section lesson produced only {len(pages)} page(s)"
    )
    assert all(_normalise(page) for page in pages), (
        "conversion produced an empty page"
    )
    # The required three-line header (school / teacher / Week 1, Phase 5)
    # sits one line taller than the old two-line band, so the tight JHS form
    # can carry a SHORT TAIL page whose text is the form's own last line —
    # continuation, not truncation. The truncation guard is therefore the
    # completeness assertions below (every required sentence survives), not a
    # per-page character floor; a page may be short but never empty.
    assert all(len(_normalise(page)) >= 10 for page in pages), (
        "a page carries almost no readable text: "
        f"{[len(_normalise(p)) for p in pages]}"
    )

    page_text = [_normalise(page) for page in pages]
    full = _normalise(" ".join(pages))

    # Content that must survive the DOCX -> PDF layout, including the edited
    # teacher text and the Ghanaian/local-material context.
    required = [
        "CLASS / LEVEL: Basic 9",
        "Creative Arts",
        "Teacher-edited starter",
        "calabash",
        "kente",
        "GHS 2.50",
        "Teacher-edited conclusion",
        "property that makes it suitable",
        "Assessment Questions / Checks",
        "Marking Rubric for the Learner Task",
        "Total marks:",
        "not an official",
    ]
    for phrase in required:
        assert phrase in full, f"missing from converted PDF: {phrase!r}"

    # All four rubric bands survive (the legacy 3-band map used to mislabel
    # the top band while still printing four descriptor points).
    for band in (
        "exceeds the standard",
        "meets the standard",
        "developing",
        "needs support",
    ):
        assert band in full, f"missing rubric band: {band!r}"

    # Page ordering: cover -> main teaching -> assessment/rubric. Looking at
    # the first page that carries each marker proves content was not reordered
    # or collapsed into a single dump.
    def first_page(marker: str) -> int:
        for index, text in enumerate(page_text):
            if marker in text:
                return index
        raise AssertionError(f"marker never appeared: {marker!r}")

    cover = first_page("CLASS / LEVEL: Basic 9")
    main = first_page("PHASE 2: MAIN LEARNING")
    assessment = first_page("Assessment Questions / Checks")
    rubric = first_page("Marking Rubric for the Learner Task")
    assert cover <= main < assessment <= rubric, (
        "unexpected page order: "
        f"cover={cover}, main={main}, assessment={assessment}, rubric={rubric}"
    )

    # The final rubric note and the homework sentence are at the end of the
    # document; both being present proves the tail was not truncated.
    assert "not an official" in page_text[-1].lower()
    assert "property that makes it suitable" in full


def test_libreoffice_conversion_keeps_tables_readable(tmp_path, konverter_available):
    """The GES delivery grid survives as extractable, non-empty table text."""
    pypdf = pytest.importorskip("pypdf")
    from src.engines.docx_export import (
        DOCXExportEngine, default_template_for_lessons,
    )

    lp = _representative_lesson()
    docx = DOCXExportEngine().export_combined(
        [lp], default_template_for_lessons([lp]), tmp_path / "tables.docx")
    pdf = PDFExportEngine()._try_libreoffice(docx, tmp_path / "tables.pdf")

    reader = pypdf.PdfReader(str(pdf))
    full = _normalise(" ".join((p.extract_text() or "") for p in reader.pages))
    # Headers and cell content from the delivery grid, not just body prose.
    for header in ("PHASE 1", "PHASE 2", "PHASE 3", "TEACHER", "LEARNER"):
        assert header in full, f"table header missing after conversion: {header}"
    assert "duration" in full.lower() or "mins" in full.lower()

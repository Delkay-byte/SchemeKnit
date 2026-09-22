"""
Phase 16D: scanned / image-only PDFs fail honestly with useful diagnostics.

Root cause found in Phase 16: BASIC 8 TERM 1.pdf (a real district scheme) is a
fully scanned document — 45 pages, ZERO extractable characters. It is not a
layout bug; there is simply no text layer. The parser must:
  * surface an explicit machine-readable "no_text_layer" diagnostic (analyze),
  * attach an honest validation issue telling the user how to proceed (parse),
  * NEVER fabricate a subject, class level, or week count,
  * still extract a text-layer PDF rendered with materially different
    formatting (proving the fix is generic, not tuned to one file).
"""

import asyncio
from pathlib import Path

import fitz
import pytest

from src.models import ClassLevel, Subject, ValidationSeverity
from src.parsers.pdf_parser import PDFParser

REAL_DOCS = Path(__file__).parent.parent / "real_documents"
BASIC8_PDF = REAL_DOCS / "BASIC 8 TERM 1.pdf"


def _image_only_pdf(path: Path, pages: int = 2) -> Path:
    """A scanned-style PDF: pages with vector graphics but no text layer."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(fitz.Rect(40, 40, 520, 720), color=(0, 0, 0), width=1.5)
    doc.save(str(path))
    doc.close()
    return path


def _different_layout_pdf(path: Path) -> Path:
    """A text PDF with materially different formatting from the real fixtures:
    no ruled tables, no pipes — columns are separated by runs of two spaces and
    the content standard cell uses a single token code (different cell shapes).
    """
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    lines = [
        "BASIC 8 SCHEME OF LEARNING",
        "Grade: Basic 8",
        "SCIENCE",
        "Week Ending  Strand  Sub-Strand  Content Standard  Indicators",
        "1  08/09/2026  Diversity of Matter  Elements  B8.1.1.1.1  B8.1.1.1.1 Indicator one",
        "2  15/09/2026  Diversity of Matter  Elements  B8.1.2.1.1  B8.1.2.1.1 Indicator two",
    ]
    for line in lines:
        page.insert_text((50, y), line, fontsize=9)
        y += 14
    doc.save(str(path))
    doc.close()
    return path


# ── Synthetic image-only (no text layer) ─────────────────────────────────────

def test_image_only_pdf_analyzes_as_no_text_layer(tmp_path):
    path = _image_only_pdf(tmp_path / "scan.pdf")
    info = PDFParser().analyze(path)
    assert info["detection_status"] == "extraction_failed"
    assert info["extraction"]["reason"] == "no_text_layer"
    assert info["extraction"]["text_chars"] == 0
    assert info["extraction"]["blank_pages"] == 2


def test_image_only_pdf_parse_is_honest_failure(tmp_path):
    path = _image_only_pdf(tmp_path / "BASIC 8 MATHEMATICS scan.pdf")
    scheme = asyncio.run(PDFParser().parse(path))
    assert scheme.status == "extraction_failed"
    assert len(scheme.weeks) == 0
    # Class may be inferred from the filename; subject is NEVER fabricated.
    assert scheme.subject == Subject.UNKNOWN
    assert scheme.subject != Subject.MATHEMATICS
    error_issues = [vi for vi in scheme.validation_issues
                    if vi.severity == ValidationSeverity.ERROR]
    assert error_issues, "expected an ERROR validation issue on extraction"
    combined = " ".join(vi.message.lower() for vi in error_issues)
    assert "scanned" in combined or "image-only" in combined


# ── Real BASIC 8 scan (the Phase 16 reported failure) ────────────────────────

@pytest.mark.skipif(not BASIC8_PDF.exists(), reason="BASIC 8 PDF not found")
def test_real_basic8_scan_reports_no_text_layer():
    parser = PDFParser()
    info = parser.analyze(BASIC8_PDF)
    assert info["detection_status"] == "extraction_failed"
    assert info["extraction"]["reason"] == "no_text_layer"
    assert info["extraction"]["text_chars"] == 0
    assert info["extraction"]["blank_pages"] == 45

    scheme = asyncio.run(parser.parse(BASIC8_PDF))
    assert scheme.status == "extraction_failed"
    assert len(scheme.weeks) == 0
    # Never a fabricated B9 / Mathematics / non-zero week count.
    assert scheme.class_level != ClassLevel.BASIC_9
    assert scheme.subject != Subject.MATHEMATICS


# ── Generic: a text-layer PDF with different formatting still extracts ───────

def test_different_layout_text_pdf_still_extracts(tmp_path):
    path = _different_layout_pdf(tmp_path / "variant.pdf")
    scheme = asyncio.run(PDFParser().parse(path))
    assert scheme.status == "extracted"
    assert len(scheme.weeks) == 2
    assert scheme.subject == Subject.SCIENCE
    assert scheme.class_level == ClassLevel.BASIC_8
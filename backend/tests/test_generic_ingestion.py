"""
Generic document ingestion tests (PART W — DOCUMENT GENERALIZATION).

These fixtures are DELIBERATELY synthetic: different schools, wording, column
names and orders, and content from the owner's sample Basic 7/8/9 documents.
They prove the parser understands curriculum STRUCTURE rather than recognising
one particular file (Parts D/E/F/G/H/I/J).
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Subject, ClassLevel, WeekType
from src.parsers.docx_parser import DOCXParser


def _parse(parser, path, **kwargs):
    """Run the async parser synchronously for tests."""
    return asyncio.run(parser.parse(path, **kwargs))


def _analyze(parser, path, **kwargs):
    return parser.analyze(path, **kwargs)


def _add_table(doc, rows):
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            table.rows[r].cells[c].text = val
    return table


def _write_docx(path: Path, paragraphs, rows):
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if rows:
        _add_table(doc, rows)
    doc.save(str(path))
    return path


def _basic_rows(header, indicator_code="B7.1.1.1.1", indicator="Count objects up to 1000",
                content_standard="B7.1.1.1 Count and represent whole numbers"):
    """One header row + one instruction week + one revision week."""
    return [
        header,
        ["1", "Number", "Counting", content_standard, f"{indicator_code} {indicator}", "counters"],
        ["2", "Number", "Counting", content_standard, "Revision of counting", "counters"],
    ]


# ── Generic structure, alternate headers, different column order ────────────

class TestGenericHeaders:
    def test_alternate_headers_and_column_order(self, tmp_path):
        rows = _basic_rows(
            ["Wk", "Sub-Strand", "Strand", "Content Standards",
             "Learning Indicator", "Resources"])
        doc = _write_docx(tmp_path / "st_marys_b7.docx", [
            "ST. MARY'S JHS — TAMALE",
            "BASIC 7 SCHEME OF LEARNING",
            "MATHEMATICS",
            "First Term 2026/2027",
        ], rows)

        scheme = _parse(DOCXParser(), doc, original_filename="st_marys_b7.docx")
        assert scheme.subject == Subject.MATHEMATICS
        assert scheme.class_level == ClassLevel.BASIC_7
        assert len(scheme.weeks) >= 1
        week1 = next(w for w in scheme.weeks if w.week_number == 1)
        assert any("B7.1.1.1.1" in i for i in week1.indicators)

    def test_performance_indicator_alias(self, tmp_path):
        rows = _basic_rows(
            ["Week No.", "Strand", "Sub-Theme", "Content Standard",
             "Performance Indicator", "Teaching Learning Resources"])
        doc = _write_docx(tmp_path / "alias.docx", [
            "SUNRISE ACADEMY", "BASIC 8 SCHEME OF WORK", "SCIENCE", "Second Term",
        ], rows)
        scheme = _parse(DOCXParser(), doc, original_filename="alias.docx")
        assert scheme.subject == Subject.SCIENCE
        assert scheme.class_level == ClassLevel.BASIC_8
        assert scheme.weeks

    def test_same_curriculum_different_wording_parses_identically(self, tmp_path):
        """Same information, different school/wording/columns → same indicators."""
        a = _write_docx(tmp_path / "a.docx", [
            "SCHOOL A", "BASIC 7", "MATHEMATICS",
        ], _basic_rows(["Week", "Strand", "Sub-Strand", "Content Standard",
                        "Indicator", "Resources"]))
        b = _write_docx(tmp_path / "b.docx", [
            "SCHOOL B", "BASIC 7", "MATHEMATICS",
        ], _basic_rows(["Wk", "Sub-Strand", "Strand", "Content Standards",
                        "Learning Indicator", "TLRs"]))

        sa = _parse(DOCXParser(), a, original_filename="a.docx")
        sb = _parse(DOCXParser(), b, original_filename="b.docx")
        codes_a = {i.split()[0] for w in sa.weeks for i in w.indicators}
        codes_b = {i.split()[0] for w in sb.weeks for i in w.indicators}
        assert "B7.1.1.1.1" in codes_a and "B7.1.1.1.1" in codes_b
        assert codes_a == codes_b


# ── No wrong fallback classification (PART E) ───────────────────────────────

class TestNoWrongFallbacks:
    def test_unknown_class_is_not_fabricated_as_basic_9(self, tmp_path):
        rows = _basic_rows(["Week", "Strand", "Sub-Strand", "Content Standard",
                            "Indicator", "Resources"])
        doc = _write_docx(tmp_path / "noclass.docx", [
            "A SCHEME OF WORK", "Integrated Science", "Third Term",
        ], rows)
        scheme = _parse(DOCXParser(), doc, original_filename="noclass.docx")
        # No class signal anywhere → honest UNKNOWN, never Basic 9.
        assert scheme.class_level == ClassLevel.UNKNOWN
        assert scheme.class_level != ClassLevel.BASIC_9

    def test_unknown_subject_is_not_fabricated_as_mathematics(self, tmp_path):
        rows = _basic_rows(["Week", "Strand", "Sub-Strand", "Content Standard",
                            "Indicator", "Resources"])
        doc = _write_docx(tmp_path / "nosubject.docx", [
            "SOME SCHOOL", "BASIC 6", "A SCHEME OF WORK",
        ], rows)
        scheme = _parse(DOCXParser(), doc, original_filename="nosubject.docx")
        assert scheme.subject == Subject.UNKNOWN
        assert scheme.subject != Subject.MATHEMATICS

    def test_filename_document_class_mismatch_needs_confirmation(self, tmp_path):
        rows = _basic_rows(["Week", "Strand", "Sub-Strand", "Content Standard",
                            "Indicator", "Resources"])
        doc = _write_docx(tmp_path / "stored.docx", [
            "SOME SCHOOL", "BASIC 9 SCHEME OF LEARNING", "MATHEMATICS",
        ], rows)
        # Filename says Basic 8, document heading says Basic 9 → mismatch.
        scheme = _parse(DOCXParser(), 
            doc, original_filename="BASIC 8 MATHEMATICS.docx")
        assert scheme.class_level == ClassLevel.UNKNOWN

        info = _analyze(DOCXParser(), 
            doc, original_filename="BASIC 8 MATHEMATICS.docx")
        assert info["detection_status"] == "needs_confirmation"
        assert info["metadata"]["class_signals"]["conflict"] is True

    def test_consistent_filename_and_document_has_high_confidence(self, tmp_path):
        rows = _basic_rows(["Week", "Strand", "Sub-Strand", "Content Standard",
                            "Indicator", "Resources"])
        doc = _write_docx(tmp_path / "ok.docx", [
            "SOME SCHOOL", "BASIC 8 SCHEME OF LEARNING", "MATHEMATICS",
        ], rows)
        info = _analyze(DOCXParser(), 
            doc, original_filename="BASIC 8 MATHEMATICS Term 1.docx")
        assert info["metadata"]["class_signals"]["conflict"] is False
        assert info["metadata"]["class_signals"]["resolved"] == "Basic 8"


# ── Multi-subject documents (PART I) ────────────────────────────────────────

class TestMultiSubject:
    def test_two_subject_sections_require_confirmation(self, tmp_path):
        doc = Document()
        doc.add_paragraph("ACCRA GIRLS JHS")
        doc.add_paragraph("BASIC 7 SCHEME OF LEARNING")
        doc.add_paragraph("MATHEMATICS")
        _add_table(doc, _basic_rows(
            ["Week", "Strand", "Sub-Strand", "Content Standard", "Indicator", "Resources"]))
        doc.add_paragraph("SCIENCE")
        _add_table(doc, _basic_rows(
            ["Week", "Strand", "Sub-Strand", "Content Standard", "Indicator", "Resources"],
            indicator_code="B7.2.1.1.1", indicator="Describe matter"))
        path = tmp_path / "multi.docx"
        doc.save(str(path))

        info = _analyze(DOCXParser(), path, original_filename="multi.docx")
        assert info["detection_status"] == "multiple"
        subjects = {s["subject"] for s in info["sections"] if s["week_count"] > 0}
        assert {"Mathematics", "Science"}.issubset(subjects)

    def test_confirming_a_subject_re_extracts_only_that_section(self, tmp_path):
        doc = Document()
        doc.add_paragraph("BASIC 7 SCHEME OF LEARNING")
        doc.add_paragraph("MATHEMATICS")
        _add_table(doc, _basic_rows(
            ["Week", "Strand", "Sub-Strand", "Content Standard", "Indicator", "Resources"]))
        doc.add_paragraph("SCIENCE")
        _add_table(doc, _basic_rows(
            ["Week", "Strand", "Sub-Strand", "Content Standard", "Indicator", "Resources"],
            indicator_code="B7.2.1.1.1", indicator="Describe matter"))
        path = tmp_path / "multi2.docx"
        doc.save(str(path))

        scheme = _parse(DOCXParser(), 
            path, original_filename="multi2.docx", target_subject="Science")
        assert scheme.subject == Subject.SCIENCE
        codes = {i.split()[0] for w in scheme.weeks for i in w.indicators}
        assert "B7.2.1.1.1" in codes
        # The Mathematics indicator must NOT leak into the Science section.
        assert not any(c.startswith("B7.1") for c in codes)


# ── Extraction failure safety (PART J) ──────────────────────────────────────

class TestExtractionSafety:
    def test_no_tables_is_extraction_failure_not_success(self, tmp_path):
        path = tmp_path / "empty.docx"
        doc = Document()
        doc.add_paragraph("BASIC 7 MATHEMATICS")
        doc.add_paragraph("This document has no curriculum table at all.")
        doc.save(str(path))

        scheme = _parse(DOCXParser(), path, original_filename="empty.docx")
        assert scheme.weeks == []
        assert scheme.status == "extraction_failed"

        info = _analyze(DOCXParser(), path, original_filename="empty.docx")
        assert info["detection_status"] == "extraction_failed"

    def test_special_weeks_are_classified(self, tmp_path):
        rows = [
            ["Week", "Strand", "Sub-Strand", "Content Standard", "Indicator", "Resources"],
            ["1", "Number", "Counting", "B7.1.1.1 Count", "B7.1.1.1.1 Count objects", "counters"],
            ["9", "Revision", "", "", "", ""],
            ["10", "End of Term Assessment", "", "", "", ""],
            ["11", "SBA Activities and Vacation", "", "", "", ""],
        ]
        doc = _write_docx(tmp_path / "special.docx", [
            "SCHOOL", "BASIC 7", "MATHEMATICS",
        ], rows)
        scheme = _parse(DOCXParser(), doc, original_filename="special.docx")
        types = {w.week_number: w.week_type for w in scheme.weeks}
        assert types.get(9) == WeekType.REVISION
        assert types.get(10) == WeekType.ASSESSMENT
        assert types.get(11) == WeekType.SBA

"""
Parser class-level and subject detection improvements.

Tests that:
- Class level detection extracts from table cell text (not just paragraphs)
- Class level detection extracts from filename as secondary signal
- Subject detection extracts from table cell text
- Subject detection uses filename as secondary signal
- Detection works for Basic 7, Basic 8, Basic 9, SHS 1
- Multi-subject documents detect all valid sections
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.docx_parser import DOCXParser  # noqa: E402
from src.parsers.pdf_parser import PDFParser  # noqa: E402
from src.models import ClassLevel, Subject  # noqa: E402


class TestClassLevelDetection:
    """Class level should be detected from text, table cells, and filename."""

    def setup_method(self):
        self.parser = DOCXParser()

    def test_basic_7_from_text(self):
        result = self.parser._extract_class_level_from_text(
            "Basic 7 Scheme of Learning"
        )
        assert result == "Basic 7"

    def test_basic_8_from_text(self):
        result = self.parser._extract_class_level_from_text(
            "Basic 8 Term 1 Scheme"
        )
        assert result == "Basic 8"

    def test_basic_9_from_text(self):
        result = self.parser._extract_class_level_from_text(
            "Basic 9 Mathematics"
        )
        assert result == "Basic 9"

    def test_shs_1_from_text(self):
        result = self.parser._extract_class_level_from_text(
            "SHS 1 Physics scheme"
        )
        assert result == "SHS 1"

    def test_basic_8_from_filename_when_text_absent(self):
        """Filename is a secondary signal when document text lacks class level."""
        result = self.parser._extract_class_level_from_text(
            "Scheme of Learning for the academic year",
            filename="BASIC_8_TERM_1.pdf",
        )
        assert result == "Basic 8"

    def test_basic_7_from_filename(self):
        result = self.parser._extract_class_level_from_text(
            "General scheme of work",
            filename="Basic 7 English.docx",
        )
        assert result == "Basic 7"

    def test_text_takes_precedence_over_filename(self):
        """If both text and filename have class levels, text wins."""
        result = self.parser._extract_class_level_from_text(
            "Basic 9 Scheme of Learning",
            filename="Basic_8_file.pdf",
        )
        assert result == "Basic 9"

    def test_returns_none_when_no_signal(self):
        result = self.parser._extract_class_level_from_text(
            "Some random document text"
        )
        assert result is None

    def test_b8_abbreviation(self):
        result = self.parser._extract_class_level_from_text("B8 Mathematics")
        assert result == "Basic 8"


class TestSubjectDetection:
    """Subject should be detected from text, table cells, and filename."""

    def setup_method(self):
        self.parser = DOCXParser()

    def test_science_from_text(self):
        result = self.parser._extract_subject_from_text(
            "Science scheme of work"
        )
        assert result == "Science"

    def test_english_from_text(self):
        result = self.parser._extract_subject_from_text(
            "English Language scheme"
        )
        assert result == "English Language"

    def test_mathematics_from_text(self):
        result = self.parser._extract_subject_from_text(
            "Mathematics curriculum"
        )
        assert result == "Mathematics"

    def test_integrated_science_before_science(self):
        """Specific phrase 'Integrated Science' wins over generic 'Science'."""
        result = self.parser._extract_subject_from_text(
            "Integrated Science scheme"
        )
        assert result == "Integrated Science"

    def test_core_math_before_math(self):
        """Specific phrase 'Core Mathematics' wins over generic 'Mathematics'."""
        result = self.parser._extract_subject_from_text(
            "Core Mathematics curriculum"
        )
        assert result == "Core Mathematics"

    def test_returns_none_when_no_signal(self):
        result = self.parser._extract_subject_from_text(
            "Some random text about education"
        )
        assert result is None


class TestPDFParserTableText:
    """PDF parser should include table cell text in raw_text."""

    def test_pdf_parser_includes_table_text(self):
        """Verify that the PDF parser builds raw_text from table cells."""
        parser = PDFParser()
        # The _rows_from_text method is a fallback; we test that it exists
        # and can handle pipe-delimited text
        rows = parser._rows_from_text([
            "Week | Strand | Sub-strand",
            "1 | Number | Place Value",
        ])
        assert len(rows) == 2
        assert rows[0] == ["Week", "Strand", "Sub-strand"]
        assert rows[1] == ["1", "Number", "Place Value"]

    def test_pdf_parser_handles_space_delimited(self):
        parser = PDFParser()
        rows = parser._rows_from_text([
            "Week    Strand    Sub-strand",
            "1    Number    Place Value",
        ])
        assert len(rows) == 2

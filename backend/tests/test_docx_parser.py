"""
Comprehensive unit tests for the SchemeKnit DOCX Scheme Parser.

Tests cover:
1. Single-table scheme
2. Multi-table scheme
3. Repeated headers
4. Merged cells
5. Blank continuation cells
6. Multiple indicators under one week
7. Multiple indicators under one content standard
8. Week/date extraction
9. Invalid dates
10. Special weeks
11. Missing columns
12. Different header spellings
13. Unexpected/unknown rows
14. Empty documents
15. Documents containing no scheme table
16. Real uploaded Basic 9 Science scheme
17. Real uploaded Basic 9 Mathematics scheme
"""
import asyncio
import pytest
import re
from pathlib import Path
from datetime import date

from src.parsers.docx_parser import (
    DOCXParser, HEADER_ALIASES, WEEK_NUMBER_PATTERN,
    WEEK_ONLY_PATTERN, SPECIAL_WEEK_KEYWORDS
)
from src.models import WeekType, ValidationSeverity


FIXTURES_DIR = Path(r"C:\Users\SAVIOUR\Documents\DScience\Lesson Plan")
SCIENCE_FILE = FIXTURES_DIR / "BASIC 9 SCIENCE SCHEME OF LEARNING.docx"
MATH_FILE = FIXTURES_DIR / "BASIC 9 MATH SCHEME OF LEARNING.docx"


@pytest.fixture
def parser():
    return DOCXParser()


# ── Helper function ───────────────────────────────────────────────────────────

def run_parse(parser, file_path):
    return asyncio.run(parser.parse(Path(file_path)))


# ── 1 & 2: Single-table and multi-table schemes ──────────────────────────────

class TestMultiTableScheme:
    def test_science_has_15_weeks(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert len(result.weeks) == 15

    def test_math_has_15_weeks(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert len(result.weeks) == 15

    def test_science_week_numbers_are_sequential(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        nums = [w.week_number for w in result.weeks]
        assert nums == list(range(1, 16))

    def test_math_week_numbers_are_sequential(self, parser):
        result = run_parse(parser, MATH_FILE)
        nums = [w.week_number for w in result.weeks]
        assert nums == list(range(1, 16))


# ── 3: Repeated headers ──────────────────────────────────────────────────────

class TestRepeatedHeaders:
    def test_science_tables_have_headers(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        from docx import Document
        doc = Document(Path(SCIENCE_FILE))
        assert len(doc.tables) >= 3
        first_row_0 = [c.text.strip().lower() for c in doc.tables[0].rows[0].cells]
        assert "week ending" in first_row_0

    def test_math_tables_have_headers(self, parser):
        result = run_parse(parser, MATH_FILE)
        from docx import Document
        doc = Document(Path(MATH_FILE))
        assert len(doc.tables) >= 3
        for t in doc.tables:
            first_row = [c.text.strip().lower().replace('-', ' ').replace('_', ' ') for c in t.rows[0].cells]
            has_header = any("week" in c for c in first_row)
            assert has_header, f"Table missing header: {[c.text for c in t.rows[0].cells]}"


# ── 4: Merged cells ──────────────────────────────────────────────────────────

class TestMergedCells:
    def test_science_week_11_strand(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w11 = [w for w in result.weeks if w.week_number == 11]
        assert len(w11) == 1
        assert w11[0].strand == "Force and Energy"

    def test_math_week_11_strand(self, parser):
        result = run_parse(parser, MATH_FILE)
        w11 = [w for w in result.weeks if w.week_number == 11]
        assert len(w11) == 1
        assert "Geometry" in (w11[0].strand or "")


# ── 5: Blank continuation cells ──────────────────────────────────────────────

class TestContinuationRows:
    def test_math_week_1_has_2_indicators(self, parser):
        result = run_parse(parser, MATH_FILE)
        w1 = [w for w in result.weeks if w.week_number == 1][0]
        assert len(w1.indicators) == 2

    def test_math_week_4_has_3_indicators(self, parser):
        result = run_parse(parser, MATH_FILE)
        w4 = [w for w in result.weeks if w.week_number == 4][0]
        assert len(w4.indicators) == 3

    def test_math_week_6_has_3_indicators(self, parser):
        result = run_parse(parser, MATH_FILE)
        w6 = [w for w in result.weeks if w.week_number == 6][0]
        assert len(w6.indicators) == 3

    def test_math_week_8_has_2_indicators(self, parser):
        result = run_parse(parser, MATH_FILE)
        w8 = [w for w in result.weeks if w.week_number == 8][0]
        assert len(w8.indicators) == 2

    def test_math_week_4_has_3_content_standards(self, parser):
        result = run_parse(parser, MATH_FILE)
        w4 = [w for w in result.weeks if w.week_number == 4][0]
        assert len(w4.content_standards) >= 1

    def test_science_week_2_has_2_indicators(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w2 = [w for w in result.weeks if w.week_number == 2][0]
        assert len(w2.indicators) >= 1


# ── 6 & 7: Multiple indicators under one week/content standard ────────────────

class TestMultipleIndicators:
    def test_science_week_4_has_multiple_indicators(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w4 = [w for w in result.weeks if w.week_number == 4][0]
        assert len(w4.indicators) >= 1

    def test_science_week_11_has_multiple_indicators(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w11 = [w for w in result.weeks if w.week_number == 11][0]
        assert len(w11.indicators) >= 1

    def test_math_week_2_has_2_indicators(self, parser):
        result = run_parse(parser, MATH_FILE)
        w2 = [w for w in result.weeks if w.week_number == 2][0]
        assert len(w2.indicators) == 2


# ── 8: Week/date extraction ──────────────────────────────────────────────────

class TestWeekDateExtraction:
    def test_science_first_week_date(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w1 = [w for w in result.weeks if w.week_number == 1][0]
        assert w1.end_date == date(2026, 9, 11)

    def test_science_last_week_date(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w15 = [w for w in result.weeks if w.week_number == 15][0]
        assert w15.end_date == date(2026, 12, 18)

    def test_all_science_dates_are_valid(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        for w in result.weeks:
            assert w.end_date is not None, f"Week {w.week_number} has no date"
            assert isinstance(w.end_date, date)

    def test_all_math_dates_are_valid(self, parser):
        result = run_parse(parser, MATH_FILE)
        for w in result.weeks:
            assert w.end_date is not None, f"Week {w.week_number} has no date"
            assert isinstance(w.end_date, date)

    def test_science_week_dates_match_expected(self, parser):
        expected = [
            (1, date(2026, 9, 11)),
            (2, date(2026, 9, 18)),
            (3, date(2026, 9, 25)),
            (4, date(2026, 10, 2)),
            (5, date(2026, 10, 9)),
            (6, date(2026, 10, 16)),
            (7, date(2026, 10, 23)),
            (8, date(2026, 10, 30)),
            (9, date(2026, 11, 6)),
            (10, date(2026, 11, 13)),
            (11, date(2026, 11, 20)),
            (12, date(2026, 11, 27)),
            (13, date(2026, 12, 4)),
            (14, date(2026, 12, 11)),
            (15, date(2026, 12, 18)),
        ]
        result = run_parse(parser, SCIENCE_FILE)
        for week_num, expected_date in expected:
            w = [w for w in result.weeks if w.week_number == week_num][0]
            assert w.end_date == expected_date, \
                f"Week {week_num}: expected {expected_date}, got {w.end_date}"


# ── 9: Invalid dates ─────────────────────────────────────────────────────────

class TestInvalidDates:
    def test_parse_date_valid(self, parser):
        d = parser._parse_date("11/09/2026")
        assert d == date(2026, 9, 11)

    def test_parse_date_with_dashes(self, parser):
        d = parser._parse_date("11-09-2026")
        assert d == date(2026, 9, 11)

    def test_parse_date_with_dots(self, parser):
        d = parser._parse_date("11.09.2026")
        assert d == date(2026, 9, 11)

    def test_parse_date_invalid_month(self, parser):
        d = parser._parse_date("32/13/2026")
        assert d is None

    def test_parse_date_empty(self, parser):
        d = parser._parse_date("")
        assert d is None

    def test_parse_date_garbage(self, parser):
        d = parser._parse_date("not-a-date")
        assert d is None


# ── 10: Special weeks ────────────────────────────────────────────────────────

class TestSpecialWeeks:
    def test_science_week_13_is_revision(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w13 = [w for w in result.weeks if w.week_number == 13][0]
        assert w13.week_type == WeekType.REVISION

    def test_science_week_14_is_assessment(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w14 = [w for w in result.weeks if w.week_number == 14][0]
        assert w14.week_type == WeekType.ASSESSMENT

    def test_science_week_15_is_sba(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w15 = [w for w in result.weeks if w.week_number == 15][0]
        assert w15.week_type == WeekType.SBA

    def test_math_week_13_is_revision(self, parser):
        result = run_parse(parser, MATH_FILE)
        w13 = [w for w in result.weeks if w.week_number == 13][0]
        assert w13.week_type == WeekType.REVISION

    def test_math_week_14_is_assessment(self, parser):
        result = run_parse(parser, MATH_FILE)
        w14 = [w for w in result.weeks if w.week_number == 14][0]
        assert w14.week_type == WeekType.ASSESSMENT

    def test_math_week_15_is_sba(self, parser):
        result = run_parse(parser, MATH_FILE)
        w15 = [w for w in result.weeks if w.week_number == 15][0]
        assert w15.week_type == WeekType.SBA

    def test_special_week_count_science(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        special = [w for w in result.weeks if w.week_type != WeekType.INSTRUCTION]
        assert len(special) == 3

    def test_special_week_count_math(self, parser):
        result = run_parse(parser, MATH_FILE)
        special = [w for w in result.weeks if w.week_type != WeekType.INSTRUCTION]
        assert len(special) == 3

    def test_classify_revision(self, parser):
        assert parser._classify_special_week("REVISION") == WeekType.REVISION

    def test_classify_assessment(self, parser):
        assert parser._classify_special_week("END OF TERM ASSESSMENT") == WeekType.ASSESSMENT

    def test_classify_sba(self, parser):
        assert parser._classify_special_week("SBA ACTIVITIES AND VACATION") == WeekType.SBA


# ── 11: Missing columns ──────────────────────────────────────────────────────

class TestMissingColumns:
    def test_science_week_7_missing_strand(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w7 = [w for w in result.weeks if w.week_number == 7][0]
        assert w7.strand is None or w7.strand == ""

    def test_science_week_8_missing_strand(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w8 = [w for w in result.weeks if w.week_number == 8][0]
        assert w8.strand is None or w8.strand == ""


# ── 13: Unexpected/unknown rows ──────────────────────────────────────────────

class TestUnexpectedRows:
    def test_science_raw_tables_preserved(self, parser):
        from docx import Document
        doc = Document(Path(SCIENCE_FILE))
        assert len(doc.tables) >= 3

    def test_math_raw_tables_preserved(self, parser):
        from docx import Document
        doc = Document(Path(MATH_FILE))
        assert len(doc.tables) >= 3


# ── 14: Empty documents ──────────────────────────────────────────────────────

class TestEmptyDocuments:
    def test_empty_document_no_tables(self, parser):
        import tempfile
        from docx import Document

        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            doc = Document()
            doc.save(f.name)
            result = asyncio.run(parser.parse(Path(f.name)))

        assert len(result.weeks) == 0
        errors = [i for i in parser.validation_issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) > 0


# ── 15: Documents containing no scheme table ─────────────────────────────────

class TestNoSchemeTable:
    def test_document_with_text_only(self, parser):
        import tempfile
        from docx import Document

        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            doc = Document()
            doc.add_paragraph("This is just some random text about science")
            doc.add_paragraph("No tables here at all")
            doc.save(f.name)
            result = asyncio.run(parser.parse(Path(f.name)))

        assert len(result.weeks) == 0
        errors = [i for i in parser.validation_issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) > 0


# ── 16 & 17: Real uploaded schemes (regression fixtures) ─────────────────────

class TestRealScienceScheme:
    def test_subject(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert result.subject.value == "Science"

    def test_class_level(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert result.class_level.value == "Basic 9"

    def test_term(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert result.term == "First Term"

    def test_academic_year(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert result.academic_year == "2026/2027"

    def test_week_count(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        assert len(result.weeks) == 15

    def test_instructional_weeks(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        inst = [w for w in result.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(inst) == 12

    def test_week_1_structure(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w1 = [w for w in result.weeks if w.week_number == 1][0]
        assert w1.end_date == date(2026, 9, 11)
        assert w1.strand == "Diversity of Matter"
        assert w1.sub_strand == "Materials"
        assert len(w1.content_standards) >= 1
        assert len(w1.indicators) >= 1

    def test_week_6_structure(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w6 = [w for w in result.weeks if w.week_number == 6][0]
        assert w6.end_date == date(2026, 10, 16)
        assert w6.strand == "Cycle"
        assert w6.sub_strand == "Earth Science"

    def test_week_12_structure(self, parser):
        result = run_parse(parser, SCIENCE_FILE)
        w12 = [w for w in result.weeks if w.week_number == 12][0]
        assert w12.strand == "Humans and the Environment"
        assert w12.sub_strand == "Waste Management"

    def test_no_validation_errors(self, parser):
        run_parse(parser, SCIENCE_FILE)
        errors = [i for i in parser.validation_issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0

    def test_warnings_for_missing_strands(self, parser):
        run_parse(parser, SCIENCE_FILE)
        warnings = [i for i in parser.validation_issues if i.severity == ValidationSeverity.WARNING]
        strand_warnings = [w for w in warnings if "strand" in (w.field or "").lower()]
        assert len(strand_warnings) >= 2


class TestRealMathScheme:
    def test_subject(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert result.subject.value == "Mathematics"

    def test_class_level(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert result.class_level.value == "Basic 9"

    def test_term(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert result.term == "First Term"

    def test_academic_year(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert result.academic_year == "2026/2027"

    def test_week_count(self, parser):
        result = run_parse(parser, MATH_FILE)
        assert len(result.weeks) == 15

    def test_continuation_rows_week_1(self, parser):
        result = run_parse(parser, MATH_FILE)
        w1 = [w for w in result.weeks if w.week_number == 1][0]
        assert len(w1.indicators) == 2

    def test_continuation_rows_week_4(self, parser):
        result = run_parse(parser, MATH_FILE)
        w4 = [w for w in result.weeks if w.week_number == 4][0]
        assert len(w4.indicators) == 3

    def test_continuation_rows_week_6(self, parser):
        result = run_parse(parser, MATH_FILE)
        w6 = [w for w in result.weeks if w.week_number == 6][0]
        assert len(w6.indicators) == 3

    def test_continuation_rows_week_8(self, parser):
        result = run_parse(parser, MATH_FILE)
        w8 = [w for w in result.weeks if w.week_number == 8][0]
        assert len(w8.indicators) == 2

    def test_week_11_strand(self, parser):
        result = run_parse(parser, MATH_FILE)
        w11 = [w for w in result.weeks if w.week_number == 11][0]
        assert "Geometry" in (w11.strand or "")

    def test_week_12_strand(self, parser):
        result = run_parse(parser, MATH_FILE)
        w12 = [w for w in result.weeks if w.week_number == 12][0]
        assert "Geometry" in (w12.strand or "")

    def test_special_weeks(self, parser):
        result = run_parse(parser, MATH_FILE)
        special = [w for w in result.weeks if w.week_type != WeekType.INSTRUCTION]
        assert len(special) == 3

    def test_no_validation_errors(self, parser):
        run_parse(parser, MATH_FILE)
        errors = [i for i in parser.validation_issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0

    def test_instructional_weeks(self, parser):
        result = run_parse(parser, MATH_FILE)
        inst = [w for w in result.weeks if w.week_type == WeekType.INSTRUCTION]
        assert len(inst) == 12


# ── Regex pattern tests ──────────────────────────────────────────────────────

class TestRegexPatterns:
    def test_week_number_pattern_with_pipe(self):
        m = WEEK_NUMBER_PATTERN.search("1 | 11/09/2026")
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "11/09/2026"

    def test_week_number_pattern_with_newline(self):
        m = WEEK_NUMBER_PATTERN.search("1\n11/09/2026")
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "11/09/2026"

    def test_week_number_pattern_with_cr(self):
        m = WEEK_NUMBER_PATTERN.search("1\r11/09/2026")
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "11/09/2026"

    def test_week_number_pattern_two_digit(self):
        m = WEEK_NUMBER_PATTERN.search("15\n18/12/2026")
        assert m
        assert m.group(1) == "15"
        assert m.group(2) == "18/12/2026"

    def test_week_number_pattern_no_match_text(self):
        m = WEEK_NUMBER_PATTERN.search("REVISION")
        assert m is None

    def test_week_only_pattern(self):
        m = WEEK_ONLY_PATTERN.match("1")
        assert m
        assert m.group(1) == "1"

    def test_week_only_pattern_no_match(self):
        m = WEEK_ONLY_PATTERN.match("hello")
        assert m is None

    def test_special_week_keywords(self):
        for kw in ["revision", "end of term assessment", "sba activities and vacation"]:
            assert any(kw in sk for sk in SPECIAL_WEEK_KEYWORDS)


# ── Header detection tests ───────────────────────────────────────────────────

class TestHeaderDetection:
    def test_valid_header(self, parser):
        row = ["WEEK ENDING", "STRAND", "SUB-STRAND", "CONTENT STANDARD", "INDICATORS", "RESOURCES"]
        result = parser._detect_header(row)
        assert result is not None
        assert "week_ending" in result
        assert "strand" in result
        assert "sub_strand" in result

    def test_header_with_different_spelling(self, parser):
        row = ["WEEK", "STRAND", "SUB STRAND", "CONTENT STANDARDS", "INDICATOR", "RESOURCE"]
        result = parser._detect_header(row)
        assert result is not None
        assert "week_ending" in result

    def test_insufficient_headers(self, parser):
        row = ["WEEK ENDING", "STRAND", "random", "data", "here", "there"]
        result = parser._detect_header(row)
        assert result is None

    def test_no_headers(self, parser):
        row = ["1\n11/09/2026", "Number", "Some topic", "Content", "Indicator", "Resource"]
        result = parser._detect_header(row)
        assert result is None


# ── Class detection tests ────────────────────────────────────────────────────

class TestClassDetection:
    def test_detect_basic_9(self, parser):
        assert parser._extract_class_level_from_text("FIRST TERM SCHEME - B9 SCIENCE") == "Basic 9"

    def test_detect_basic_8(self, parser):
        assert parser._extract_class_level_from_text("Basic 8 Mathematics") == "Basic 8"

    def test_detect_shs_1(self, parser):
        assert parser._extract_class_level_from_text("SHS 1 Chemistry") == "SHS 1"

    def test_detect_none(self, parser):
        assert parser._extract_class_level_from_text("Random text") is None


# ── Subject detection tests ──────────────────────────────────────────────────

class TestSubjectDetection:
    def test_detect_science(self, parser):
        assert parser._extract_subject_from_text("B9 SCIENCE") == "Science"

    def test_detect_math(self, parser):
        assert parser._extract_subject_from_text("B9 MATHEMATICS") == "Mathematics"

    def test_detect_maths(self, parser):
        assert parser._extract_subject_from_text("B9 MATHS") == "Mathematics"

    def test_detect_none(self, parser):
        assert parser._extract_subject_from_text("Random text") is None

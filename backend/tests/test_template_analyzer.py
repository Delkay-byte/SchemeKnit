"""
Tests for the deterministic sample-template analyzer.
Uses synthetic DOCX fixtures (hermetic) plus the real teacher sample when present.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docx import Document
from docx.oxml.ns import qn

from src.engines.template_analyzer import (
    analyze_docx_sample,
    detect_field,
    split_label_value,
    normalize_label,
    TEACHFLOW_FIELDS,
)

REAL_SAMPLE = r"C:\Users\SAVIOUR\SchemeKnit_web_acceptance\BASIC 9 SCIENCE SAMPLE WEEK 2.docx"


def make_sample_docx(path: str):
    """Build a small teacher-style sample: metadata grid + phases + unknown field."""
    doc = Document()
    doc.add_paragraph("WEEK 2")
    table = doc.add_table(rows=4, cols=4)
    # Row 0: merged label:value cells
    table.cell(0, 0).text = "Date: 01/05/2026"
    table.cell(0, 1).text = "Date: 01/05/2026"
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(0, 2).text = "Subject: Science"
    table.cell(0, 3).text = "Subject: Science"
    table.cell(0, 2).merge(table.cell(0, 3))
    # Row 1
    table.cell(1, 0).text = "Class: B7"
    table.cell(1, 1).text = "Class Size: 24"
    table.cell(1, 2).text = "Strand: Forces & Energy"
    table.cell(1, 3).text = "Sub Strand: Energy"
    # Row 2: content + unknown custom field
    table.cell(2, 0).text = "Content Standard:\nB7.4.3.1 Demonstrate"
    table.cell(2, 1).text = "Indicator:\nB7.4.3.1.2 Demonstrate the"
    table.cell(2, 2).text = "Period: 4th"
    table.cell(2, 3).text = "Teaching Method: Demonstration"
    # Row 3: phase marker row
    table.cell(3, 0).text = "PHASE 1: STARTER"
    table.cell(3, 1).text = "Revise previous lesson"
    table.cell(3, 2).text = "PHASE 2: MAIN"
    table.cell(3, 3).text = "Present new content"
    doc.save(path)
    return path


@pytest.fixture()
def sample_path(tmp_path):
    p = str(tmp_path / "sample.docx")
    make_sample_docx(p)
    return p


def test_normalize_label():
    assert normalize_label("Date:") == "date"
    assert normalize_label("  Content   Standard: ") == "content standard"
    assert normalize_label("Sub-Strand") == "sub-strand"


def test_split_label_value():
    assert split_label_value("Date: 01/05/2026") == ("Date", "01/05/2026")
    assert split_label_value("Content Standard:\nB7.4.3.1 Demo") == ("Content Standard", "B7.4.3.1 Demo")
    assert split_label_value("References: / Science Pg. 3") == ("References", "Science Pg. 3")
    assert split_label_value("Just some prose without colon") == (None, "Just some prose without colon")
    assert split_label_value("") == (None, "")
    assert split_label_value("Date:") == ("Date", "")


def test_detect_field_exact_and_alias():
    assert detect_field("Date")["field"] == "lesson_date"
    assert detect_field("Date")["confidence"] == "high"
    assert detect_field("Lesson Date")["field"] == "lesson_date"
    assert detect_field("Content Standards")["field"] == "content_standard"
    assert detect_field("Sub Strand")["field"] == "sub_strand"
    assert detect_field("Class Size")["field"] == "class_size"
    assert detect_field("Performance Indicator")["field"] == "learning_objectives"


def test_detect_field_unknown_preserved_as_custom():
    det = detect_field("Teaching Method")
    assert det["field"] is None
    assert det["custom"] is True
    assert det["confidence"] == "manual"
    det2 = detect_field("Period")
    assert det2["custom"] is True


def test_analyze_tables_and_merges(sample_path):
    struct = analyze_docx_sample(sample_path)
    assert struct["meta"]["table_count"] == 1
    t = struct["tables"][0]
    assert t["rows"] == 4
    # merged Date cell spans 2 grid columns
    date_cells = [c for c in t["cells"] if c["label"] == "Date"]
    assert date_cells and date_cells[0]["colspan"] == 2
    assert date_cells[0]["field"] == "lesson_date"


def test_analyze_mappings_include_custom(sample_path):
    struct = analyze_docx_sample(sample_path)
    by_label = {m["label"]: m for m in struct["mappings"]}
    assert by_label["Subject"]["field"] == "subject"
    assert by_label["Teaching Method"]["custom"] is True
    assert by_label["Teaching Method"]["field"] is None
    assert by_label["Period"]["custom"] is True


def test_analyze_phase_markers_not_fields(sample_path):
    struct = analyze_docx_sample(sample_path)
    labels = [m["label"] for m in struct["mappings"]]
    assert not any("PHASE" in (label or "").upper() for label in labels)


def test_analyze_detects_jhs_level(sample_path):
    struct = analyze_docx_sample(sample_path)
    # 'B7' alone is not a level keyword; default family applies wiehoue crash
    assert struct["detected_family"] in ("early_childhood", "primary", "jhs", "shs")


def test_analyze_malformed_raises(tmp_path):
    bad = str(tmp_path / "bad.docx")
    with open(bad, "wb") as f:
        f.write(b"not a zip file")
    with pytest.raises(ValueError):
        analyze_docx_sample(bad)


def test_analyze_empty_raises(tmp_path):
    empty = str(tmp_path / "empty.docx")
    Document().save(empty)
    with pytest.raises(ValueError):
        analyze_docx_sample(empty)


def test_field_vocabulary_covers_rendering():
    for f in ["school_name", "teacher_name", "lesson_date", "strand", "indicators",
              "assessment", "conclusion", "introduction", "references"]:
        assert f in TEACHFLOW_FIELDS


@pytest.mark.skipif(not os.path.exists(REAL_SAMPLE), reason="real teacher sample not staged")
def test_real_teacher_sample():
    struct = analyze_docx_sample(REAL_SAMPLE)
    assert struct["meta"]["table_count"] >= 2
    by_label = {m["label"]: m for m in struct["mappings"]}
    # Real labels from the JHc science sample
    assert by_label["Date"]["field"] == "lesson_date"
    assert by_label["Subject"]["field"] == "subject"
    assert by_label["Strand"]["field"] == "strand"
    assert by_label["Content Standard"]["field"] == "content_standard"
    assert by_label["Indicator"]["field"] == "indicators"
    assert by_label["References"]["field"] == "references"
    assert by_label["Period"]["custom"] is True
    # merged meeadaea cells deeeceed
    spans = [c["colspan"] for t in struct["tables"] for c in t["cells"]]
    assert max(spans) >= 2

"""Source-accurate week mapping for the actual Basic 9 Science scheme.

The source has three Word tables, one schedule row per numbered week, and
vertical merges for shared strand / sub-strand / content-standard cells. The
schedule ROW (not the indicator count) is the weekly unit.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.parsers.docx_parser import DOCXParser

SOURCE = (os.path.join(os.path.dirname(__file__), "..", "real_documents",
                       "BASIC 9 SCIENCE SCHEME OF LEARNING.docx"))

pytestmark = pytest.mark.skipif(
    not os.path.exists(SOURCE),
    reason="source scheme fixture is not available",
)


def _parse():
    from pathlib import Path
    return asyncio.run(DOCXParser().parse(Path(SOURCE), []))


@pytest.fixture(scope="module")
def parsed():
    return _parse()


def _week(parsed, number):
    return next(w for w in parsed.weeks if w.week_number == number)


def test_all_fifteen_source_weeks_are_present_in_order(parsed):
    assert [w.week_number for w in parsed.weeks] == list(range(1, 16))


def test_week_ending_dates_match_the_source(parsed):
    expected = {
        1: "2026-09-11", 2: "2026-09-18", 3: "2026-09-25",
        4: "2026-10-02", 5: "2026-10-09", 6: "2026-10-16",
        9: "2026-11-06", 10: "2026-11-13", 11: "2026-11-20",
        12: "2026-11-27", 13: "2026-12-04", 14: "2026-12-11",
        15: "2026-12-18",
    }
    for number, day in expected.items():
        assert str(_week(parsed, number).end_date) == day


def test_week_two_is_one_row_with_two_indicators(parsed):
    week = _week(parsed, 2)
    assert len(week.indicators) == 2
    joined = " | ".join(week.indicators)
    assert "B9.1.1.1.2 Discuss the formation of binary chemical compounds" in joined
    assert "B9.1.1.1.3 Describe the characteristics of common acids, bases and salts" in joined
    # Each indicator carries only its own text (no concatenated remainder).
    for text in week.indicators:
        assert text.count("Discuss the formation") <= 1
        assert text.count("Describe the characteristics") <= 1


def test_weeks_one_and_two_share_a_content_standard_without_merging(parsed):
    w1, w2 = _week(parsed, 1), _week(parsed, 2)
    assert w1.content_standards[0].startswith("B9.1.1.1")
    assert w2.content_standards[0].startswith("B9.1.1.1")
    assert w1.week_number != w2.week_number


def test_week_three_keeps_its_own_standard_and_indicator(parsed):
    w3 = _week(parsed, 3)
    assert w3.content_standards[0].startswith("B9.1.1.2")
    assert w3.indicators[0].startswith("B9.1.1.2.1")
    assert "B9.1.1.1.2" not in " ".join(w3.indicators)


def test_weeks_four_and_five_stay_distinct_though_they_share_a_standard(parsed):
    w4, w5 = _week(parsed, 4), _week(parsed, 5)
    assert w4.content_standards[0].startswith("B9.1.2.1")
    assert w5.content_standards[0].startswith("B9.1.2.1")
    assert len(w4.indicators) == 2
    assert w4.indicators[0].startswith("B9.1.2.1.1")
    assert w4.indicators[1].startswith("B9.1.2.1.2")
    assert w5.indicators[0].startswith("B9.1.2.1.3")


def test_weeks_nine_and_ten_stay_distinct_though_they_share_a_standard(parsed):
    w9, w10 = _week(parsed, 9), _week(parsed, 10)
    assert w9.content_standards[0].startswith("B9.3.1.1")
    assert w10.content_standards[0].startswith("B9.3.1.1")
    assert w9.indicators[0].startswith("B9.3.1.1.1")
    assert w10.indicators[0].startswith("B9.3.1.1.2")


def test_week_eleven_keeps_both_content_standards_in_one_week(parsed):
    w11 = _week(parsed, 11)
    joined = " ".join(w11.content_standards)
    assert "B9.4.1.1" in joined and "B9.4.1.2" in joined
    assert len(w11.indicators) >= 6


def test_special_weeks_keep_their_classification(parsed):
    assert _week(parsed, 13).week_type.value == "revision"
    assert _week(parsed, 14).week_type.value == "assessment"
    assert _week(parsed, 15).week_type.value == "sba"


def test_source_anomaly_in_weeks_seven_and_eight_is_preserved(parsed):
    """The source repeats B9.2.3.2 in Week 7's content standard and repeats the
    B9.2.3.2.1 indicator code across Weeks 7 and 8. Neither row may be moved or
    invented; the anomaly is reported for review."""
    w7, w8 = _week(parsed, 7), _week(parsed, 8)
    assert "B9.2.3.1.1" in " ".join(w7.indicators)
    assert "B9.2.3.2.1" in " ".join(w7.indicators)
    assert "B9.2.3.2.2" in " ".join(w8.indicators)
    assert "B9.2.3.2.1" in " ".join(w8.indicators)


def test_merged_cells_do_not_create_or_drop_weeks(parsed):
    # Weeks 1-3 share the strand; 1-2 share the content standard; 4-5 share one.
    for number in (1, 2, 3):
        assert _week(parsed, number).strand  # inherited, never blank
    assert len({w.week_number for w in parsed.weeks}) == 15


def test_no_indicator_is_moved_to_an_adjacent_week(parsed):
    mapping = {
        1: ["B9.1.1.1.1"],
        2: ["B9.1.1.1.2", "B9.1.1.1.3"],
        3: ["B9.1.1.2.1"],
        4: ["B9.1.2.1.1", "B9.1.2.1.2"],
        5: ["B9.1.2.1.3"],
        6: ["B9.2.1.1.1", "B9.2.1.1.2"],
        9: ["B9.3.1.1.1"],
        10: ["B9.3.1.1.2"],
    }
    for number, codes in mapping.items():
        joined = " ".join(_week(parsed, number).indicators)
        for code in codes:
            assert code in joined, (number, code)

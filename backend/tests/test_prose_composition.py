"""Deterministic lesson prose must not expose composition artefacts.

Real scheme cells print ``"B6.1.3.1.1 : Relate … experiences."`` or fragmented
multi-sentence ICT cells (``"… techniques. . Summarise …"``). The builder used
the raw cleaned cell as ``{focus}``/``{skill}`` inside templates that add their
own punctuation, producing visible defects:

  * ``"… personal experiences.. Read it aloud"``  (double full stop)
  * ``"… keyboarding techniques. . Summarise"``   (space-dot-dot)
  * ``"… model/example of: Relate …"``            (leading separator)
  * topic strings beginning with ``": "``

The fix is at the composition boundary — sanitise the focus phrase and
collapse dotted artefacts in the mechanical prose normaliser — not a global
rewrite of lesson text.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.curriculum.lesson_builder import (  # noqa: E402
    PLENARY_MODE_TEMPLATES, _normalize_prose, build_lesson,
)
from src.models import (  # noqa: E402
    AIMode, AllocatedIndicator, ClassLevel, Subject, TermConfig,
)

DOUBLE_PERIOD = re.compile(r"\.\s*\.")


def _config(subject, class_level):
    return TermConfig(
        scheme_of_work_id="probe", academic_year="2026/2027",
        term="First Term", class_level=class_level, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60, teaching_days=[0],
        holidays=[], ai_mode=AIMode.OFF, school_name="S", teacher_name="T",
    )


def _lesson(subject, class_level, code, description, strand, sub_strand):
    alloc = AllocatedIndicator(
        indicator_code=code, indicator_description=description,
        content_standard_code="CS", content_standard_description="CS",
        strand=strand, sub_strand=sub_strand, week_number=1,
        source_resources=[], lesson_date=date(2026, 9, 7),
        period_index=1, allocated=True, teaching_week=1,
    )
    return build_lesson(alloc, _config(subject, class_level), "probe")


#: Source-verbatim fields: the scheme's own cell text is preserved exactly
#: (including its defects) so the teacher can audit provenance.
_VERBATIM_KEYS = {"indicators", "content_standard"}


def _strings(value, key=None):
    if isinstance(value, str):
        if key not in _VERBATIM_KEYS:
            yield value
    elif isinstance(value, dict):
        for name, item in value.items():
            yield from _strings(item, name)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item, key)


ENGLISH = (
    Subject.ENGLISH, ClassLevel.BASIC_6, "B6.1.3.1.1",
    "B6.1.3.1.1 : Relate the central messages of poems to personal "
    "experiences.",
    "Reading", "Poetry",
)
ICT = (
    Subject.ICT, ClassLevel.BASIC_6, "B6.1.1.1.4",
    "B6.1.1.1.4 . Demonstrate proper use of keyboarding techniques. . "
    "Summarise the generations of computers (second generation of computers)",
    "Introduction to Computing", "Keyboarding",
)


@pytest.mark.parametrize("case", [ENGLISH, ICT], ids=["english", "ict"])
def test_lesson_text_has_no_dotted_artefacts(case):
    lp = _lesson(*case)
    for text in _strings(lp.model_dump(mode="json")):
        assert not DOUBLE_PERIOD.search(text), (
            f"double period leaked into lesson prose: {text!r}")


def test_english_focus_drops_separator_and_terminal_period():
    lp = _lesson(*ENGLISH)
    assert not lp.lesson_topic.startswith(":")
    for text in _strings(lp.model_dump(mode="json")):
        assert "model/example of:" not in text
        assert "of: Relate" not in text


def test_ict_topic_does_not_begin_with_a_bare_dot():
    lp = _lesson(*ICT)
    assert not re.match(r"^[.:;,\s]", lp.lesson_topic), lp.lesson_topic


def test_normalize_prose_collapses_double_periods():
    assert _normalize_prose("techniques. . Summarise") == "techniques. Summarise"
    assert _normalize_prose("experiences.. Read") == "experiences. Read"


def test_plenary_agreement_grammar_is_fixed_at_source():
    report = PLENARY_MODE_TEMPLATES["report_findings"]
    assert "agrees the strongest evidence" not in report
    assert "agrees on the strongest evidence" in report
    minute = PLENARY_MODE_TEMPLATES["one_minute_summary"]
    assert "agrees the best statement" not in minute
    assert "agrees on the best statement" in minute

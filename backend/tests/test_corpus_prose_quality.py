"""Corpus-wide prose regression for the deterministic lesson builder.

The rubric can score a lesson highly while its prose is broken ("... up to
100,000 to the nearest and state ...", "learners investigate Investigate ...").
These assertions run the three frozen corpora through the REAL generation
pipeline (AI OFF) and reject malformed composition artefacts in every
teacher-visible composed field.

Source-verbatim fields (indicators, content standards, source resources) are
excluded: the builder must never rewrite curriculum text it was given.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests import benchmark_deterministic_lessons as deterministic  # noqa: E402
from tests import benchmark_hardening as hardening  # noqa: E402

#: Fields that echo the teacher's source cell verbatim. A defect there is the
#: source's, not the builder's, so they are not scanned as composed prose.
VERBATIM_KEYS = {
    "indicators", "indicator", "content_standard", "content_standard_description",
    "content_standard_code", "source_tlrs", "provenance", "source_occurrence_id",
    "lesson_topic_source", "original_data",
}

PATTERNS = {
    "double_period": re.compile(r"\.\s*\."),
    "space_before_punctuation": re.compile(r"\s+[,.;:!?]"),
    "stray_separator": re.compile(r"\.\s*[:;]"),
    "empty_parentheses": re.compile(r"\(\s*\)"),
    "empty_colon": re.compile(r":\s*[.;]"),
    "double_comma": re.compile(r",\s*,"),
    "double_semicolon": re.compile(r";\s*;"),
    "placeholder": re.compile(r"\b(?:TODO|TBD|None|undefined|null)\b"),
    "repeated_word": re.compile(r"\b(\w{3,})\s+\1\b", re.IGNORECASE),
    "dangling_connector_before_conjunction": re.compile(
        r"\b(?:to|the|of|for|with|between)\s+(?:and|or)\b", re.IGNORECASE),
    "unfinished_determiner": re.compile(
        r"\b(?:the\s+nearest|the\s+next|the\s+following)\s+(?:and|or)\b",
        re.IGNORECASE),
}


def _composed_strings(value, key=None):
    if isinstance(value, str):
        if key not in VERBATIM_KEYS:
            yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _composed_strings(v, k)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _composed_strings(v, key)
    elif hasattr(value, "model_dump"):
        yield from _composed_strings(value.model_dump(mode="json"), key)


def _corpora():
    return {
        "deterministic": deterministic.run_generation(),
        "expanded": hardening.run_generation(hardening.CORPUS),
        "messy": hardening.run_generation(hardening.MESSY_CORPUS),
    }


def test_frozen_corpora_have_no_composition_artefacts():
    findings = []
    for corpus, pairs in _corpora().items():
        for entry, lesson in pairs:
            for text in _composed_strings(lesson):
                for name, pattern in PATTERNS.items():
                    match = pattern.search(text)
                    if match:
                        findings.append(
                            f"{corpus}/{entry.get('code')} {entry.get('subject')}: "
                            f"{name} {match.group(0)!r} in {text[:180]!r}"
                        )
    assert not findings, "\n".join(findings)


def test_truncated_focus_never_ends_on_a_dependent_adjective():
    """A max-word cut must not leave "... to the nearest" before "and"."""
    from src.curriculum.lesson_builder import _first_clause

    indicator = (
        "B6.1.1.1.5 : Round (off, up, down) whole numbers up to 100,000 "
        "to the nearest ten thousand, thousands, hundreds, and tens."
    )
    focus = _first_clause(indicator)
    assert not re.search(r"\b(?:nearest|next|following)\s*$", focus, re.I), focus
    assert focus.endswith("100,000"), focus

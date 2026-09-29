"""
SchemeKnit Official-Curriculum Exemplar Corpus
==============================================

A **versioned, derived** pedagogical corpus built from the official NaCCA
Common Core Programme (CCP) curricula for Basic 7–9.

What this is
------------
Each record stores *derived structured pedagogical information* about ONE
curriculum indicator — the action verbs the official exemplars imply, a short
derived learning focus, teacher-ready activity patterns, assessment patterns,
assignment patterns and resource patterns. It does **not** store the official
document's prose: the exemplar lists were read and transformed, not copied, so
no page of a NaCCA document is reproduced here.

Provenance is mandatory on every record
---------------------------------------
Every record carries ``source_title``, ``source_url``, ``source_version`` and a
``provenance`` note. A record is only ever attached to a NaCCA source when that
source was actually read for that indicator. Where official exemplar detail was
not available in a usable form the record is simply absent, and the deterministic
planner falls back to the teacher's scheme plus the bounded subject pedagogy —
never to a fabricated "official exemplar".

Lookup
------
``lookup_indicator(code)`` / ``lookup_content_standard(code)`` normalize the many
code shapes the real curricula use (``B7.1.1.1.1``, ``B7/JHS1.1.1.1.1``,
``B7/JHS1 1.1.1.1``) onto one canonical key, so a scheme that prints codes only
still resolves to real curriculum evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = [
    "ExemplarRecord",
    "normalize_code",
    "lookup_indicator",
    "lookup_content_standard",
    "all_records",
    "subject_of",
    "CORPUS_VERSION",
]

#: Bumped whenever records are added, corrected or removed. Stored so a lesson
#: can record which corpus revision grounded it.
CORPUS_VERSION = "2026.09-1"


@dataclass(frozen=True)
class ExemplarRecord:
    """Derived pedagogical evidence for one official curriculum indicator.

    ``level`` is the curriculum level the record was derived for (e.g. "B7").
    ``strand`` / ``sub_strand`` are the official organizing names, stored
    because a code-only scheme usually still prints them — they let the planner
    reach the right record from document evidence alone.
    """

    subject: str
    level: str
    strand: str
    sub_strand: str
    content_standard_code: str
    indicator_code: str
    #: Short derivative of the official indicator — what the lesson is ABOUT.
    learning_focus: str
    #: Action verbs the official exemplar(s) actually require.
    curriculum_action_verbs: List[str] = field(default_factory=list)
    #: Teacher-ready activity structures derived from the exemplars.
    exemplar_activity_patterns: List[str] = field(default_factory=list)
    assessment_patterns: List[str] = field(default_factory=list)
    assignment_patterns: List[str] = field(default_factory=list)
    class_assignment_pattern: str = ""
    home_assignment_pattern: str = ""
    suitable_resource_patterns: List[str] = field(default_factory=list)
    #: Concrete curriculum terms for keyword seeding (never generic nouns).
    focus_terms: List[str] = field(default_factory=list)
    core_competencies: List[str] = field(default_factory=list)
    #: Mandatory provenance.
    source_title: str = ""
    source_url: str = ""
    source_version: str = ""
    provenance: str = ""


# ── Code normalization ────────────────────────────────────────────────────────

_LEVEL_RE = re.compile(r"^(B?\d+)\s+")


def normalize_code(raw: str) -> str:
    """Canonical key for any of the curricula's code shapes.

    ``B7.1.1.1.1`` → ``B7.1.1.1.1``
    ``B7/JHS1.1.1.1.1`` → ``B7.1.1.1.1``
    ``B7/JHS1 1.1.1.1`` → ``B7.1.1.1``
    ``b7.1.1.1.1`` → ``B7.1.1.1.1``
    """
    s = (raw or "").upper()
    s = re.sub(r"/JHS\d", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _LEVEL_RE.sub(r"\1.", s)
    s = s.replace(" ", "")
    s = re.sub(r"[^0-9A-Z.]", "", s)
    s = re.sub(r"\.{2,}", ".", s).strip(".")
    return s


# ── Registry ────────────────────────────────────────────────────────────────
#
# Indicator codes are NOT globally unique: B7.1.1.1.1 is the first indicator of
# Strand 1 in Computing, Mathematics AND Physical Education and Health. The index
# is therefore keyed by (subject, code) so a lookup can never return another
# subject's curriculum evidence.

_INDICATOR_INDEX: Dict[tuple, ExemplarRecord] = {}
_CONTENT_STANDARD_INDEX: Dict[tuple, ExemplarRecord] = {}
_INDICATOR_BY_CODE: Dict[str, List[ExemplarRecord]] = {}
_LOADED = False

#: Names a real scheme or the subject catalogue may use for each corpus subject.
SUBJECT_ALIASES: Dict[str, str] = {
    "computing": "computing",
    "ict": "computing",
    "information and communication technology": "computing",
    "mathematics": "mathematics",
    "core mathematics": "mathematics",
    "elective mathematics": "mathematics",
    "numeracy": "mathematics",
    "maths": "mathematics",
    "science": "science",
    "integrated science": "science",
    "english language": "english language",
    "english": "english language",
    "religious and moral education": "religious and moral education",
    "rme": "religious and moral education",
    "social studies": "social studies",
    "social studies (jhs)": "social studies",
    "career technology": "career technology",
    "creative arts and design": "creative arts and design",
    "creative arts": "creative arts and design",
    "physical education and health": "physical education and health",
    "physical and health education": "physical education and health",
    "phe": "physical education and health",
}


def _subject_key(subject: str) -> str:
    """Canonical corpus subject name for a scheme's subject label (or '')."""
    name = " ".join((subject or "").split()).strip().lower()
    if not name:
        return ""
    if name in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[name]
    # A longer official label that merely contains a known name.
    for alias, canonical in SUBJECT_ALIASES.items():
        if alias in name:
            return canonical
    return name


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    from . import (
        career_technology,
        computing,
        creative_arts,
        english,
        mathematics,
        phe,
        rme,
        science,
        social_studies,
    )

    for module in (computing, mathematics, science, english, rme,
                   career_technology, creative_arts, phe, social_studies):
        for record in getattr(module, "RECORDS", []):
            subject = _subject_key(record.subject)
            key = normalize_code(record.indicator_code)
            if key and subject:
                _INDICATOR_INDEX.setdefault((subject, key), record)
                _INDICATOR_BY_CODE.setdefault(key, []).append(record)
            cs_key = normalize_code(record.content_standard_code)
            if cs_key and subject:
                _CONTENT_STANDARD_INDEX.setdefault((subject, cs_key), record)
    _LOADED = True


def all_records() -> List[ExemplarRecord]:
    """Every loaded record (used by tests and the corpus coverage report)."""
    _load()
    seen = set()
    out: List[ExemplarRecord] = []
    for record in list(_INDICATOR_INDEX.values()):
        marker = (record.subject, record.indicator_code)
        if marker not in seen:
            seen.add(marker)
            out.append(record)
    return sorted(out, key=lambda r: (r.subject, r.indicator_code))


def lookup_indicator(code: str, subject: str = "") -> Optional[ExemplarRecord]:
    """The record for an indicator code in THIS subject, or None.

    A code that exists in several subjects is only returned when the caller's
    subject identifies one record — SchemeKnit never guesses another subject's
    curriculum evidence for a lesson.
    """
    _load()
    key = normalize_code(code)
    if not key:
        return None
    canonical = _subject_key(subject)
    if canonical:
        record = _INDICATOR_INDEX.get((canonical, key))
        if record:
            return record
        record = _CONTENT_STANDARD_INDEX.get((canonical, key))
        if record:
            return record
    if not canonical:
        matches = _INDICATOR_BY_CODE.get(key) or []
        if len(matches) == 1:
            return matches[0]
    return None


def lookup_content_standard(code: str, subject: str = "") -> Optional[ExemplarRecord]:
    """The record for a content-standard code in THIS subject (or None)."""
    _load()
    key = normalize_code(code)
    canonical = _subject_key(subject)
    if not key or not canonical:
        return None
    return _CONTENT_STANDARD_INDEX.get((canonical, key))


def subject_of(record: ExemplarRecord) -> str:
    return record.subject

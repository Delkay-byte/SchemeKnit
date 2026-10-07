"""Canonical curriculum evidence for ONE source occurrence (Priority 2 §2).

The evidence object is assembled before any prose is written and carries the
FULL indicator text, the content standard, curriculum action verbs, key
concepts, expected performance, source provenance and any exemplar/interpreter
evidence. The lesson builder consumes it for objective, topic, activity,
assessment and differentiation decisions — the indicator is never truncated
into a title, and the content standard is never dropped from reach of the
authoring engine.

This is plain structured data (no AI). A future RAG layer can populate the
same fields from retrieved documents without changing the consumers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import CODE_PREFIX_RE as _CODE_RE


def strip_code(text: str) -> str:
    """Indicator text without a leading curriculum code."""
    if not text:
        return ""
    return _CODE_RE.sub("", text).strip() or text.strip()


@dataclass(frozen=True)
class LessonEvidence:
    """Everything verified about one source occurrence, before composition."""

    subject: str
    class_level: str
    strand: str
    sub_strand: str
    content_standard: str
    content_standard_code: str
    #: FULL indicator prose exactly as the source states it (code stripped).
    indicator_text: str
    indicator_code: str
    #: Action verbs supported by the corpus/exemplar or the indicator text.
    action_verbs: List[str] = field(default_factory=list)
    #: The indicator's leading performance verb ("" when none is detectable).
    primary_verb: str = ""
    #: Significant curriculum concepts drawn from the indicator/standard.
    key_concepts: List[str] = field(default_factory=list)
    #: Observable performance the indicator demands (interpreter evidence).
    expected_performance: str = ""
    source_week: int = 0
    source_occurrence_id: str = ""
    source_resources: List[str] = field(default_factory=list)
    core_competencies: List[str] = field(default_factory=list)
    curriculum_terms: List[str] = field(default_factory=list)
    #: Exemplar record for this (subject, code) when one exists.
    exemplar: Optional[Any] = None
    assessment_evidence: List[str] = field(default_factory=list)
    #: Interpreter activity type (problem_solving, classification, ...).
    activity_type: str = ""
    bloom_level: str = ""
    #: True when the scheme stated real indicator prose (source authority).
    has_source_indicator: bool = False

    @property
    def has_indicator(self) -> bool:
        return bool(self.indicator_text.strip())


# Leading verbs that make an indicator measurable as written.
_VERB_RE = re.compile(
    r"^(?:to\s+)?(identify|describe|demonstrate|compare|classify|explain|"
    r"apply|investigate|distinguish|examine|categorise|categorize|design|"
    r"state|list|model|represent|determine|analyse|analyze|evaluate|outline|"
    r"use|create|perform|measure|calculate|interpret|justify|name|match|"
    r"arrange|sort|construct|draw|solve|round|express|ask|respond|record|"
    r"research|reflect|participate|write|read|practise|practice|recognise|"
    r"recognize|recite|pronounce|label|observe|predict|select|choose|"
    r"construct|compose|discuss|talk|play|sing|trace|colour|color|paste|"
    r"fold|cut|count|add|subtract|multiply|divide|measure|test)\b",
    re.I,
)

_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "into", "their",
    "will", "can", "are", "was", "were", "has", "have", "had", "but", "not",
    "you", "your", "our", "its", "his", "her", "each", "every", "then",
    "than", "when", "what", "which", "who", "how", "why", "all", "any",
    "out", "about", "after", "before", "between", "more", "most", "some",
    "such", "only", "own", "same", "too", "very", "just", "like", "well",
    "through", "during", "above", "below", "both", "few", "other", "while",
    "does", "done", "make", "made", "take", "give", "know", "see", "now",
    "new", "next", "last", "first", "second", "third", "over", "under",
    "learners", "learner", "children", "pupils", "lesson", "school", "class",
}


def primary_verb(indicator_text: str) -> str:
    """The indicator's leading performance verb (lowercase), or ""."""
    text = strip_code(indicator_text)
    text = re.sub(
        r"^(by the end of the lesson,? learners (should be able to|will)\s*:?\s*)",
        "", text, flags=re.I)
    text = re.sub(r"^learners (can|will|should be able to)\s+", "", text, flags=re.I)
    m = _VERB_RE.match(text.strip())
    if m:
        return m.group(1).lower()
    return ""


def key_concepts(text: str, limit: int = 8) -> List[str]:
    """Significant curriculum content words, in order of appearance."""
    words = re.findall(r"[A-Za-z][A-Za-z\-']{3,}", (text or "").lower())
    out: List[str] = []
    for w in words:
        if w in _STOP or w in out:
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


def build_evidence(
    *,
    subject: str,
    class_level: str,
    alloc: Any,
    exemplar: Optional[Any] = None,
    interp: Optional[Any] = None,
    default_verbs: Optional[List[str]] = None,
) -> LessonEvidence:
    """Assemble the canonical evidence object for one allocated occurrence.

    ``alloc`` is the AllocatedIndicator (Priority 1 source occurrence);
    ``exemplar`` the corpus record for (subject, code) or None; ``interp`` the
    indicator interpreter's reading or None. Never raises — missing evidence
    degrades to empty fields, never to fabricated content.
    """
    raw_indicator = (getattr(alloc, "indicator_description", "") or "").strip()
    code_only = bool(raw_indicator) and not re.search(r"[A-Za-z]", _CODE_RE.sub("", raw_indicator))
    indicator_text = "" if code_only else strip_code(raw_indicator)

    verbs: List[str] = []
    if exemplar is not None:
        verbs.extend(str(v).strip().lower()
                     for v in (getattr(exemplar, "curriculum_action_verbs", []) or [])
                     if str(v).strip())
    pv = primary_verb(indicator_text)
    if pv and pv not in verbs:
        verbs.insert(0, pv)
    if not verbs and default_verbs:
        verbs.extend(default_verbs)

    activity_type = (getattr(interp, "activity_type", "") or "") if interp else ""
    expected = (getattr(interp, "evidence_of_achievement", "") if interp else "") or ""
    if not expected and exemplar is not None:
        patterns = [p for p in (getattr(exemplar, "assessment_patterns", []) or []) if p]
        expected = patterns[0] if patterns else ""

    return LessonEvidence(
        subject=subject or "",
        class_level=class_level or "",
        strand=(getattr(alloc, "strand", "") or "").strip(),
        sub_strand=(getattr(alloc, "sub_strand", "") or "").strip(),
        content_standard=(getattr(alloc, "content_standard_description", "") or "").strip(),
        content_standard_code=(getattr(alloc, "content_standard_code", "") or "").strip(),
        indicator_text=indicator_text,
        indicator_code=(getattr(alloc, "indicator_code", "") or "").strip(),
        action_verbs=verbs,
        primary_verb=pv,
        key_concepts=key_concepts(indicator_text or (getattr(alloc, "sub_strand", "") or "")),
        expected_performance=expected.strip(),
        source_week=int(getattr(alloc, "week_number", 0) or 0),
        source_occurrence_id=(getattr(alloc, "source_occurrence_id", "") or ""),
        source_resources=list(getattr(alloc, "source_resources", []) or []),
        core_competencies=(
            list(getattr(exemplar, "core_competencies", []) or []) if exemplar else []),
        curriculum_terms=(
            list(getattr(exemplar, "focus_terms", []) or []) if exemplar else []),
        exemplar=exemplar,
        assessment_evidence=(
            [p for p in (getattr(exemplar, "assessment_patterns", []) or []) if p]
            if exemplar else []),
        activity_type=activity_type.lower(),
        bloom_level=(getattr(interp, "bloom_level", "") or "") if interp else "",
        has_source_indicator=bool(indicator_text),
    )

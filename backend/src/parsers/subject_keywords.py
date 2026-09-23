"""
Canonical subject-heading recognition for document section detection.

One document may pack several subjects (a "Basic 7 Scheme of Learning" with
English, Mathematics, Science, ...). Detecting a subject heading is the single
classification primitive shared by the DOCX and PDF parsers — definitions live
here only, never duplicated per parser.

Order matters: more specific phrases come before their generic substrings
("Integrated Science" before "Science", "Core Mathematics" before
"Mathematics", "Literature in English" before "English").
"""

import re
from typing import List, Optional

from ..models import Subject

#: (keyword, canonical Subject) — specific first.
SUBJECT_KEYWORDS: List[tuple] = [
    ("integrated science", Subject.INTEGRATED_SCIENCE),
    ("core mathematics", Subject.CORE_MATHEMATICS),
    ("elective mathematics", Subject.ELECTIVE_MATHEMATICS),
    ("general knowledge in art", Subject.GENERAL_KNOWLEDGE_IN_ART),
    ("general agriculture", Subject.GENERAL_AGRICULTURE),
    ("financial accounting", Subject.FINANCIAL_ACCOUNTING),
    ("cost accounting", Subject.COST_ACCOUNTING),
    ("business management", Subject.BUSINESS_MANAGEMENT),
    ("literature in english", Subject.LITERATURE_IN_ENGLISH),
    ("english language", Subject.ENGLISH),
    ("french language", Subject.FRENCH),
    ("language and literacy", Subject.LANGUAGE_AND_LITERACY),
    ("our world our people", Subject.OUR_WORLD_OUR_PEOPLE),
    ("religious and moral education", Subject.RME),
    ("physical and health education", Subject.PHE),
    ("physical development", Subject.PHYSICAL_DEVELOPMENT),
    ("creative arts and design", Subject.CREATIVE_ARTS),
    ("creative arts", Subject.CREATIVE_ARTS),
    ("career technology", Subject.CAREER_TECHNOLOGY),
    ("social studies", Subject.SOCIAL_STUDIES),
    ("ghanaian language", Subject.GHANAIAN_LANGUAGE),
    ("numeracy", Subject.NUMERACY),
    ("mathematics", Subject.MATHEMATICS),
    ("maths", Subject.MATHEMATICS),
    ("math", Subject.MATHEMATICS),
    ("biology", Subject.BIOLOGY),
    ("chemistry", Subject.CHEMISTRY),
    ("physics", Subject.PHYSICS),
    ("economics", Subject.ECONOMICS),
    ("geography", Subject.GEOGRAPHY),
    ("government", Subject.GOVERNMENT),
    ("history", Subject.HISTORY),
    ("french", Subject.FRENCH),
    ("english", Subject.ENGLISH),
    ("science", Subject.SCIENCE),
    ("computing", Subject.ICT),
    ("ict", Subject.ICT),
]

# Words that are noise in a heading and are stripped before matching.
# 'for' appears in real district titles: "… SCHEME OF LEARNING FOR BASIC 6 - ENGLISH LANGUAGE".
_NOISE_PATTERN = re.compile(
    r"\b(basic|jhs|shs|primary|nursery|kg|class|level|subject|scheme|of|"
    r"learning|work|term|first|second|third|one|two|three|week|weekly|for|"
    r"form|academic|year|nine|ten|eleven|twelve)\b"
)
_LEVEL_NUM = re.compile(r"\b\d+\b")
#: Class / form codes common in real headings after noise stripping:
#: "B9 SCIENCE", "BS9 CREATIVE ARTS…", "BASIC NINE - CAREER…", "FORM 3".
_CLASS_CODE = re.compile(
    r"\b(?:b|bs|jhs|shs|p)\s*\d+\b|\bform\s*\d+\b|\bbasic\s+\w+\b",
    re.IGNORECASE,
)

#: A heading is short; long paragraphs are prose, not headings.
#: Real multi-subject PDFs use full titles such as
#: "FIRST TERM SCHEME OF LEARNING - 2026/2027 ACADEMIC YEAR - BASIC NINE - CAREER TECHNOLOGY"
#: (88 chars) which still normalise to a bare subject name.
MAX_HEADING_LENGTH = 120

#: Leading/trailing tokens that wrap a subject name inside a heading.
#: Stripped iteratively so "for english language" and "the science" still
#: resolve, while interior keywords remain required as contiguous words.
WRAPPER_WORDS = frozenset({
    "for", "and", "the", "of", "a", "an", "to", "in", "on", "with",
    "at", "by", "from", "is", "are", "unit", "subject",
})


def _normalize(text: str) -> str:
    # '&' is part of real titles: "RELIGIOUS & MORAL EDUCATION".
    norm = text.lower().replace("&", " and ")
    norm = re.sub(r"[^a-z0-9 ]", " ", norm)
    norm = _CLASS_CODE.sub(" ", norm)
    norm = _LEVEL_NUM.sub(" ", norm)
    norm = _NOISE_PATTERN.sub(" ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def _strip_wrappers(norm: str) -> str:
    """Remove leading/trailing wrapper tokens (``for``, ``the``, …)."""
    words = norm.split()
    while words and words[0] in WRAPPER_WORDS:
        words = words[1:]
    while words and words[-1] in WRAPPER_WORDS:
        words = words[:-1]
    return " ".join(words)


def _matches_keyword(cand: str, keyword: str) -> bool:
    """True when ``cand`` is the subject keyword with only wrapper tokens around it.

    Any other extra words (prose) disqualify the match —
    "science measurement is fun" is not a Science heading.
    """
    if cand == keyword:
        return True
    if cand.startswith(keyword + " "):
        rest = cand[len(keyword) + 1:].split()
        return bool(rest) and all(w in WRAPPER_WORDS for w in rest)
    if cand.endswith(" " + keyword):
        rest = cand[: len(cand) - len(keyword) - 1].split()
        return bool(rest) and all(w in WRAPPER_WORDS for w in rest)
    return False


def canonical_subject_from_heading(text: str) -> Optional[Subject]:
    """Return the Subject a heading names, or None when it is not a heading.

    Requires the normalised heading to BE the subject name (optionally with
    wrapper tokens around it), not merely mention it. This keeps a sentence
    like "the science of measurement" from being misread as a subject heading
    while still accepting district titles such as
    "FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - ENGLISH LANGUAGE".
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_HEADING_LENGTH:
        return None
    norm = _normalize(stripped)
    if not norm:
        return None
    candidates = [norm]
    unwrapped = _strip_wrappers(norm)
    if unwrapped and unwrapped != norm:
        candidates.append(unwrapped)
    for cand in candidates:
        for keyword, subject in SUBJECT_KEYWORDS:
            if _matches_keyword(cand, keyword):
                return subject
    return None


def detect_document_title(lines: List[str]) -> str:
    """Best-effort document title from the earliest heading-like line."""
    for line in lines:
        text = (line or "").strip()
        if not text:
            continue
        if len(text) > 120:
            continue
        if re.search(r"scheme\s+of\s+(learning|work)", text, re.IGNORECASE):
            return text
    for line in lines:
        text = (line or "").strip()
        if text and len(text) <= 120:
            return text
    return ""

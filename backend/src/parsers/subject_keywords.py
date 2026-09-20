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
_NOISE_PATTERN = re.compile(
    r"\b(basic|jhs|shs|primary|nursery|kg|class|level|subject|scheme|of|"
    r"learning|work|term|first|second|third|one|two|three|week|weekly)\b"
)
_LEVEL_NUM = re.compile(r"\b\d+\b")

#: A heading is short; long paragraphs are prose, not headings.
MAX_HEADING_LENGTH = 80


def _normalize(text: str) -> str:
    norm = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    norm = _LEVEL_NUM.sub(" ", norm)
    norm = _NOISE_PATTERN.sub(" ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def canonical_subject_from_heading(text: str) -> Optional[Subject]:
    """Return the Subject a heading names, or None when it is not a heading.

    Requires the normalised heading to BE the subject name (optionally with a
    leading/trailing level word), not merely mention it. This keeps a sentence
    like "the science of measurement" from being misread as a subject heading.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_HEADING_LENGTH:
        return None
    norm = _normalize(stripped)
    if not norm:
        return None
    for keyword, subject in SUBJECT_KEYWORDS:
        if norm == keyword or norm.startswith(keyword + " ") or norm.endswith(" " + keyword):
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

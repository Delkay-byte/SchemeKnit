"""Official NaCCA core competencies (National Pre-Tertiary Learning
Assessment Framework, Section 4.1).

The six labels are fixed. Teacher selections and generated output use these
exact names with their official abbreviations; no AI/provider label is
accepted.
"""

from __future__ import annotations

from typing import Iterable, List

OFFICIAL_CORE_COMPETENCIES = (
    ("Critical Thinking and Problem Solving", "CP"),
    ("Creativity and Innovation", "CI"),
    ("Communication and Collaboration", "CC"),
    ("Cultural Identity and Global Citizenship", "CG"),
    ("Personal Development and Leadership", "PL"),
    ("Digital Literacy", "DL"),
)

_CANONICAL = {
    name.lower(): f"{name} ({code})"
    for name, code in OFFICIAL_CORE_COMPETENCIES
}
_CANONICAL_BY_CODE = {
    code.lower(): f"{name} ({code})" for name, code in OFFICIAL_CORE_COMPETENCIES
}
# Legacy values stored before the abbreviations were shown.
_CANONICAL.update({
    f"{name} ({code})".lower(): f"{name} ({code})"
    for name, code in OFFICIAL_CORE_COMPETENCIES
})


def normalize_competency(value: str) -> str:
    """Return the official label for one value, or "" when not recognised."""
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    key = text.lower()
    if key in _CANONICAL:
        return _CANONICAL[key]
    if key in _CANONICAL_BY_CODE:
        return _CANONICAL_BY_CODE[key]
    # Accept "Name (CP)" written with different spacing/case.
    for name, code in OFFICIAL_CORE_COMPETENCIES:
        if key in {name.lower(), f"{name} ({code})".lower(),
                   f"{name} - {code}".lower()}:
            return f"{name} ({code})"
    return ""


def normalize_competencies(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        canonical = normalize_competency(value)
        if canonical and canonical not in out:
            out.append(canonical)
    return out

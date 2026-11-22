"""
WAPEF academic-year profile: Deep Hope and Storyline.

Contract
--------
* Deep Hope and Storyline are ACADEMIC-YEAR level. One value each per teacher
  per academic year, reused byte-identically on every WAPEF lesson plan.
* They are teacher-selected: an approved option or the teacher's own wording.
  AI never chooses, generates, rewrites or clears them.
* A row is keyed by (teacher_id, academic_year). Opening a new academic year
  therefore starts EMPTY: it never inherits the previous year's values and can
  never overwrite them (the old row is untouched).
* Through lines and God's Story stay topic/indicator-level and are NOT stored
  here; they remain per-lesson teacher selections.

The year is derived from the scheme's own ``academic_year`` field (for example
``2026/2027``), so the profile a plan uses is the year the plan belongs to.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .database import WapefAnnualProfileDB
from .engines.wapef_fields import (
    normalize_deep_hope,
    normalize_storyline,
    wapef_options,
)

#: The two fields the annual profile owns.
ANNUAL_FIELDS = ("deep_hope", "storyline")


class WapefAnnualProfileMissing(Exception):
    """Raised when a WAPEF plan would generate without annual values."""

    def __init__(self, academic_year: str, missing: list[str]):
        self.academic_year = academic_year
        self.missing = missing
        super().__init__(
            f"Set {', '.join(missing)} for {academic_year or 'this academic year'} "
            "before generating a WAPEF lesson plan."
        )


def _clean_year(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


#: Longest teacher-written annual value. Generous enough for a full sentence.
ANNUAL_TEXT_MAX = 1000


def _annual_text(value: Any, normalizer) -> str:
    """Approved label when it matches, otherwise the teacher's own wording.

    Deep Hope and Storyline are teacher-owned annual statements. The approved
    option still canonicalizes when chosen from the list, but a teacher may
    write their own wording; the value is stored verbatim (whitespace cleaned)
    and is NEVER generated or rewritten by AI.
    """
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    canonical = normalizer(text)
    if canonical:
        return canonical
    return text[:ANNUAL_TEXT_MAX]


def get_profile(db: Session, teacher_id: str,
                academic_year: str) -> Dict[str, Any]:
    """Return the stored annual profile (empty values when not set yet)."""
    year = _clean_year(academic_year)
    row = (
        db.query(WapefAnnualProfileDB)
        .filter(
            WapefAnnualProfileDB.teacher_id == teacher_id,
            WapefAnnualProfileDB.academic_year == year,
        )
        .first()
    )
    if row is None:
        return {
            "academic_year": year,
            "deep_hope": "",
            "storyline": "",
            "configured": False,
            "missing": ["Deep Hope", "Storyline"],
            "updated_at": None,
        }
    deep_hope = _annual_text(row.deep_hope, normalize_deep_hope)
    storyline = _annual_text(row.storyline, normalize_storyline)
    missing = []
    if not deep_hope:
        missing.append("Deep Hope")
    if not storyline:
        missing.append("Storyline")
    return {
        "academic_year": year,
        "deep_hope": deep_hope,
        "storyline": storyline,
        "configured": not missing,
        "missing": missing,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def save_profile(db: Session, teacher_id: str, academic_year: str,
                 deep_hope: Any, storyline: Any) -> Dict[str, Any]:
    """Create or update ONE academic year's profile.

    An approved option keeps its canonical spelling; teacher-written wording is
    stored verbatim. An explicit blank clears that field for this year only.
    """
    year = _clean_year(academic_year)
    if not year:
        raise ValueError("An academic year is required.")

    canonical_hope = _annual_text(deep_hope, normalize_deep_hope)
    canonical_story = _annual_text(storyline, normalize_storyline)

    row = (
        db.query(WapefAnnualProfileDB)
        .filter(
            WapefAnnualProfileDB.teacher_id == teacher_id,
            WapefAnnualProfileDB.academic_year == year,
        )
        .first()
    )
    if row is None:
        row = WapefAnnualProfileDB(
            teacher_id=teacher_id,
            academic_year=year,
            deep_hope=canonical_hope,
            storyline=canonical_story,
        )
        db.add(row)
    else:
        row.deep_hope = canonical_hope
        row.storyline = canonical_story
        row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return get_profile(db, teacher_id, year)


def require_profile(db: Session, teacher_id: str,
                    academic_year: str) -> Dict[str, Any]:
    """Return the profile or raise :class:`WapefAnnualProfileMissing`.

    Used by the generation route: a WAPEF plan never falls back to an AI guess,
    a prior year's value, or a per-lesson value when the annual selection is
    unset.
    """
    profile = get_profile(db, teacher_id, academic_year)
    if not profile["configured"]:
        raise WapefAnnualProfileMissing(profile["academic_year"],
                                        profile["missing"])
    return profile


def annual_options() -> Dict[str, Any]:
    """Approved option lists for the annual selectors."""
    options = wapef_options()
    return {
        "deep_hopes": options.get("deep_hopes", []),
        "storylines": options.get("storylines", []),
    }

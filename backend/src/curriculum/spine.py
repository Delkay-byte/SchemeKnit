"""
SchemeKnit Curriculum Spine
===========================

The **curriculum spine** is the persistent, canonical representation of a
processed scheme. Once a document has been parsed and its weeks stored
(``WeekDB`` rows, written once at upload / subject-confirmation time), every
later consumer — allocation, generation, quality gate, export, and the review
workspace — reads the *same* spine instead of rediscovering the curriculum.

Design decisions
----------------
* **No second parser, no second store.** The spine is derived from the already
  persisted, authoritative ``WeekDB`` rows. Re-deriving it on read means a
  source replacement (re-upload / re-confirm a subject) can never leave a stale
  cached curriculum behind: the spine always reflects the stored weeks.
* **No fabrication.** A week whose indicator content could not be confidently
  extracted is marked ``needs_review`` with a teacher-facing reason. It is never
  silently promoted to a complete instructional week, and generic model
  knowledge never stands in for missing curriculum evidence.
* **Provenance is first-class.** Every week and every generated lesson can be
  traced back to the source document, source week, strand, sub-strand, content
  standard and indicator that produced it.

The internal name ("spine") is not surfaced to teachers; the review workspace
renders it as the curriculum table and the "Source & alignment" panel.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from . import split_indicator_text

#: Teacher-facing week type labels (never raw enum values in the UI).
WEEK_TYPE_LABELS: Dict[str, str] = {
    "instruction": "Instruction",
    "revision": "Revision",
    "assessment": "Assessment",
    "sba": "SBA / Vacation",
    "sba_vacation": "SBA / Vacation",
    "other": "Other",
}

#: Review status values surfaced to the teacher.
REVIEW_OK = "ok"
REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_SPECIAL = "special"


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _week_type_value(week) -> str:
    raw = getattr(week, "week_type", None)
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw or "instruction")


def classify_week_review(week) -> Tuple[str, List[str]]:
    """Return ``(review_status, teacher_facing_reasons)`` for one week.

    Rules (deliberately conservative — flag only real uncertainty):

    * A non-instructional week (revision / assessment / SBA-vacation / other) is
      ``special``: it is a real curriculum state and carries no lesson fields.
    * An instructional week with **no extracted indicators** is ``needs_review``.
    * An instructional week whose strand, sub-strand *and* content standard are
      all missing is ``needs_review`` (the curriculum framing was not read).
    * Anything else is ``ok``.
    """
    week_type = _week_type_value(week)
    if week_type != "instruction":
        return REVIEW_SPECIAL, []

    indicators = [i for i in (getattr(week, "indicators", None) or []) if str(i).strip()]
    strand = (getattr(week, "strand", "") or "").strip()
    sub_strand = (getattr(week, "sub_strand", "") or "").strip()
    standards = [s for s in (getattr(week, "content_standards", None) or []) if str(s).strip()]

    reasons: List[str] = []
    if not indicators:
        reasons.append("No indicators were found for this week.")
    if not strand and not sub_strand and not standards:
        reasons.append(
            "The strand, sub-strand and content standard were not found for this week."
        )
    if reasons:
        return REVIEW_NEEDS_REVIEW, reasons
    return REVIEW_OK, []


def _week_indicators(week) -> List[Dict[str, str]]:
    """Split the stored indicator strings into (code, text) pairs.

    Reuses the canonical Curriculum IR splitter — never a second parser.
    """
    out: List[Dict[str, str]] = []
    for raw in (getattr(week, "indicators", None) or []):
        text = str(raw or "").strip()
        if not text:
            continue
        code, description = split_indicator_text(text)
        out.append({
            "code": code,
            "text": text,
            "description": description or text,
        })
    return out


def build_week_spine(week) -> Dict[str, Any]:
    """Canonical view of one curriculum week."""
    status, reasons = classify_week_review(week)
    week_type = _week_type_value(week)
    indicators = _week_indicators(week)
    return {
        "week_number": getattr(week, "week_number", None),
        "id": getattr(week, "id", None),
        "week_type": week_type,
        "week_type_label": WEEK_TYPE_LABELS.get(week_type, week_type.title()),
        "start_date": _iso(getattr(week, "start_date", None)),
        "end_date": _iso(getattr(week, "end_date", None)),
        "week_ending_derived": bool(getattr(week, "week_ending_derived", False)),
        "strand": getattr(week, "strand", "") or "",
        "sub_strand": getattr(week, "sub_strand", "") or "",
        "content_standards": list(getattr(week, "content_standards", None) or []),
        "indicators": indicators,
        "indicator_count": len(indicators),
        "resources": list(getattr(week, "resources", None) or []),
        "special_period_label": getattr(week, "special_period_label", "") or "",
        "special_period_type": getattr(week, "special_period_type", "") or "",
        # Teacher-facing review state — never raw parser diagnostics.
        "review_status": status,
        "review_reasons": reasons,
    }


def build_curriculum_spine(scheme_db) -> Dict[str, Any]:
    """Build the full spine for a scheme's persisted curriculum.

    ``scheme_db`` is a ``SchemeDB`` row (owner already enforced by the caller).
    """
    weeks = sorted(
        list(getattr(scheme_db, "weeks", None) or []),
        key=lambda w: (getattr(w, "week_number", 0) or 0),
    )
    week_rows = [build_week_spine(w) for w in weeks]

    instructional = [w for w in week_rows if w["week_type"] == "instruction"]
    special = [w for w in week_rows if w["week_type"] != "instruction"]
    needs_review = [w for w in week_rows if w["review_status"] == REVIEW_NEEDS_REVIEW]

    strands: List[str] = []
    for w in week_rows:
        s = (w["strand"] or "").strip()
        if s and s not in strands:
            strands.append(s)

    return {
        "scheme_id": getattr(scheme_db, "id", None),
        "subject": getattr(scheme_db, "subject", "") or "",
        "class_level": getattr(scheme_db, "class_level", "") or "",
        "term": getattr(scheme_db, "term", "") or "",
        "academic_year": getattr(scheme_db, "academic_year", "") or "",
        "source": {
            "filename": getattr(scheme_db, "filename", "") or "",
            "document_title": getattr(scheme_db, "document_title", "") or "",
            "detection_status": getattr(scheme_db, "detection_status", "") or "",
            "stored_at": _iso(getattr(scheme_db, "upload_date", None)),
        },
        "weeks": week_rows,
        "strands": strands,
        "summary": {
            "total_weeks": len(week_rows),
            "instructional_weeks": len(instructional),
            "special_weeks": len(special),
            "indicator_count": sum(w["indicator_count"] for w in week_rows),
            "needs_review_weeks": len(needs_review),
            "strand_count": len(strands),
        },
        #: Content version: a hash of the stored curriculum. Changes whenever the
        #: source is replaced / re-confirmed, so derived caches can be invalidated
        #: correctly instead of silently going stale.
        "spine_version": spine_version(scheme_db),
    }


def spine_version(scheme_db) -> str:
    """Content hash of the persisted curriculum (source + weeks).

    Deterministic and content-only: two identical curricula hash identically,
    and any change to a week (or a source replacement) changes the hash.
    """
    payload = {
        "filename": getattr(scheme_db, "filename", "") or "",
        "subject": getattr(scheme_db, "subject", "") or "",
        "class_level": getattr(scheme_db, "class_level", "") or "",
        "term": getattr(scheme_db, "term", "") or "",
        "weeks": [
            {
                "n": getattr(w, "week_number", None),
                "t": _week_type_value(w),
                "st": getattr(w, "strand", "") or "",
                "sub": getattr(w, "sub_strand", "") or "",
                "cs": list(getattr(w, "content_standards", None) or []),
                "ind": list(getattr(w, "indicators", None) or []),
                "res": list(getattr(w, "resources", None) or []),
            }
            for w in sorted(
                list(getattr(scheme_db, "weeks", None) or []),
                key=lambda w: (getattr(w, "week_number", 0) or 0),
            )
        ],
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def lesson_provenance(
    lp,
    scheme_db=None,
    *,
    ai_active: bool = False,
    ai_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Answer "Why did SchemeKnit generate this?" for one lesson.

    The teacher does not need every technical detail by default; this record is
    rendered inside a compact, expandable "Source & alignment" panel.
    """
    codes = list(getattr(lp, "indicator_codes", None) or [])
    indicators = list(getattr(lp, "indicators", None) or [])
    indicator_code = codes[0] if codes else ""
    indicator_text = ""
    if indicator_code:
        for raw in indicators:
            code, _ = split_indicator_text(str(raw))
            if code == indicator_code:
                indicator_text = str(raw)
                break
    if not indicator_text and indicators:
        indicator_text = str(indicators[0])

    if ai_active:
        generation = "Curriculum-first + AI enrichment"
    elif getattr(lp, "ai_generated", False):
        generation = "Curriculum-first + AI enrichment"
    else:
        generation = "Curriculum-first (deterministic)"

    # Source-week review state, read from the SAME spine the generator uses.
    # A lesson generated from a week that needs review says so (Pattern 6);
    # with no scheme we report "unknown" rather than claiming the week is fine.
    source_week_type: Optional[str] = None
    source_review_status: Optional[str] = None
    source_review_reasons: List[str] = []
    if scheme_db is not None:
        source_week = getattr(lp, "week_number", None)
        for week in (getattr(scheme_db, "weeks", None) or []):
            if getattr(week, "week_number", None) == source_week:
                source_week_type = _week_type_value(week)
                source_review_status, source_review_reasons = classify_week_review(week)
                break

    return {
        "scheme": (getattr(scheme_db, "filename", "") if scheme_db else "") or "",
        "curriculum_source": "Teacher scheme",
        "source_week": getattr(lp, "week_number", None),
        "teaching_week": getattr(lp, "teaching_week", None) or getattr(lp, "week_number", None),
        "strand": getattr(lp, "strand", "") or "",
        "sub_strand": getattr(lp, "sub_strand", "") or "",
        "content_standard": getattr(lp, "content_standard", "") or "",
        "content_standard_code": getattr(lp, "content_standard_code", "") or "",
        "indicator": indicator_code,
        "indicator_text": indicator_text,
        "period": getattr(lp, "period", "") or "",
        "carry_forward": bool(getattr(lp, "carry_forward", False)),
        "generation": generation,
        "ai_provider": ai_provider or ("AI enrichment" if getattr(lp, "ai_generated", False) else None),
        "source_week_type": source_week_type,
        "source_review_status": source_review_status,
        "source_review_reasons": source_review_reasons,
    }

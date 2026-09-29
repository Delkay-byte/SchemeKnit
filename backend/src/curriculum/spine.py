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
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from . import split_indicator_text

#: Teacher-facing week type labels (never raw enum values in the UI).
WEEK_TYPE_LABELS: Dict[str, str] = {
    "instruction": "Instruction",
    "revision": "Revision",
    "assessment": "Assessment",
    "sba": "SBA / Vacation",
    "sba_vacation": "SBA / Vacation",
    "mixed": "Mixed week",
    "other": "Other",
}

#: Review status values surfaced to the teacher.
REVIEW_OK = "ok"
REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_SPECIAL = "special"
REVIEW_MIXED = "mixed"


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


def classify_week_review(week, scheme_weeks=None) -> Tuple[str, List[str]]:
    """Return ``(review_status, teacher_facing_reasons)`` for one week.

    ``scheme_weeks`` optionally supplies the FULL week list of the source
    scheme so the "does this source provide indicators at all?" question is
    answered scheme-wide (Defect 2: "no indicator column in the source" is a
    different fact from "the parser missed this week's indicator"). Omit it
    and the check falls back to this week alone.

    Rules (deliberately conservative — flag only real uncertainty):

    * A non-instructional week (revision / assessment / SBA-vacation / other) is
      ``special``: it is a real curriculum state and carries no lesson fields.
    * A ``mixed`` week is ``mixed``: it carries BOTH a special period and real
      teaching content. The special segment stays excluded from normal lesson
      allocation while the teaching segment remains allocatable (Defect 4/7).
    * An instructional week with **no extracted indicators** is ``needs_review``
      — UNLESS the source genuinely provides no indicator column at all (a
      whole-scheme check), in which case the honest state is ``ok`` with a
      "not provided in source" presentation (Defect 2: never conflate "the
      source has none" with "the parser failed").
    * An instructional week whose strand, sub-strand *and* content standard are
      all missing is ``needs_review`` (the curriculum framing was not read).
    * Anything else is ``ok``.
    """
    week_type = _week_type_value(week)
    if week_type == "mixed":
        return REVIEW_MIXED, []
    if week_type != "instruction":
        return REVIEW_SPECIAL, []

    indicators = [i for i in (getattr(week, "indicators", None) or []) if str(i).strip()]
    strand = (getattr(week, "strand", "") or "").strip()
    sub_strand = (getattr(week, "sub_strand", "") or "").strip()
    standards = [s for s in (getattr(week, "content_standards", None) or []) if str(s).strip()]

    reasons: List[str] = []
    # Defect 2, precisely: the source DOES provide indicators (other weeks
    # carry them) but this week has none → extraction uncertainty → review.
    # The source provides NO indicator column anywhere → the honest state is
    # "not provided in source", never a review failure.
    # Conservative default: with NO scheme context the source cannot be proven
    # to provide indicators, so the week stays flagged for review.
    if not indicators:
        # ``scheme_weeks`` supplied → trust the whole-scheme check: review only
        # when the source DOES provide indicators elsewhere. No context →
        # conservative default: flag for review (cannot prove the source has
        # no indicator column).
        source_provides = (
            scheme_provides_indicators(scheme_weeks)
            if scheme_weeks is not None else None
        )
        if source_provides is not False:
            reasons.append("No indicators were found for this week.")
    if not strand and not sub_strand and not standards:
        reasons.append(
            "The strand, sub-strand and content standard were not found for this week."
        )
    if reasons:
        return REVIEW_NEEDS_REVIEW, reasons
    return REVIEW_OK, []


def scheme_provides_indicators(scheme_or_weeks) -> bool:
    """True when the source curriculum carries an indicator column AT ALL.

    Defect 2: "the parser found no indicator this week" and "this source has
    no indicator column" are different facts. A whole-level scheme (WAPEF
    Nursery/KG) legitimately has no Indicator column anywhere; its weeks must
    not be flagged ``needs_review`` for lacking one. Detection is
    content-based — any non-special week in the scheme carrying any indicator
    text means the source provides them.

    Accepts a scheme object (anything with ``.weeks``) OR a list of weeks.
    """
    weeks = getattr(scheme_or_weeks, "weeks", None)
    if weeks is None and not isinstance(scheme_or_weeks, (list, tuple)):
        return False
    if weeks is None:
        weeks = scheme_or_weeks
    for w in (weeks or []):
        if _week_type_value(w) not in ("instruction", "mixed"):
            continue
        for i in (getattr(w, "indicators", None) or []):
            if str(i or "").strip():
                return True
    return False


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
            # Defect D5: the description never repeats the code. A code-only
            # cell ("B7.1.1.1.1") has no description at all — the bare code is
            # reported through ``code``, never echoed as prose.
            "description": description,
        })
    return out


def week_special_segments(week) -> List[Dict[str, Any]]:
    """Source-defined special-period segments of one week (Defect 5).

    The verbatim source label is preserved as DATA. A label that embeds a date
    range ("MID-TERM (05-11-2026 to 06-11-2026)") is parsed into start/end
    dates; a label without dates yields ``start=None, end=None``. No calendar
    range is ever invented: absent pieces stay absent.
    """
    label = (getattr(week, "special_period_label", "") or "").strip()
    if not label:
        return []
    start, end = _parse_label_dates(label)
    return [{
        "type": (getattr(week, "special_period_type", "") or "other_non_instructional"),
        "label": label,
        "start": _iso(start),
        "end": _iso(end),
    }]


def week_teaching_segments(week) -> List[Dict[str, Any]]:
    """Source-defined teaching segments of one week (Defect 5 / D1).

    For a normal instructional week the teaching segment is simply the source
    week's own date span (start == end for week-ending-date schemes).

    A week's teaching span never overlaps its own special period (D1): the
    special segment — whose dates come from the label the source printed,
    never from a calendar guess — is subtracted from the week's span, so
    teaching begins the day AFTER an opening special period and stops the day
    BEFORE one that sits later in the week. When the special period covers
    every day of the week there is no teaching segment at all. Nothing is
    invented: every boundary is a date the source itself supplies, and a
    label without dates shifts nothing.
    """
    start = getattr(week, "start_date", None)
    end = getattr(week, "end_date", None)
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()

    special_spans: List[Tuple[date, date]] = []
    for seg in week_special_segments(week):
        seg_start = _as_date(seg.get("start"))
        seg_end = _as_date(seg.get("end"))
        if seg_start is None or seg_end is None:
            continue
        if seg_end < seg_start:
            seg_start, seg_end = seg_end, seg_start
        special_spans.append((seg_start, seg_end))

    if not special_spans or start is None or end is None:
        # Nothing dated to subtract (or no span to subtract from): the
        # source's own dates stay exactly as read.
        return [{"start": _iso(start), "end": _iso(end)}]

    pieces: List[Tuple[date, date]] = [(start, end)]
    for seg_start, seg_end in special_spans:
        remaining: List[Tuple[date, date]] = []
        for lo, hi in pieces:
            if seg_end < lo or seg_start > hi:
                remaining.append((lo, hi))
                continue
            if lo < seg_start:
                remaining.append((lo, seg_start - timedelta(days=1)))
            if hi > seg_end:
                remaining.append((seg_end + timedelta(days=1), hi))
        pieces = remaining

    return [
        {"start": _iso(lo), "end": _iso(hi)}
        for lo, hi in pieces
        if lo <= hi
    ]


def _as_date(value) -> Optional[date]:
    """ISO string / date / datetime → ``date`` (``None`` when undated)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


_DATE_RANGE_RE = re.compile(
    r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\s*(?:to|→|->|–|-)\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
    re.IGNORECASE,
)


def _parse_label_dates(label: str) -> Tuple[Optional[date], Optional[date]]:
    """Pull the (start, end) dates out of a special-period label, day-first.

    "MID-TERM (05-11-2026 to 06-11-2026)" → (date(2026,11,5), date(2026,11,6)).
    No dates in the label → (None, None). Nothing is invented.
    """
    import re as _re
    m = _DATE_RANGE_RE.search(label or "")
    if not m:
        return (None, None)

    def _day_first(token: str) -> Optional[date]:
        parts = _re.split(r"[-/.]", token.strip())
        if len(parts) != 3:
            return None
        try:
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if y < 100:
            y += 2000
        if not (1 <= d <= 31 and 1 <= mo <= 12 and 2020 <= y <= 2035):
            return None
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    start = _day_first(m.group(1))
    end = _day_first(m.group(2))
    if start and end and end < start:
        start, end = end, start
    return (start, end)


def build_week_spine(week, scheme_weeks=None) -> Dict[str, Any]:
    """Canonical view of one curriculum week.

    ``scheme_weeks`` (the full stored week list) gives the review classifier
    scheme-wide context — see ``classify_week_review``.
    """
    status, reasons = classify_week_review(week, scheme_weeks)
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
        # Source-defined segments (Defect 5): special periods and teaching
        # spans are represented explicitly — never an invented Mon–Fri range.
        "special_segments": week_special_segments(week),
        "teaching_segments": week_teaching_segments(week),
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
    week_rows = [build_week_spine(w, weeks) for w in weeks]

    instructional = [w for w in week_rows if w["week_type"] == "instruction"]
    special = [w for w in week_rows if w["week_type"] not in ("instruction", "mixed")]
    mixed = [w for w in week_rows if w["week_type"] == "mixed"]
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
            "mixed_weeks": len(mixed),
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
            code, description = split_indicator_text(str(raw))
            if code == indicator_code:
                indicator_text = description
                break
    if not indicator_text and indicators:
        # Fall back to the first indicator's TEXT only: the code is already
        # reported separately in ``indicator``, and the panel renders them
        # side by side — repeating it here would show it twice (Defect D5).
        indicator_text = split_indicator_text(str(indicators[0]))[1]

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
        # Official-curriculum grounding, recomputed from the lesson's own subject
        # and indicator code — no stored copy, so it can never go stale. Absent
        # (None) when no official record exists for this indicator, which is the
        # honest answer: the deterministic planner then rests on the teacher's
        # scheme and the bounded subject pedagogy.
        "exemplar": _exemplar_provenance(lp),
    }


def _exemplar_provenance(lp) -> Optional[Dict[str, Any]]:
    """Official NaCCA exemplar evidence behind this lesson, or None."""
    codes = list(getattr(lp, "indicator_codes", None) or [])
    code = codes[0] if codes else ""
    subject = getattr(lp, "subject", "") or ""
    try:
        from .exemplars import CORPUS_VERSION, lookup_indicator
    except Exception:  # pragma: no cover - corpus is optional infrastructure
        return None
    looked_up = [
        code,
        getattr(lp, "content_standard_code", "") or "",
    ]
    for candidate in looked_up:
        if not candidate:
            continue
        record = lookup_indicator(candidate, str(subject))
        if record is None:
            continue
        return {
            "grounding": "Official NaCCA curriculum (derived)",
            "learning_focus": record.learning_focus,
            "action_verbs": list(record.curriculum_action_verbs or []),
            "source_title": record.source_title,
            "source_url": record.source_url,
            "source_version": record.source_version,
            "corpus_version": CORPUS_VERSION,
            "provenance": record.provenance,
        }
    return None

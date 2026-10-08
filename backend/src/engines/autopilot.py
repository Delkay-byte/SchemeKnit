"""Autopilot selection rules (Priority 3.1 — zero-decision generation).

The teacher's single "Generate my lesson plans" action must choose the right
source occurrences without the teacher picking weeks, periods or indicators.
Every rule here is PURE so the acceptance matrix (quota-capped, unlimited,
needs-review, repeated indicators, special-only weeks, WAPEF saved/missing)
runs directly against these functions and against the API endpoint that wraps
them.

Design contract (never renegotiated by callers):

* **Source order wins.** Rows arrive in curriculum order (earliest source
  week first, source occurrence order within the week) and are never
  reordered here. Selection is greedy in that order.
* **Pending only.** An occurrence whose id is already stored on the scheme is
  generated and never re-enters the batch.
* **Safe only.** ``needs_review`` occurrences are never silently generated —
  they are reported so the teacher can review them, and the rest still runs.
* **Special weeks never generate.** A special-period row (midterm/revision)
  has no instructional occurrence and is always skipped.
* **Quota is the server's.** The caller passes the authoritative monthly
  lesson-plan status; a repeated indicator across weeks shares one quota unit
  (the existing ``scheme:code`` reservation key), so admitting its second
  occurrence never costs an extra unit. Indicatorless schemes (Nursery/KG)
  reserve nothing, so every safe pending row fits.
* **No AI decision lives here.** Autopilot generates with the config the
    teacher already has; the default mode stays deterministic OFF.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

WAPEF_APPROVED_TEMPLATE_ID = "tpl-wapef-approved-plan"

_WAPEF_DRAFT_KEYS = (
    "wapef_deep_hope",
    "wapef_storyline",
    "wapef_through_lines",
    "wapef_gods_story",
)


def wapef_autopilot_state(
    template_id: Optional[str],
    drafts: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """WAPEF readiness for one scheme (spec §9, cases A/B/C).

    * Not the WAPEF template → nothing is required (``required=False``).
    * WAPEF template + any saved reusable value in this scheme's review
      drafts (case A: fully configured, case B: previously saved values) →
      ``saved=True``, autopilot proceeds.
    * WAPEF template + no saved values (case C) → ``saved=False``; the caller
      interrupts for the smallest necessary WAPEF input. Deep Hope,
      Storyline, Through lines and God's Story are never invented.
    """
    required = template_id == WAPEF_APPROVED_TEMPLATE_ID
    if not required:
        return {"required": False, "saved": True, "template_id": template_id or ""}

    saved = False
    for value in (drafts or {}).values():
        if not isinstance(value, dict):
            continue
        for key in _WAPEF_DRAFT_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                saved = True
                break
            if isinstance(candidate, (list, tuple)) and any(
                str(item).strip() for item in candidate
            ):
                saved = True
                break
        if saved:
            break
    return {"required": True, "saved": saved, "template_id": template_id or ""}


def select_autopilot_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    generated_ids: Iterable[str],
    quota_remaining: Optional[int],
    quota_unlimited: bool,
    quota_enforced: bool,
    indicatorless: bool,
) -> Dict[str, Any]:
    """Pick the occurrences one Autopilot click will generate.

    ``rows`` are the scheme's instructional allocations in source order
    (special-period rows may be present and are skipped). Each row needs at
    least ``source_occurrence_id`` and ``indicator_code``; ``needs_review``
    defaults to False when absent.

    Returns a dict with the selected rows/ids/codes (curriculum order), the
    safe-but-quota-skipped rows, the needs-review rows, and the counts the
    teacher-facing summary reads (``pending_count``, ``safe_pending_count``,
    ``needs_review_count``, ``selected_count``).
    """
    generated = {str(g) for g in generated_ids if g}
    remaining = None if quota_unlimited or not quota_enforced else max(int(quota_remaining or 0), 0)

    selected: List[Dict[str, Any]] = []
    selected_codes: List[str] = []
    selected_code_set = set()
    quota_skipped: List[Dict[str, Any]] = []
    needs_review_items: List[Dict[str, Any]] = []
    pending_count = 0
    safe_pending_count = 0

    for row in rows:
        if row.get("is_special_period"):
            # Special-only weeks produce no instructional lesson (never an
            # empty plan) — skip before anything else is considered.
            continue
        occurrence_id = str(row.get("source_occurrence_id") or "")
        if not occurrence_id:
            # Without stable identity the row cannot be targeted safely.
            continue
        if occurrence_id in generated:
            continue
        pending_count += 1

        if row.get("needs_review"):
            needs_review_items.append(row)
            continue
        safe_pending_count += 1

        code = str(row.get("indicator_code") or "").strip()
        admits_for_free = (
            indicatorless
            or not code
            or code in selected_code_set
            or remaining is None  # unlimited
        )
        if not admits_for_free:
            if len(selected_code_set) >= remaining:
                quota_skipped.append(row)
                continue
            selected_code_set.add(code)
            selected_codes.append(code)
        selected.append(row)

    return {
        "selected": selected,
        "selected_occurrence_ids": [r["source_occurrence_id"] for r in selected],
        "selected_indicator_codes": selected_codes,
        "quota_skipped": quota_skipped,
        "needs_review_items": needs_review_items,
        "pending_count": pending_count,
        "safe_pending_count": safe_pending_count,
        "needs_review_count": len(needs_review_items),
        "selected_count": len(selected),
    }


def selection_blockers(
    *,
    detection_status: str,
    subject: Optional[str],
    class_level: Optional[str],
    confirmed_class: Optional[str],
    is_known_class_level,
    quota_selected_count: int,
    safe_pending_count: int,
    pending_count: int,
    needs_review_count: int,
    wapef: Dict[str, Any],
    quota_remaining: Optional[int],
    quota_message_for_empty,
) -> List[Dict[str, str]]:
    """Teacher-facing interruption reasons, in the order the teacher fixes them.

    Only genuinely-required decisions appear here (spec §1): subject ambiguity,
    a class the scheme never stated, missing one-time WAPEF values, an
    exhausted monthly allowance, an all-uncertain source, or a scheme that has
    nothing pending. Everything the system can infer is absent from this list.
    """
    blockers: List[Dict[str, str]] = []
    undetermined = ("Unknown", "", None)

    if detection_status == "multiple":
        blockers.append({
            "code": "subject_confirmation",
            "message": (
                "This document contains more than one subject. Confirm which "
                "subject section to use before generating lesson plans."
            ),
        })
        return blockers
    if detection_status == "extraction_failed":
        blockers.append({
            "code": "extraction_failed",
            "message": (
                "This scheme could not be reliably extracted. Review the "
                "detected structure or upload a clearer copy."
            ),
        })
        return blockers
    if subject in undetermined:
        blockers.append({
            "code": "subject_confirmation",
            "message": (
                "The subject could not be determined from this scheme and "
                "needs confirmation before lesson plans can be generated."
            ),
        })
    if class_level in undetermined:
        confirmed = (confirmed_class or "").strip()
        if not confirmed or confirmed == "Unknown" or not is_known_class_level(confirmed):
            blockers.append({
                "code": "class_confirmation",
                "message": (
                    "The class could not be determined from this scheme. "
                    "Select the class this scheme is for, then try again."
                ),
            })

    if wapef.get("required") and not wapef.get("saved"):
        blockers.append({
            "code": "wapef_required",
            "message": "Before generating these WAPEF plans, choose your WAPEF values once.",
        })

    if not blockers:
        if pending_count == 0:
            blockers.append({
                "code": "nothing_pending",
                "message": "These lesson plans are already generated.",
            })
        elif safe_pending_count == 0:
            n = needs_review_count
            blockers.append({
                "code": "needs_review",
                "message": (
                    f"{n} source item{'s' if n != 1 else ''} "
                    f"{'needs' if n == 1 else 'need'} review before "
                    "lesson plans can be generated."
                ),
            })
        elif quota_selected_count == 0 and safe_pending_count > 0:
            blockers.append({
                "code": "quota_exhausted",
                "message": quota_message_for_empty(),
            })

    return blockers

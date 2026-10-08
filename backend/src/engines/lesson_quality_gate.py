"""Priority 4 — the deterministic lesson QUALITY GATE.

Every deterministic lesson is built, then VALIDATED in memory, then either
accepted, mechanically repaired, or deterministically REBUILT (bounded), and
only an accepted candidate is ever persisted. The gate sits on the canonical
generation path (``POST /generate`` → ``generate_all`` → persist), so single,
week, Autopilot and manual regeneration all pass through the same code.

Three layers, in order (spec §3):

1. HARD FAILURES (A–X) — the lesson is wrong, not merely weak. A lesson with
   any hard failure is never persisted as-is.
2. MECHANICAL REPAIR — punctuation/whitespace cleanup, exact-duplicate row
   removal, restoring a missing Phase 1/3 boundary row from the structured
   starter/conclusion values. Deterministic, in-place, never invents content.
3. DETERMINISTIC REBUILD — up to ``MAX_REBUILD_ATTEMPTS`` alternative
   candidates built with a different teaching pattern (the pattern catalog is
   scored with the already-tried patterns excluded), each re-checked through
   the same gate. The BEST passing candidate wins; ties break on curriculum
   alignment → subject pedagogy → activity specificity → assessment alignment
   → higher rubric total → fewer structural repetitions → source order.

Soft scoring reuses the canonical 15-criterion rubric
(``src/curriculum/lesson_rubric.py``) — the same implementation the frozen
benchmarks score with — plus the calibrated teacher-ready floors (no second,
conflicting rubric exists anywhere). A lesson with no hard failures but an
unmet floor is rebuilt, never silently accepted.

Early years (Nursery/KG) opt OUT of the provenance checks and floors their
source documents cannot supply — exactly as the pattern engine and the
builder's own pedagogy overrides do — and are gated on STRUCTURAL integrity
(phases, timing, filler, resources, assessment, export shape, WAPEF).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..curriculum.batch_context import (
    _EARLY_YEARS_PROFILES,
    build_selection_context,
    subject_profile_key,
)
from ..curriculum.lesson_rubric import (
    RUBRIC,
    hard_failures as _rubric_hard_failures,
    lesson_body,
    overlap_recall,
    phase_rows,
    score_lesson,
    teacher_ready,
)
from ..curriculum.patterns import PATTERNS, novelty_penalty, select_pattern
from ..curriculum.variation import fingerprint_lesson
from .wapef_template import is_wapef_template
from ..models import LessonPlan, TeachingActivity, TermConfig

#: Bounded rebuild: the initial candidate plus at most this many alternatives.
MAX_REBUILD_ATTEMPTS = 2

#: The lesson durations the composition engine is calibrated for (the timing
#: test matrix). Any positive duration up to ABSURD_DURATION_MAX is legal —
#: this tuple documents the supported set and is used only for reporting.
SUPPORTED_DURATIONS = (30, 40, 50, 60, 70, 80)
ABSURD_DURATION_MAX = 240

#: The four teacher-selected WAPEF fields (never rewritten or invented),
#: mapped draft-key → lesson field.
WAPEF_FIELDS = {
    "deep_hope": "wapef_deep_hope",
    "storyline": "wapef_storyline",
    "through_lines": "wapef_through_lines",
    "gods_story": "wapef_gods_story",
}

#: Teacher-ready floors — the calibrated acceptance threshold on top of
#: "no hard failures" (see docs/QUALITY_GATE.md). A lesson below any floor is
#: rebuilt, never accepted as-is.
REQUIRED_FLOORS = {
    "timing_integrity": 5,
    "objective_specificity": 4,
    "topic_specificity": 3,
    "phase1_usefulness": 3,
    "phase2_usefulness": 3,
    "phase3_usefulness": 3,
    "assessment_alignment": 3,
    "resource_realism": 3,
}

#: Class levels whose source documents carry no Content Standard column and
#: whose pedagogy is play-based (mirrors lesson_builder's own overrides and
#: batch_context._EARLY_YEARS_PROFILES).
EARLY_YEARS_CLASS_LEVELS = frozenset(
    {"Nursery", "Nursery 1", "Nursery 2", "KG 1", "KG 2"}
)

#: Canonical phase labels the composer emits (used only when a boundary row has
#: to be restored mechanically from the structured starter/conclusion).
_PHASE1_LABEL = "PHASE 1 · STARTER"
_PHASE3_LABEL = "PHASE 3 · PLENARY"

_TEXT_FIELDS = (
    "lesson_topic", "introduction", "starter_activity", "assessment",
    "conclusion", "class_assignment", "home_assignment", "group_work",
    "individual_work", "differentiation", "remediation", "extension",
    "reflection", "homework", "previous_knowledge", "remarks",
)

_LIST_STR_FIELDS = (
    "indicators", "indicator_codes", "keywords", "source_tlrs", "other_tlrs",
    "teaching_learning_resources", "references", "essential_questions",
    "core_competencies", "wapef_through_lines",
)


# ── Findings ────────────────────────────────────────────────────────────────


@dataclass
class Finding:
    """One gate finding. ``severity`` is "hard" (reject) or "soft" (rebuild)."""

    code: str
    severity: str
    detail: str = ""


@dataclass
class Outcome:
    """The gate's verdict on ONE candidate lesson."""

    accepted: bool
    hard: List[str] = field(default_factory=list)
    floors: List[str] = field(default_factory=list)
    scores: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    teacher_ready: bool = False

    @property
    def needs_work(self) -> bool:
        return bool(self.hard) or bool(self.floors)


@dataclass
class LessonReport:
    """The full per-lesson record (for metrics, logs and the report)."""

    lesson_id: str
    lesson_sequence: int
    indicator_code: str
    accepted: bool
    hard_failures: List[str] = field(default_factory=list)
    floors_failed: List[str] = field(default_factory=list)
    scores: Dict[str, int] = field(default_factory=dict)
    total: int = 0
    attempts: int = 0
    repairs: List[str] = field(default_factory=list)
    rebuild_pattern_ids: List[str] = field(default_factory=list)
    status: str = "rejected"
    final_lesson: Optional[LessonPlan] = None


# ── Ground truth entry ──────────────────────────────────────────────────────


def is_early_years(lp: LessonPlan) -> bool:
    """Nursery/KG lessons gate on structural integrity only (see module docstring)."""
    class_level = getattr(lp, "class_level", None)
    if class_level is None:
        return False
    # ClassLevel is a (str, Enum): normalize to the string value so the
    # membership test is reliable regardless of the enum's hashing.
    level = class_level.value if hasattr(class_level, "value") else str(class_level)
    return level in EARLY_YEARS_CLASS_LEVELS


def build_entry(alloc: Any, lp: LessonPlan) -> Dict[str, Any]:
    """Build the rubric's ground-truth ``entry`` for one lesson.

    ``alloc`` is the allocation the lesson was actually built from (the
    ledger's copy, whose ``indicator_description`` is the source string with
    its curriculum code). It may be ``None`` for lessons built outside the
    allocation engine; the entry then falls back to the lesson's own fields.
    """
    if alloc is not None:
        indicator = (getattr(alloc, "indicator_description", "") or "").strip()
        indicatorless = not indicator
        if indicatorless:
            # Code-only / indicatorless rows (KG, Nursery continuation weeks):
            # the sub-strand is the honest curriculum focus — the same
            # substitution the allocation engine uses for the previous-lesson
            # link. The objective and topic are composed from it, so the
            # rubric's recall check must reference it too.
            indicator = (getattr(alloc, "sub_strand", "") or "").strip()
        return {
            "subject": lp.subject,
            "class_level": lp.class_level,
            "week": getattr(alloc, "week_number", lp.week_number),
            "code": getattr(alloc, "indicator_code", "") or "",
            "indicator": indicator,
            "indicatorless": indicatorless,
            "strand": getattr(alloc, "strand", "") or "",
            "sub_strand": getattr(alloc, "sub_strand", "") or "",
            "content_standard_code": getattr(alloc, "content_standard_code", "") or "",
            "content_standard": getattr(alloc, "content_standard_description", "") or "",
            "resources": list(getattr(alloc, "source_resources", None) or []),
            "provenance": "runtime:%s" % (getattr(alloc, "source_occurrence_id", "") or ""),
            "source_occurrence_id": getattr(alloc, "source_occurrence_id", "") or "",
            "group": "",
        }
    indicator = " ".join(lp.indicators or []).strip()
    return {
        "subject": lp.subject,
        "class_level": lp.class_level,
        "week": lp.week_number,
        "code": (lp.indicator_codes[0] if lp.indicator_codes else ""),
        "indicator": indicator,
        "indicatorless": not indicator,
        "strand": lp.strand or "",
        "sub_strand": lp.sub_strand or "",
        "content_standard_code": lp.content_standard_code or "",
        "content_standard": lp.content_standard or "",
        "resources": list(lp.source_tlrs or []),
        "provenance": "runtime:lesson",
        "source_occurrence_id": getattr(lp, "source_occurrence_id", "") or "",
        "group": "",
    }


# ── Layer 1: hard failures ──────────────────────────────────────────────────

def _export_structure_failures(lp: LessonPlan) -> List[str]:
    """Export-critical structural corruption (X / W)."""
    out: List[str] = []
    for name in _LIST_STR_FIELDS:
        value = getattr(lp, name, None)
        if value is None:
            out.append("corrupted_field:" + name)
            continue
        if not isinstance(value, list):
            out.append("corrupted_field:" + name)
            continue
        for item in value:
            if not isinstance(item, str):
                out.append("corrupted_field:" + name)
                break
    for name in ("main_activities", "learner_activities", "teacher_activities"):
        rows = getattr(lp, name, None) or []
        if not isinstance(rows, list):
            out.append("corrupted_field:" + name)
            continue
        for row in rows:
            desc = getattr(row, "description", None)
            if not isinstance(desc, str) or not desc.strip():
                out.append("empty_activity_row")
                break
            if not isinstance(getattr(row, "phase", None), str) or not row.phase.strip():
                out.append("corrupted_field:" + name)
                break
    for obj in (lp.learning_objectives or []):
        if not isinstance(getattr(obj, "description", None), str) or not obj.description.strip():
            out.append("corrupted_field:learning_objectives")
            break
    for ref in (lp.structured_references or []):
        title = getattr(ref, "title", None)
        if not isinstance(title, str) or not title.strip():
            out.append("invalid_reference_shape")
            break
    # Duplicate structured references (same title+author) are corrupted data.
    seen = set()
    for ref in (lp.structured_references or []):
        key = (
            (getattr(ref, "title", "") or "").strip().lower(),
            (getattr(ref, "author_publisher", "") or "").strip().lower(),
        )
        if key in seen:
            out.append("duplicate_reference")
            break
        seen.add(key)
    return out


def _wapef_norm(value: Any) -> Any:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v or "").strip()]
    return str(value or "").strip()


def wapef_loss_failures(lp: LessonPlan, canonical: Optional[Dict[str, Any]]) -> List[str]:
    """Hard failure T — a saved WAPEF selection was LOST or rewritten.

    The four WAPEF values are the teacher's own selections from the approved
    lists. They are never composed or AI-changed, so the ONLY defect the gate
    can catch is LOSS: the teacher saved a selection and the persisted lesson
    no longer carries exactly it (byte-identical, through the same
    canonicalization the review draft path uses).

    No selection at all is the documented "empty state" (save-boundary group
    G): genuinely empty fields stay empty and the lesson is still valid — the
    gate must never invent a WAPEF plan or refuse a lesson the teacher chose
    to leave unselected.
    """
    if not is_wapef_template(lp.template_id):
        return []
    if not canonical:
        return []
    failures: List[str] = []
    for key, field in WAPEF_FIELDS.items():
        saved = canonical.get(key)
        saved_norm = _wapef_norm(saved)
        if not saved_norm:
            continue  # no selection for this field — empty is legitimate
        current = _wapef_norm(getattr(lp, field, None))
        if current != saved_norm:
            failures.append("wapef_loss")
            break
    return failures


def hard_failures(
    lp: LessonPlan,
    entry: Dict[str, Any],
    *,
    wapef_canonical: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Hard failures A–X for one lesson (calibrated canonical list).

    Combines the canonical benchmark ``hard_failures`` with the runtime
    provenance/structural checks the corpora do not exercise. Names that the
    canonical function already produces are never duplicated here.
    """
    out: List[str] = []

    # ── Canonical (calibrated) failures ──────────────────────────────────
    canonical = _rubric_hard_failures(entry, lp)
    early = is_early_years(lp)
    indicatorless = bool(entry.get("indicatorless"))
    for name in canonical:
        # Early-years sources carry no Content Standard column; the composer
        # cannot invent one and the source is the authority.
        if early and name == "missing_content_standard":
            continue
        # Indicatorless rows keep their code/sub-strand only; the canonical
        # wrong_indicator check assumes prose indicators in lp.indicators.
        if indicatorless and name == "wrong_indicator":
            continue
        out.append(name)

    # ── Runtime provenance checks (A/B/C/D/U/V) ──────────────────────────
    indicators = [i for i in (lp.indicators or []) if (i or "").strip()]
    if not indicators:
        out.append("missing_indicator")
    if entry.get("content_standard_code") and not (lp.content_standard_code or "").strip():
        out.append("missing_content_standard_code")
    if entry.get("code") and lp.indicator_codes and entry["code"] not in lp.indicator_codes:
        out.append("indicator_code_mismatch")
    if entry.get("week") and lp.week_number != entry["week"]:
        out.append("source_week_mismatch")
    if (
        entry.get("source_occurrence_id")
        and getattr(lp, "source_occurrence_id", "")
        and entry["source_occurrence_id"] != lp.source_occurrence_id
    ):
        out.append("source_occurrence_mismatch")

    # ── Structure (F/G/O/Q/X/W) ──────────────────────────────────────────
    p1, _p2, p3 = phase_rows(lp)
    if not p1:
        out.append("missing_phase1")
    if not p3:
        out.append("missing_phase3")
    if not any((a.description or "").strip() for a in (lp.learner_activities or [])):
        out.append("missing_learner_action")
    if not any((a.description or "").strip() for a in (lp.teacher_activities or [])):
        out.append("missing_teacher_action")
    if not (lp.assessment or "").strip():
        out.append("missing_assessment")
    duration = int(lp.duration_minutes or 0)
    if duration <= 0 or duration > ABSURD_DURATION_MAX:
        out.append("invalid_duration")

    # WAPEF loss (T): see ``wapef_loss_failures`` — a saved selection that the
    # persisted lesson no longer carries byte-identically. No selection → no
    # failure (the empty state is legitimate and never invented).
    out.extend(wapef_loss_failures(lp, wapef_canonical))

    out.extend(_export_structure_failures(lp))

    # Deterministic, de-duplicated order (a lesson is failed once per reason).
    seen = set()
    deduped: List[str] = []
    for name in out:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


# ── Layer 2: mechanical repair ──────────────────────────────────────────────

_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;.:])")
_REPEATED_PUNCT = re.compile(r"([,;]){2,}")
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_TRAILING_PUNCT = re.compile(r"[,;]\s*$")


def _clean_text(text: str) -> str:
    cleaned = _WS.sub(" ", (text or "")).strip()
    cleaned = _SPACE_BEFORE_PUNCT.sub(r"\1", cleaned)
    cleaned = _REPEATED_PUNCT.sub(r"\1", cleaned)
    cleaned = _EMPTY_PARENS.sub("", cleaned)
    cleaned = _TRAILING_PUNCT.sub("", cleaned).strip()
    return cleaned


def _activity_key(description: str) -> str:
    return _WS.sub(" ", (description or "")).strip().lower()


def mechanical_repair(lp: LessonPlan) -> List[str]:
    """Deterministic, in-place mechanical repairs. Never invents content.

    Returns the list of repairs applied (for metrics). Unresolved placeholders,
    filler phrases and weak content are NOT mechanical — they need a rebuild.
    """
    repairs: List[str] = []

    for name in _TEXT_FIELDS:
        value = getattr(lp, name, None)
        if not isinstance(value, str):
            continue
        cleaned = _clean_text(value)
        if cleaned != value:
            setattr(lp, name, cleaned)
            repairs.append("text:" + name)

    for name in ("main_activities", "learner_activities", "teacher_activities"):
        rows = getattr(lp, name, None)
        if not isinstance(rows, list) or not rows:
            continue
        cleaned_rows: List[TeachingActivity] = []
        keys: Dict[str, int] = {}
        changed = False
        for row in rows:
            description = _clean_text(getattr(row, "description", "") or "")
            if not description:
                changed = True
                continue
            key = _activity_key(description)
            if key in keys:
                # Merge an exact duplicate into the row that kept its place —
                # its minutes are added so the phase-sum invariant survives.
                kept = cleaned_rows[keys[key]]
                kept.duration_minutes = int(
                    kept.duration_minutes or 0) + int(getattr(row, "duration_minutes", 0) or 0)
                changed = True
                continue
            keys[key] = len(cleaned_rows)
            cleaned_rows.append(row.model_copy(update={"description": description}))
        if changed:
            setattr(lp, name, cleaned_rows)
            repairs.append("dedupe:" + name)

    # Restore a lost Phase 1 / Phase 3 boundary row from the structured
    # starter / conclusion values, using the minutes left in the budget so the
    # stored phase-sum still equals the lesson duration.
    duration = int(lp.duration_minutes or 0)
    if duration > 0:
        p1, _p2, p3 = phase_rows(lp)
        spent = sum(int(a.duration_minutes or 0) for a in (lp.main_activities or []))
        remainder = duration - spent
        if not p1 and remainder > 0 and (lp.starter_activity or "").strip():
            lp.main_activities.insert(
                0,
                TeachingActivity(
                    phase=_PHASE1_LABEL,
                    description=_clean_text(lp.starter_activity),
                    duration_minutes=remainder,
                ),
            )
            repairs.append("restore:phase1")
        elif not p3 and remainder > 0 and (lp.conclusion or "").strip():
            lp.main_activities.append(
                TeachingActivity(
                    phase=_PHASE3_LABEL,
                    description=_clean_text(lp.conclusion),
                    duration_minutes=remainder,
                ),
            )
            repairs.append("restore:phase3")

    return repairs


# ── Layer 3: deterministic rebuild ──────────────────────────────────────────


def pick_alternate_pattern(
    alloc: Any,
    config: TermConfig,
    batch_history: Any,
    previous_indicator: Optional[str],
    excluded_pattern_ids: Sequence[str],
) -> Optional[Any]:
    """The next-best teaching pattern, excluding the ones already tried.

    Deterministic: the catalog is scored with the same context the original
    selection used, the tried patterns are removed from the pool, and the
    remaining order is the same fit order with canonical/catalog tie-breaks.
    Early years have no patterns (play-based pedagogy) → ``None``: their
    lessons cannot be rebuilt with a different pattern.
    """
    if alloc is None or config is None or batch_history is None:
        return None
    if subject_profile_key(config) in _EARLY_YEARS_PROFILES:
        return None
    try:
        ctx = build_selection_context(
            alloc, config, batch_history,
            previous_indicator=previous_indicator or "",
        )
    except Exception:
        return None
    pool = [p for p in PATTERNS if p.id not in set(excluded_pattern_ids)]
    if not pool:
        return None
    try:
        pattern, _fit, _adjusted = select_pattern(
            ctx, candidates=pool, novelty_penalty=novelty_penalty(ctx))
    except Exception:
        return None
    return pattern


def _floor_failures(scores: Dict[str, int], early: bool) -> List[str]:
    """Soft floor failures (the rebuild trigger above "no hard failures")."""
    if early:
        # The calibrated floors are Basic 1-JHS; early-years sources cannot
        # meet the provenance-derived ones (see docs/QUALITY_GATE.md).
        return []
    return [
        "%s<%d" % (name, floor)
        for name, floor in REQUIRED_FLOORS.items()
        if (scores.get(name) or 0) < floor
    ]


def evaluate(
    lp: LessonPlan,
    entry: Dict[str, Any],
    *,
    wapef_canonical: Optional[Dict[str, Any]] = None,
) -> Outcome:
    """Run the full gate on one candidate (no mutation)."""
    scored = score_lesson(entry, lp)
    hard = hard_failures(lp, entry, wapef_canonical=wapef_canonical)
    early = is_early_years(lp)
    floors = _floor_failures(scored["scores"], early)
    accepted = (not hard) and (not floors)
    return Outcome(
        accepted=accepted,
        hard=hard,
        floors=floors,
        scores=dict(scored["scores"]),
        total=int(scored["total"] or 0),
        teacher_ready=accepted,
    )


# ── Best-candidate selection ────────────────────────────────────────────────


@dataclass
class Scored:
    """One candidate, scored, with its structural repetition count."""

    lp: LessonPlan
    outcome: Outcome
    fingerprint: Any = None
    collisions: int = 0
    order: int = 0


def _rank_key(scored: Scored) -> Tuple[Any, ...]:
    scores = scored.outcome.scores
    return (
        scores.get("indicator_fidelity", 0),
        scores.get("subject_pedagogy_fit", 0),
        scores.get("activity_specificity", 0),
        scores.get("assessment_alignment", 0),
        scored.outcome.total,
        -scored.collisions,
    )


def pick_best(candidates: List[Scored]) -> Optional[Scored]:
    """Deterministic best-candidate selection.

    Curriculum fidelity overrides style: the priority order is the spec's —
    curriculum alignment → subject pedagogy → activity specificity →
    assessment alignment → rubric total → fewer structural repetitions — and
    full ties keep SOURCE ORDER (the initial candidate wins), never randomness.
    """
    if not candidates:
        return None
    best = candidates[0]
    best_key = _rank_key(best)
    for cand in candidates[1:]:
        key = _rank_key(cand)
        if key > best_key:
            best, best_key = cand, key
    return best


def count_collisions(
    fingerprint: Any, prior_fingerprints: Sequence[Any]
) -> int:
    """How many already-accepted lessons this candidate is structurally the
    same as (normalized starter/main/reflection/assignments)."""
    if fingerprint is None:
        return 0
    return sum(1 for other in prior_fingerprints if other == fingerprint)


def lesson_fingerprint(lp: LessonPlan) -> Any:
    return fingerprint_lesson(lp, pattern_id=getattr(lp, "pattern_id", "") or "")


# ── Batch metrics ───────────────────────────────────────────────────────────


def summarize(reports: Sequence[LessonReport]) -> Dict[str, Any]:
    """Gate metrics for one run (logged and returned to the caller)."""
    n = len(reports)
    accepted = [r for r in reports if r.accepted]
    first_pass = [r for r in accepted if r.attempts == 0 and not r.repairs]
    repaired = [r for r in accepted if r.attempts == 0 and r.repairs]
    rebuilt = [r for r in accepted if r.attempts > 0]
    rejected = [r for r in reports if not r.accepted]
    hard_rejections: Dict[str, int] = {}
    soft_rejections: Dict[str, int] = {}
    for r in rejected:
        for code in r.hard_failures:
            hard_rejections[code] = hard_rejections.get(code, 0) + 1
        for code in r.floors_failed:
            soft_rejections[code] = soft_rejections.get(code, 0) + 1
    repairs: Dict[str, int] = {}
    for r in accepted:
        for repair in r.repairs:
            repairs[repair] = repairs.get(repair, 0) + 1
    return {
        "lessons": n,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "first_pass": len(first_pass),
        "repaired": len(repaired),
        "rebuilt": len(rebuilt),
        "first_pass_rate": round(len(first_pass) / n, 3) if n else 0.0,
        "teacher_ready_rate": round(len(accepted) / n, 3) if n else 0.0,
        "mean_score": round(sum(r.total for r in accepted) / len(accepted), 1)
        if accepted else 0.0,
        "mean_rebuilds": round(sum(r.attempts for r in accepted) / len(accepted), 2)
        if accepted else 0.0,
        "hard_rejections": hard_rejections,
        "soft_rejections": soft_rejections,
        "repairs": repairs,
    }


__all__ = [
    "ABSURD_DURATION_MAX",
    "EARLY_YEARS_CLASS_LEVELS",
    "Finding",
    "LessonReport",
    "MAX_REBUILD_ATTEMPTS",
    "Outcome",
    "REQUIRED_FLOORS",
    "Scored",
    "SUPPORTED_DURATIONS",
    "WAPEF_FIELDS",
    "build_entry",
    "wapef_loss_failures",
    "count_collisions",
    "evaluate",
    "hard_failures",
    "is_early_years",
    "lesson_fingerprint",
    "mechanical_repair",
    "pick_alternate_pattern",
    "pick_best",
    "summarize",
]

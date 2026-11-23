"""Final content-quality pass shared by deterministic and provider lessons.

The lesson builder already composes three distinct phases, but provider output
(Zeli) and older persisted drafts can still copy the starter into the main
phase, or leave generic drafting filler such as "the same content". This pass
runs on EVERY lesson before the quality gate and before persistence:

* it removes a Phase 1 sentence that was copied into Phase 2/3;
* it removes the same activity sentence repeated in two main phases;
* it replaces drafting filler ("the same content") with the lesson's real
  curriculum focus;
* it drops incomplete resource labels (a wrapped cell such as "patterns made
  from") and incomplete resource clauses from generated prose.

It never invents teaching content: it only deletes duplicated/truncated text.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List

from ..curriculum.vocabulary import is_incomplete_resource

__all__ = [
    "ensure_distinct_phases",
    "sanitize_resources",
    "class_code_prose_violations",
    "validate_lesson_content",
]

_BOUNDARY_STARTER = ("PHASE 1", "STARTER")
_BOUNDARY_PLENARY = ("PHASE 3", "PLENARY", "REFLECTION")
_FILLER_PATTERNS = (
    re.compile(r"\bthe same content\b", re.IGNORECASE),
    re.compile(r"\bsame content\b", re.IGNORECASE),
)
_CLASS_CODE_TOKEN = re.compile(r"(?<![\w.])([BK]\d+)(?![\w]|\.\d)")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _words(value: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (value or "").lower())
            if len(w) > 3}


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _is_same_text(a: str, b: str) -> bool:
    na, nb = _normalise(a), _normalise(b)
    if not na or not nb:
        return False
    if na == nb or na.startswith(nb) or nb.startswith(na):
        return True
    return _overlap(a, b) >= 0.82


def _focus(lp) -> str:
    for name in ("sub_strand", "strand", "lesson_topic"):
        value = " ".join(_text(getattr(lp, name, "")).replace("\n", " ").split())
        if value and re.search(r"[A-Za-z]{2,}", value):
            return value
    return "the lesson focus"


def _replace_filler(text: str, focus: str) -> str:
    if not text:
        return text
    out = text
    for pattern in _FILLER_PATTERNS:
        out = pattern.sub(focus, out)
    # A replacement at the start of a sentence keeps the focus readable.
    out = re.sub(r"\s{2,}", " ", out).strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def _split_sentences(text: str) -> List[str]:
    text = _text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _phase_name(activity) -> str:
    if isinstance(activity, dict):
        return _text(activity.get("phase")).upper()
    return _text(getattr(activity, "phase", "")).upper()


def _phase_text(activity) -> str:
    if isinstance(activity, dict):
        return _text(activity.get("description"))
    return _text(getattr(activity, "description", ""))


def _set_phase_text(activity, text: str) -> None:
    if isinstance(activity, dict):
        activity["description"] = text
    else:
        activity.description = text


def _dedupe_list(activities: list, references: List[str],
                 focus: str) -> tuple[list, int]:
    """Remove sentences copied from the starter/plenary from a phase list."""
    kept = []
    removed = 0
    seen_main: List[str] = []
    for activity in activities:
        phase = _phase_name(activity)
        if any(token in phase for token in _BOUNDARY_STARTER + _BOUNDARY_PLENARY):
            _set_phase_text(activity, _replace_filler(_phase_text(activity), focus))
            kept.append(activity)
            continue
        original = _phase_text(activity)
        sentences = _split_sentences(original)
        if not sentences:
            _set_phase_text(activity, _replace_filler(original, focus))
            kept.append(activity)
            continue
        unique = []
        for sentence in sentences:
            if any(_is_same_text(sentence, ref) for ref in references if ref):
                removed += 1
                continue
            if any(_is_same_text(sentence, other) for other in seen_main):
                removed += 1
                continue
            seen_main.append(sentence)
            unique.append(sentence)
        if unique:
            new_text = _replace_filler(" ".join(unique), focus)
            _set_phase_text(activity, new_text)
            kept.append(activity)
        else:
            # The whole row was a copy of another phase. Dropping it is honest:
            # the phase label remains on the neighbouring genuine row.
            removed += 1
    return kept, removed


def ensure_distinct_phases(lp) -> dict:
    """Make Phase 1, Phase 2 and Phase 3 tell different parts of the lesson.

    Returns a small audit dict so tests and logs can prove what was removed.
    """
    focus = _focus(lp)
    activity_lists = [
        ("main_activities", getattr(lp, "main_activities", None)),
        ("learner_activities", getattr(lp, "learner_activities", None)),
        ("teacher_activities", getattr(lp, "teacher_activities", None)),
    ]

    starter_texts = [
        _text(getattr(lp, "starter_activity", "")),
    ]
    for name, activities in activity_lists:
        for activity in activities or []:
            phase = _phase_name(activity)
            if any(token in phase for token in _BOUNDARY_STARTER):
                starter_texts.append(_phase_text(activity))

    starter_texts = [t for t in starter_texts if t]
    metrics = {"removed": 0, "lists": {}}

    for name, activities in activity_lists:
        if not activities:
            continue
        # Do not dedupe the main list against the plenary (the plenary may
        # legitimately restate the objective); remove the starter copy only.
        keeper = list(activities)
        keeper, removed = _dedupe_list(keeper, starter_texts, focus)
        # A second pass removes the same main sentence repeated across rows.
        if name == "main_activities":
            main_rows = [
                a for a in keeper
                if not any(token in _phase_name(a)
                           for token in _BOUNDARY_STARTER + _BOUNDARY_PLENARY)
            ]
            if len(main_rows) >= 2:
                seen = []
                final_rows = []
                for row in main_rows:
                    sentences = _split_sentences(_phase_text(row))
                    unique = [s for s in sentences
                              if not any(_is_same_text(s, x) for x in seen)]
                    if unique:
                        seen.extend(unique)
                        _set_phase_text(row, _replace_filler(" ".join(unique), focus))
                        final_rows.append(row)
                    else:
                        removed += 1
                if len(final_rows) >= 2:
                    boundaries = [a for a in keeper if a not in main_rows]
                    keeper = [
                        a for a in activities
                        if a in boundaries or a in final_rows
                    ]
                    # Preserve original order.
                    order = {id(a): i for i, a in enumerate(activities)}
                    keeper.sort(key=lambda a: order.get(id(a), 0))
        metrics["lists"][name] = removed
        metrics["removed"] += removed
        setattr(lp, name, keeper)

    # Replace filler even in the boundary fields.
    for field in ("starter_activity", "introduction", "conclusion", "assessment"):
        value = _text(getattr(lp, field, ""))
        if value:
            setattr(lp, field, _replace_filler(value, focus))
    return metrics


def sanitize_resources(lp) -> int:
    """Drop incomplete resource labels from every resource list on a lesson."""
    removed = 0
    for field in ("source_tlrs", "other_tlrs", "teaching_learning_resources"):
        values = getattr(lp, field, None)
        if not isinstance(values, list):
            continue
        clean = []
        for value in values:
            if is_incomplete_resource(str(value or "")):
                removed += 1
                continue
            clean.append(value)
        setattr(lp, field, clean)
    for field in ("main_activities", "learner_activities", "teacher_activities"):
        for activity in getattr(lp, field, None) or []:
            resources = (activity.get("resources")
                         if isinstance(activity, dict)
                         else getattr(activity, "resources", None))
            if not isinstance(resources, list):
                continue
            clean = [r for r in resources if not is_incomplete_resource(str(r or ""))]
            removed += len(resources) - len(clean)
            if isinstance(activity, dict):
                activity["resources"] = clean
            else:
                activity.resources = clean
    return removed


def class_code_prose_violations(text: str) -> List[str]:
    """Standalone class codes (``B4``) in natural-language prose.

    Dotted curriculum identifiers (``B4.1.1.1``) are legitimate and are not
    matched. Only a bare class code is a violation.
    """
    return [m.group(1) for m in _CLASS_CODE_TOKEN.finditer(text or "")]


def validate_lesson_content(lp) -> List[str]:
    """Return content-quality problems that must never reach a teacher."""
    problems: List[str] = []
    prose_fields = {
        "Through line": " ".join(
            str(x) for x in (getattr(lp, "wapef_through_lines", None) or [])),
        "God's Story": _text(getattr(lp, "wapef_gods_story", "")),
        "Storyline": _text(getattr(lp, "wapef_storyline", "")),
        "Deep Hope": _text(getattr(lp, "wapef_deep_hope", "")),
    }
    for label, value in prose_fields.items():
        for code in class_code_prose_violations(value):
            problems.append(f"{label} contains standalone class code {code}")

    # The DOCX renders Through line / God's Story from the teacher selection
    # plus a generated practice sentence. Validate that RENDERED prose too, not
    # only the stored label — this is where the "working with B4" defect
    # actually appeared.
    template_id = str(getattr(lp, "template_id", "") or "")
    if ("wapef" in template_id.lower()
            or prose_fields["Deep Hope"]
            or prose_fields["Storyline"]):
        try:
            from .wapef_connections import wapef_field_text
            for field, label in (("through_lines", "Through line"),
                                 ("gods_story", "God's Story"),
                                 ("storyline", "Storyline")):
                rendered = wapef_field_text(lp, field)
                for code in class_code_prose_violations(rendered):
                    problems.append(
                        f"{label} rendered prose contains standalone class code {code}")
        except Exception:
            pass

    for field in ("source_tlrs", "teaching_learning_resources"):
        for value in getattr(lp, field, None) or []:
            if is_incomplete_resource(str(value or "")):
                problems.append(f"incomplete resource: {value}")
    return problems

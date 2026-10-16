"""Structured assessment design — DoK levels, marking guidance, rubrics.

Phase 3 of the quality-enhancement sequence. Extends the composed lesson with:

  * ``AssessmentItem``s — DoK-levelled prompts that assess THIS indicator,
    each with expected evidence, marking guidance, the common misconception
    and a follow-up/remedial prompt. Deterministic, AI OFF.
  * an ``AnalyticRubric`` — only when the lesson's assessment genuinely
    marks a learner-created product, performance, investigation, design or
    extended response. Practical observable criteria, level descriptors and
    points; never presented as an official NaCCA/GES rubric.

Design rules (deterministic, no thresholds touched):

  * DoK is NOT Bloom. The shared indicator-action canon
    (``indicator_actions.py`` — one vocabulary, one interpretation) supplies
    the primary action and its coarse category; THIS module maps the action's
    cognitive DEMAND to a Depth-of-Knowledge level 1–4 (recall & reproduction
    / skills & concepts / strategic thinking / extended thinking) alongside
    — never interchangeable with — the Bloom category.
  * Level selection depends on the full indicator meaning, the primary
    action, the class level, the subject pedagogy, the lesson duration and
    what the learner must demonstrate. No lesson is forced to Level 4; DoK 4
    requires an extended creation/investigation indicator in a sufficiently
    long lesson.
  * Where the prompt involves a deterministic computation (mathematics),
    the operands are derived from the indicator code and the expected answer
    is COMPUTED in this module — never asserted without calculation.
  * Item count stays small (2–3): a recognition/recall check, the
    indicator-action check of evidence, and (where the subject offers a real
    everyday context) one contextual application item. Phase 2's formative
    checks and Phase 3's summative evidence stay in the composed prose.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

from . import activity_library
from .indicator_actions import (
    bloom_category as _bloom_category,
    leading_action as _leading_action,
)

# ── Depth of Knowledge (DoK) — cognitive-demand mapping (NOT Bloom) ─────────

#: Categories of the shared indicator-action canon → default DoK level.
_CATEGORY_DOK: Dict[str, int] = {
    "recall": 1,
    "communicate": 1,
    "practice": 1,
    "understand": 2,
    "apply": 2,
    "analyse": 3,
    "evaluate": 3,
    "create": 3,
    "french": 1,
}

#: Actions whose routine procedural demand stays DoK 2 even under a
#: higher-category umbrella (e.g. "Investigate … by calculating" stays 2
#: when the calculation itself is the deliverable).
_DOK2_ACTIONS = {
    "add", "subtract", "multiply", "divide", "calculate", "round", "count",
    "measure", "convert", "simplify", "sequence", "label", "sort", "match",
    "retell", "read", "write", "spell", "pronounce", "chart", "record",
}

#: Actions whose demand genuinely reaches strategic thinking.
_DOK3_ACTIONS = {
    "investigate", "analyse", "analyze", "evaluate", "assess", "justify",
    "critique", "compare", "relate", "design", "plan", "determine",
    "categorise", "categorize", "classify", "distinguish", "explain",
    "examine", "recommend", "appraise", "formulate", "derive", "prove",
}

#: Extended-thinking requires an extended creation/investigation demand.
_DOK4_ACTIONS = {
    # Extended thinking: producing or planning an extended original product.
    # (An ordinary one-lesson "investigate …" stays strategic — DoK 3 —
    # no lesson is forced upward to Level 4.)
    "design", "plan", "formulate", "originate", "devise", "invent",
}

_RECALL_ACTIONS = {
    "identify", "name", "state", "list", "recall", "define", "match",
    "recognise", "recognize", "label", "tell", "mention", "recite",
    "select", "choose", "circle", "tick", "sample", "pronounce", "count",
}

EARLY_YEARS_LEVELS = ("nursery", "kg", "kindergarten", "kg1", "kg2",
                      "nursery 1", "nursery 2")


def _is_early_years(class_level: str) -> bool:
    level = (class_level or "").strip().lower()
    return any(tag in level for tag in
               ("nursery", "kg", "kindergarten", "early childhood"))


def _is_jhs_or_above(class_level: str) -> bool:
    level = (class_level or "").strip().lower()
    return bool(re.search(r"\b(basic [4-9]|jhs|shs|senior|year)", level)) \
        and not _is_early_years(class_level)


def dok_level(indicator: str, class_level: str = "",
              duration_minutes: int = 60,
              action: str = "") -> int:
    """The Depth-of-Knowledge level (1–4) for THIS indicator's assessment.

    Deterministic: primary action + class level + lesson duration. DoK 4 is
    deliberately rare (extended creation/investigation in a long lesson) —
    no lesson is forced upward.
    """
    action = (action or _leading_action(indicator) or "").strip().lower()
    if _is_early_years(class_level):
        # Play-based observation only: recognise/naming at most.
        return 1 if action in _RECALL_ACTIONS else 2

    category = _bloom_category(action)
    level = _CATEGORY_DOK.get(category, 2)
    if action in _DOK2_ACTIONS:
        level = min(level, 2)
    if action in _DOK3_ACTIONS:
        level = max(level, 3)
    if action in _DOK3_ACTIONS and category in ("apply", "understand"):
        level = 3
    # DoK 4: only an extended demand with room to demonstrate it.
    if (action in _DOK4_ACTIONS and category in ("create", "analyse")
            and int(duration_minutes or 60) >= 60
            and _is_jhs_or_above(class_level)):
        level = 4
    return max(1, min(4, level))


# ── Deterministic computed answers (mathematics) ────────────────────────────

def _seed_ints(code: str, n: int = 2, cap: int = 9) -> List[int]:
    """Stable small integers derived from the indicator code (same code →
    same numbers → same answer, byte-for-byte across runs)."""
    digest = hashlib.sha256((code or indicator_fallback()).encode("utf-8"))
    return [(digest.digest()[i] % cap) + 1 for i in range(n)]


def indicator_fallback() -> str:
    return "SchemeKnit-assessment"


def computed_answer_item(code: str, action: str,
                         focus: str) -> Optional[Dict[str, str]]:
    """A check whose answer the system can compute reliably, or None.

    Only for the routine computation verbs where Python can compute the
    expected result exactly; everything else gets criteria-based marking
    (defensible, never a fake "one right creative answer").
    """
    a = (action or "").strip().lower()
    if a in ("add", "subtract", "multiply", "divide", "round", "count"):
        x, y = _seed_ints(code, 2, 9)
        if a == "add":
            prompt = f"Work out: {x} + {y} (show your working)."
            answer = x + y
            guidance = (f"Correct answer: {answer}. Full credit for the "
                        f"correct total with working shown; one mark lost "
                        f"for a place-value (carrying) slip, method intact.")
            miscon = ("Adding the digits without carrying — e.g. treating "
                      f"{x} + {y} as digit-by-digit.")
            follow = ("Re-teach with bundle-of-ten sticks; let the learner "
                      "rebuild the sum physically before re-trying.")
        elif a == "subtract":
            big, small = max(x, y) + 10, min(x, y)
            prompt = f"Work out: {big} − {small} (show your working)."
            answer = big - small
            guidance = (f"Correct answer: {answer}. Full credit with working; "
                        f"check the borrowing step when marking.")
            miscon = "Subtracting the smaller digit from the larger regardless of place."
            follow = ("Use a number line to re-model the exchange before "
                      "re-trying one item.")
        elif a == "multiply":
            x2, y2 = _seed_ints(code + "m", 2, 6)
            prompt = f"Work out: {x2} × {y2} (show your working)."
            answer = x2 * y2
            guidance = (f"Correct answer: {answer}. Full credit for the product; "
                        f"accept repeated addition if the result is right.")
            miscon = "Confusing × with + (e.g. treating 3 × 4 as 3 + 4)."
            follow = "Rebuild the product with counters in equal rows."
        elif a == "divide":
            q = _seed_ints(code + "d", 1, 8)[0]
            prod = q * _seed_ints(code + "e", 1, 6)[0]
            prompt = f"Work out: {prod} ÷ {q} (show your working)."
            answer = prod // q
            guidance = (f"Correct answer: {answer} (exact). Full credit for "
                        f"the quotient; accept sharing drawings that reach it.")
            miscon = "Sharing total by the wrong count, or ignoring remainders."
            follow = "Re-derive with actual counters shared into equal groups."
        elif a == "round":
            base = _seed_ints(code + "r", 1, 9)[0] * 1111
            prompt = f"Round {base} to the nearest ten."
            answer = base if base % 10 < 5 else base + (10 - base % 10)
            answered = (base // 10) * 10 + (10 if base % 10 >= 5 else 0)
            answer = answered
            guidance = (f"Correct answer: {answer}. Full credit for the correct "
                        f"rounded value; accept an explained wrong-place attempt "
                        f"with the right rule.")
            miscon = "Rounding down always, or changing digit places."
            follow = "Practise on a number line marked in tens."
        else:  # count
            start, n = _seed_ints(code + "c", 2, 5)
            prompt = f"Count on {n} more from {start} and write the total."
            answer = start + n
            guidance = (f"Correct answer: {answer}. Full credit for the final "
                        f"count written unprompted.")
            miscon = "Skipping a number when counting on across a ten."
            follow = "Count aloud in ones with the learner, then repeat silently."
        return dict(
            prompt=prompt,
            expected_evidence=f"The learner computes {answer} with working "
                              "shown in the exercise book.",
            marking_guidance=guidance,
            misconception=miscon,
            follow_up=follow,
        )
    return None


# ── Assessment items ────────────────────────────────────────────────────────

def _capital(focus: str) -> str:
    f = (focus or "").strip()
    return f[:1].upper() + f[1:] if f else f


def build_assessment_items(
    *,
    indicator: str,
    indicator_code: str = "",
    focus: str,
    subject: str = "",
    class_level: str = "",
    duration_minutes: int = 60,
    context_hint: str = "",
    is_early_years: bool = False,
) -> List[dict]:
    """2–3 deterministic assessment prompts for THIS indicator.

    Always: (1) a recognition/recall starter check, (2) the indicator-action
    check with evidence. Plus (3) one contextual application item when the
    subject teaching has a real everyday frame (not decoration).
    """
    action = _leading_action(indicator)
    if not action:
        return []
    dok = dok_level(indicator, class_level, duration_minutes, action)
    category = _bloom_category(action)
    f = (focus or "the lesson focus").strip()

    items: List[dict] = []

    # 1 — recall/recognition check matched to the action's vocabulary.
    focus_starts_with_action = (f.lower().startswith(action + " ")
                                or f.lower() == action)
    if action in _RECALL_ACTIONS:
        prompt = (f"Quick check (unprompted): {f} — each learner names or "
                  f"points to {f} correctly without help.")
    elif focus_starts_with_action:
        prompt = (f"Quick check: each learner states in one sentence what it "
                  f"means to {f}.")
    else:
        prompt = (f"Quick check: each learner states in one sentence what it "
                  f"means to {action} {f}.")
    items.append(dict(
        prompt=prompt, dok_level=1,
        bloom_category=category,
        expected_evidence=("Correct, unprompted naming/statement from every "
                           "learner; the teacher records who needed a prompt."),
        marking_guidance=("Mark immediately on a class list: tick = correct "
                          "unaided; circle = needed a prompt; blank = re-teach."),
        misconception=("Learners repeat the lesson phrase parrot-fashion "
                        "without attaching it to the object/example."),
        follow_up=("Ask one learner to show an example; if the example contradicts "
                   "the statement, re-model with the class chart before Phase 2 "
                   "continues."),
    ))

    # 2 — the indicator-action check (carries the lesson's real evidence).
    verb_check = activity_library.assessment_for_verb(action, _short(f)) or (
        (f"Each learner demonstrates {f} once, to the agreed criteria.")
        if focus_starts_with_action else
        (f"Each learner demonstrates {action} on {f} once, to the agreed "
         "criteria."))
    items.append(dict(
        prompt=_capital(verb_check.rstrip(".")) + ".",
        dok_level=dok,
        bloom_category=category,
        expected_evidence=("The learner's own work/answer shows the agreed "
                           "success criteria for this indicator."),
        marking_guidance=("Use the success criteria already stated in the "
                          "lesson's Assessment row; award the check when the "
                          "evidence (work, performance or answer) is present."),
        misconception=_misconception_for(category, action),
        follow_up=_follow_up_for(category),
    ))

    # 2b — computed mathematics check where reliable.
    if (subject or "").strip().lower() in ("mathematics", "numeracy",
                                           "maths", "elective mathematics"):
        comp = computed_answer_item(indicator_code or indicator, action, f)
        if comp:
            items.append(dict(
                prompt=comp["prompt"], dok_level=2,
                bloom_category="apply",
                expected_evidence=comp["expected_evidence"],
                marking_guidance=comp["marking_guidance"],
                misconception=comp["misconception"],
                follow_up=comp["follow_up"],
            ))

    # 3 — one contextual application item when a real everyday frame exists.
    hint = (context_hint or "").strip()
    if (hint and not is_early_years and dok >= 2
            and action not in _RECALL_ACTIONS):
        items.append(dict(
            prompt=(f"Apply it: {hint} Learners choose or build one fresh "
                    f"example of {f} from that situation and say why it fits."),
            dok_level=max(2, min(dok, 3)),
            bloom_category=category,
            expected_evidence=("The fresh example is genuinely from the stated "
                               "situation and the reason connects it to the "
                               "indicator."),
            marking_guidance=("Non-negotiables: example fits the situation and "
                              "the reason names the indicator's idea. Anything "
                              "creative beyond that earns full credit."),
            misconception=("Learners copy the classroom example instead of "
                           "building one from the stated context."),
            follow_up=("Acknowledge the classroom copy, then ask 'what would "
                       "change in {ctx}?' and let the learner adapt one "
                       "feature.".format(ctx=hint.split(",")[0].strip().rstrip("."))),
        ))

    return items


def _short(focus: str, max_chars: int = 40) -> str:
    f = (focus or "").strip().rstrip(".")
    return f if len(f) <= max_chars else f[:max_chars].rsplit(" ", 1)[0]


# ── Rubric banks (only lesson-applicable criteria; no invented authority) ───

def _misconception_for(category: str, action: str) -> str:
    return {
        "recall": "Learners recognise the familiar example only and reject "
                  "the fresh one in the check set.",
        "understand": "Learners describe the procedure but not the idea "
                      "(the 'how' without the 'why').",
        "apply": "The method is quoted correctly from the chart but applied "
                 "to the wrong item or in the wrong order.",
        "analyse": "Learners list several true observations yet never state "
                   "the pattern or relationship the analysis asks for.",
        "evaluate": "The judgement is stated with no reason drawn from the "
                    "evidence on the desk.",
        "create": "The product is decorated but does not meet the stated "
                  "criteria for the task.",
        "practice": "Learners go through the motion once but stop before the "
                    "agreed quality level.",
        "communicate": "Answers stay in single-word form when the task "
                       "requires a full spoken or written sentence.",
        "french": "Learners translate word-for-word from English instead of "
                  "using the target expression.",
    }.get(category, "The learner answers from memory of the classroom "
                    "example instead of the fresh check item.")


def _follow_up_for(category: str) -> str:
    return {
        "recall": "Re-model with the chart, then re-check with a fresh "
                  "example in the next lesson's starter.",
        "understand": "Let the learner explain the idea to a partner in "
                      "their own words, then re-check once.",
        "apply": "Re-do one item together on the board, then one item "
                 "independently before the lesson ends.",        "analyse": "Supply one organising frame (a table or two-column "
                   "notes) and ask for one pattern statement.",        "evaluate": "Ask 'which part of the evidence made you decide that?' "
                    "and require a reason before accepting a judgement.",
        "create": "Name ONE missing criterion explicitly and give one "
                  "improvement cycle before final display.",
        "practice": "Pair with a confident peer for one supervised repetition.",
        "communicate": "Give the sentence starter orally, then ask the "
                       "learner to complete it twice.",
        "french": "Re-model the target expression in context, then re-ask "
                  "in a new mini-dialogue.",
    }.get(category, "Re-model once, then re-check with a fresh item the "
                    "same week.")


_RUBRIC_CRITERIA: Dict[str, Tuple[Tuple[str, Tuple[str, str, str, str]], ...]] = {
    # category → ((criterion, (exceeds, meets, developing, needs-support)
    # descriptors), …) — the 4-band shape SHS Planner uses.
    "create": (
        ("Meets the stated criteria of the task", (
            "All criteria met and one exceeded with purpose",
            "All stated criteria met",
            "Most criteria met; one gap",
            "Criteria not yet met")),
        ("Originality / purposeful modification", (
            "Inventive; clearly the learner's own strong idea",
            "Clearly the learner's own idea or a purposeful change",
            "Some own choices visible",
            "Copied or unrelated to the task")),
        ("Explanation of the design/work", (
            "Justifies every choice with reasons tied to the task",
            "Justifies the choices with reasons tied to the task",
            "Partial explanation",
            "Cannot explain the choices")),
        ("Presentation and completeness", (
            "Complete, clear, usable — could be shared as a model",
            "Complete, clear, usable",
            "Mostly complete",
            "Incomplete or unclear")),
    ),
    "evaluate": (
        ("Judgement backed by evidence", (
            "Judgement + specific, well-chosen evidence",
            "Judgement + specific evidence",
            "Judgement with weak evidence",
            "Judgement without evidence")),
        ("Use of the agreed criteria", (
            "Applies the criteria exactly and explains the fit",
            "Applies the criteria exactly",
            "Applies some criteria",
            "Criteria not applied")),
        ("Clarity of the reasoned position", (
            "Fully clear, organised, persuasive",
            "Fully clear and organised",
            "Understandable but thin",
            "Unclear")),
    ),
    "analyse": (
        ("Pattern/relationship identified", (
            "Correct pattern stated with a supporting example",
            "Correct pattern stated",
            "Partly correct",
            "Not stated")),
        ("Evidence used from the source/work", (
            "Evidence quoted or shown and interpreted",
            "Evidence quoted or shown",
            "General reference only",
            "No evidence")),
        ("Accuracy of the recorded analysis", (
            "Accurate, complete, and insightfully noted",
            "Accurate and complete",
            "Minor slips",
            "Inaccurate/incomplete")),
    ),
    "apply": (
        ("Correct method followed", (
            "Method correct throughout, efficiently",
            "Method correct throughout",
            "Method mostly correct",
            "Method not followed")),
        ("Correct result/evidence", (
            "Result correct and verified",
            "Result correct",
            "Small slip in the result",
            "Result incorrect")),
        ("Working / process shown", (
            "Every step shown clearly and explained",
            "Every step shown clearly",
            "Some steps shown",
            "No working shown")),
    ),
    "understand": (
        ("Key idea stated", (
            "Idea stated accurately with a fresh example",
            "Idea stated accurately in own words",
            "Partly accurate",
            "Not the lesson's idea")),
        ("Use of the lesson's key terms", (
            "Terms used correctly and in context",
            "Terms used correctly",
            "Some terms misplaced",
            "Terms not used")),
        ("Response completeness", (
            "Full response plus an extension beyond what was asked",
            "Full response (e.g. 2+2 items as asked)",
            "Partial response",
            "Missing parts")),
    ),
    "practice": (
        ("Accuracy of the performance/skill", (
            "Accurate and fluent to the agreed standard",
            "Accurate to the agreed standard",
            "Mostly accurate",
            "Not yet accurate")),
        ("Confidence / independence", (
            "Independent; helps a peer",
            "Independent, no prompting",
            "Needed light prompting",
            "Needed full support")),
    ),
    "recall": (
        ("Correct recognition/naming", (
            "All check items correct, unprompted, and quick",
            "All check items correct, unprompted",
            "Most correct",
            "Few correct")),
        ("Response independence", (
            "No prompt needed; answers extend the item",
            "No prompt needed",
            "Needed one prompt",
            "Needed repeated prompting")),
    ),
    "communicate": (
        ("Relevance to the task", (
            "On task throughout; elevates the message",
            "On task throughout",
            "Partly on task",
            "Off task")),
        ("Language accuracy/clarity", (
            "Clear, accurate, and engaging",
            "Clear and accurate",
            "Minor errors only",
            "Blocks understanding")),
        ("Completion", (
            "Fully complete and polished",
            "Fully complete",
            "Partly complete",
            "Incomplete")),
    ),
    "french": (
        ("Target expressions used correctly", (
            "Expressions correct, natural, and varied",
            "Expressions correct and natural",
            "Some errors that do not block meaning",
            "Meaning blocked")),
        ("Response in the target language", (
            "Fully in the target language with spontaneous additions",
            "Fully in the target language",
            "Mixed with English",
            "Only English")),
    ),
}


_LEVEL_NAMES = ("4 — exceeds the standard", "3 — meets the standard",
                "2 — developing", "1 — needs support")


def _rubric_criteria_for(category: str, action: str) -> Tuple[Tuple[str, Tuple[str, str, str, str]], ...]:
    """The small, task-relevant criterion set for THIS action's category."""
    criteria = _RUBRIC_CRITERIA.get(category) or _RUBRIC_CRITERIA["apply"]
    # At most four criteria — an ordinary teacher can hold four in view.
    return criteria[:4]


def build_rubric(
    *,
    indicator: str,
    focus: str,
    assessment_text: str = "",
    class_level: str = "",
) -> Optional[dict]:
    """An analytic marking rubric for THIS lesson's product/performance.

    Returns None when the assessment does not genuinely mark a learner-created
    product, performance, investigation or extended response — a short
    oral/written check gets marking guidance in the items only (no rubric
    theatre).
    """
    if _is_early_years(class_level):
        return None
    action = _leading_action(indicator)
    if not action:
        return None
    category = _bloom_category(action)
    productish = (
        category in ("create", "evaluate", "analyse", "practice")
        or action in ("write", "present", "perform", "construct", "install",
                      "build", "make", "draw", "sketch", "compose", "sing",
                      "design", "dramatize", "dramatise", "produce", "publish",
                      "record", "model", "assemble")
    )
    if not productish:
        return None

    criteria: List[dict] = []
    total = 0
    for criterion, descriptors in _rubric_criteria_for(category, action):
        points_max = 4
        entries = []
        for name, desc in zip(_LEVEL_NAMES, descriptors):
            entries.append({"level": name, "descriptor": desc,
                            "points": str(points_max)})
            points_max -= 1
        criteria.append({
            "criterion": criterion,
            "descriptors": entries,
            "points": 4,
        })
        total += 4
    if not criteria:
        return None

    task_action = "reviewed" if action == "assess" else action
    task = (f"The learner's work for {_short(focus, 60)}") \
        if (focus or "").strip().lower().startswith(task_action + " ") \
        else (f"The learner's {task_action} work for {_short(focus, 60)}")
    return dict(
        task=task,
        criteria=criteria,
        total_points=total,
        evidence_to_award=("Award each criterion's points only for evidence "
                           "visible in the learner's work, performance or "
                           "recorded answer — the evidence stated in the "
                           "lesson's Assessment row."),
        authority_note=("SchemeKnit-generated marking guide for this task — "
                        "not an official NaCCA or GES rubric."),
        source="deterministic",
    )

"""Canonical indicator-action interpretation — the single measurability canon.

Priority 2.1's audit found that measurable-verb interpretation lived in two
places that disagreed:

  * ``lesson_rubric._MEASURABLE_VERBS`` — the gate's inventory; stale. It
    lacked verbs the official curriculum itself uses as outcomes
    (``add``, ``multiply``, ``install``, ``indicate``, ``assess``, ``relate``,
    ``recognise``, ``skip count``, French ``écouter``/``lire``, …) and its
    ``any(v in obj.lower())`` membership test matched by SUBSTRING, so
    ``performance`` passed via ``perform`` and ``household`` passed via
    ``use`` while genuinely measurable objectives were hard-rejected as
    ``generic_objective``.

This module is now the ONE source of the measurable-action vocabulary and of
the outcome-verb interpretation. Consumers:

  * ``lesson_rubric`` — ``first_indicator_verb``, criterion c02 and the
    ``generic_objective`` hard failure read the helpers here.
  * ``indicator_interpreter.BLOOM_CATEGORIES`` — kept as the Bloom mapping
    (a different purpose: activity typing), but its verb vocabulary is
    folded into ``ACTIONS`` so the two views cannot contradict each other.
  * ``lesson_builder`` — its lead lexicon combines builder-local verbs with
    these shared actions when deciding whether an indicator lead is a real
    verb or a noun phrase.

Interpretation rules (deterministic, word-boundary exact):

  * Phrases are matched longest-first on ``\\b`` boundaries — ``skip count``
    is one action, ``read`` inside ``already`` never matches.
  * For an INDICATOR the primary action is the FIRST action occurrence in the
    text (left-to-right): that is the instructional intent.
  * For an OBJECTIVE the action is read from the OUTCOME-VERB position —
    directly after ``learners can/will/should (be able to)`` — never merely
    ``somewhere in the sentence``; a later generic mention cannot make an
    objective measurable, and a later measurable mention cannot rescue an
    objective whose stated outcome is vague.
  * Accented (French / Ghanaian-language) action phrases are first-class
    members, matched with the same word-boundary rules.
"""

from __future__ import annotations

import re
from typing import Dict, Tuple

# ── Vocabulary (structured: category → action phrases) ──────────────────────

ACTION_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    # Remember / recall outcomes.
    "recall": (
        "list", "recall", "identify", "name", "state", "define", "label",
        "match", "recognise", "recognize", "describe", "enumerate", "recite",
        "pronounce", "count", "skip count", "trace", "spell",
    ),
    # Understand / compare outcomes.
    "understand": (
        "explain", "summarise", "summarize", "interpret", "classify",
        "categorise", "categorize", "discuss", "paraphrase", "illustrate",
        "clarify", "distinguish between", "distinguish", "compare",
        "contrast", "differentiate", "relate", "give examples", "exemplify",
    ),
    # Apply / problem-solving outcomes (incl. routine mathematics skills).
    "apply": (
        "apply", "use", "demonstrate", "solve", "calculate", "perform",
        "execute", "implement", "construct", "build", "make", "draw",
        "record", "measure", "complete", "practice", "practise", "add",
        "subtract", "multiply", "divide", "compute", "sum", "simplify",
        "convert", "install", "operate", "represent", "model", "round",
        "express", "arrange", "sort", "solve", "test", "select", "choose",
        "skip", "layout", "blend",
    ),
    # Analyse / investigate outcomes.
    "analyse": (
        "analyse", "analyze", "examine", "investigate", "explore",
        "differentiate", "break down", "organise", "organize", "find",
        "determine", "sequence", "indicate", "observe", "predict",
        "experiment", "discover", "propose",
    ),
    # Evaluate / judge outcomes.
    "evaluate": (
        "evaluate", "assess", "judge", "justify", "critique", "review",
        "argue", "defend", "prioritise", "prioritize", "recommend",
        "decide", "rate", "appraise",
    ),
    # Create / design outcomes.
    "create": (
        "create", "design", "develop", "formulate", "compose", "produce",
        "plan", "invent", "devise", "originate", "write", "assemble",
        "draft", "generate", "derive", "extend", "solve", "sketch",
        "produce", "interview", "rehearse", "publish", "present", "report",
    ),
    # Communicate / language & performance outcomes.
    "communicate": (
        "ask", "respond", "role play", "participate", "write", "read",
        "read aloud", "listen", "speak", "tell", "answer", "share",
        "retell", "recount", "narrate", "pluralise", "translate",
        "pronounce", "elaborate", "mention", "outline", "browse", "follow",
        "study", "preview", "sample",
    ),
    # Guided practice / musical & arts actions observed in real schemes.
    "practice": (
        "sing", "colour", "color", "paste", "fold", "cut", "play",
        "drum", "performance", "maintain", "monitor", "format", "insert",
        "edit", "proofread", "dramatize", "dramatise", "denote", "pay",
    ),
    # French curriculum outcomes (only where the product supports that
    # curriculum). First-class phrases, same word-boundary rules.
    "french": (
        "écouter", "lire", "écrire", "parler", "répéter", "décrire",
        "identifier", "répondre", "traduire", "nommer", "compter",
        "saluer", "présenter", "conjuguer", "lire à haute voix",
    ),
}

#: All measurable action phrases (multiword entries included).
ACTIONS: Tuple[str, ...] = tuple(
    sorted(
        {phrase for phrases in ACTION_CATEGORIES.values() for phrase in phrases},
        key=lambda p: (-len(p), p),   # longest phrase first in the regex
    )
)

_ACTIONS_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in ACTIONS) + r")\b",
    re.I,
)

#: Bloom level mapping retained from the interpreter for callers that need a
#: coarse category for a matched action (None → the phrase maps manually).
_BLOOM_OF: Dict[str, str] = {}
for _cat, _phrases in ACTION_CATEGORIES.items():
    for _p in _phrases:
        _BLOOM_OF.setdefault(_p, _cat)

# ── Text preparation ────────────────────────────────────────────────────────

_LEADING_CODE_RE = re.compile(r"^\s*[A-Za-z]{0,3}\d[\d.]*\s+")

#: Preambles real schemes write before the action verb. Stripped before the
#: action search; they may themselves contain the word "learners".
_PREAMBLES = (
    r"(?:by the end of the (?:lesson|sub-?strand|indicator),? )?",
    r"(?:learners?\s+(?:can|will|should be able to|should|are able to)\s+"
    r"(?:be able to\s+)?)",
    r"(?:to\s+)",
)


def _strip_preamble(text: str) -> str:
    t = _LEADING_CODE_RE.sub("", text or "")
    changed = True
    while changed:
        changed = False
        for pat in _PREAMBLES:
            stripped = re.sub(r"^" + pat, "", t, flags=re.I)
            if stripped != t:
                t = stripped.lstrip()
                changed = True
    return t.lstrip()


# ── Interpretation helpers ──────────────────────────────────────────────────


def leading_action(text: str) -> str:
    """First measurable action of an indicator (its instructional intent).

    Code prefixes and ``learners can …`` preambles are removed first; the
    first word-boundary action remaining IS the primary verb — later generic
    or secondary verbs never override it.
    """
    match = _ACTIONS_RE.search(_strip_preamble(text or ""))
    return match.group(0).lower() if match else ""


def outcome_action(objective: str) -> str:
    """The objective's OUTCOME verb (measurable action at that position, or "")."""
    obj = objective or ""
    marker = re.search(
        r"\blearners?\b[^\n]{0,40}\b(?:can|will|should be able to|should|"
        r"are able to|be able to)\b(?:\s+be able to)?\s*:?(?=\s|\Z)",
        obj, re.I,
    )
    if marker:
        # The outcome verb is whatever follows the marker (any residual
        # "to" preamble included), at word boundary.
        match = _ACTIONS_RE.search(_strip_preamble(obj[marker.end():]))
        if match:
            return match.group(0).lower()
        return ""
    # No "learners …" phrasing: fall back to the first action in the text.
    match = _ACTIONS_RE.search(_strip_preamble(obj))
    return match.group(0).lower() if match else ""


def bloom_category(action: str) -> str:
    """Coarse category of a matched action ("" when unknown)."""
    return _BLOOM_OF.get((action or "").lower(), "")

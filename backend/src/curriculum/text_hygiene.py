"""Deterministic text hygiene for generated lesson prose (Phase 6/7).

One shared layer for BOTH generation paths (deterministic and Zeli): the
functions here detect and — only where a fix is provably safe — repair the
mechanical defects seen in the Basic 9 Science regression fixture:

* duplicated consecutive words ("the the")
* sentence concatenation without a boundary ("...compounds Describe the...")
* incomplete sentences that end on a preposition/connector ("...explain it in.")
* truncated ellipses left by clipped drafting ("...from the…")
* unbalanced quotes/brackets
* stray mid-dot drafting labels ("Step 2 · Classify", raw "NS:" / "MA:")
* ordinary words wrongly capitalised after a lead-in ("Learners can Identify")
* title-cased ordinary resource names ("Charts And Pictures")

The module NEVER rewrites curriculum source statements: it only normalises
mechanical presentation. Anything it cannot fix deterministically is reported
by :func:`quality_issues` so the caller can flag or regenerate the field.
"""

from __future__ import annotations

import re
from typing import List

__all__ = [
    "normalize_prose",
    "fix_capitalisation",
    "lowercase_after_lead",
    "title_case_resource",
    "strip_drafting_markers",
    "complete_or_clean_clause",
    "fix_resource_capitalisation",
    "quality_issues",
    "hygiene_pass",
]

# Words that stay lowercase in a resource title ("Charts and Pictures").
_TITLE_SMALL_WORDS = frozenset(
    "a an and as at but by for from in into nor of on onto or per the to with"
    .split())

# Ordinary verbs/adjectives wrongly capitalised after a lead-in such as
# "Learners can Identify" — matched only against a known ordinary word so
# proper nouns, acronyms and scientific terms are never lowercased.
_ORDINARY_CAP_WORDS = frozenset(
    "identify discuss describe explain name state list compare classify sort "
    "demonstrate observe measure record draw write read count calculate group "
    "arrange collect present predict evaluate analyse analyze design create "
    "prepare show use make find give tell share answer ask match order mix "
    "separate perform produce suggest suggest interpret investigate explore "
    "apply construct illustrate outline summarise summarize justify support "
    "report display select choose determine distinguish differentiate"
    .split())

# Internal drafting labels that must never reach a printed plan.
_DRAFTING_LABELS = (
    ("What to look for:", "As learners respond, note:"),
    ("What to look/for:", "As learners respond, note:"),
    ("Look for:", "Note:"),
    ("Watch for:", "Note common errors:"),
    ("Exit check:", "Before the class leaves,"),
    ("Quick check (unprompted):", "Quick check:"),
)

_MID_DOT_LABEL_RE = re.compile(r"Step\s+\d+\s*·\s*[^:]{0,40}:\s*")
_RAW_BAND_RE = re.compile(r"\((?:NS|MA|HP)\s*:[^)]*\)")

_DUPLICATE_WORD_RE = re.compile(
    r"\b(\w+)\s+\1\b", re.IGNORECASE)

# A capitalised ordinary word glued directly onto the end of a sentence with
# no punctuation ("...binary chemical compounds Describe the characteristics")
# — a concatenated-list defect. The word BEFORE the capital decides: after a
# modal/infinitive lead-in ("can Identify") this is mere capitalisation, not
# concatenation, and only the capitalisation fix may apply.
_CONCAT_RE = re.compile(
    r"([A-Za-z]+)\s(Identify|Describe|Discuss|Explain|State|List|Demonstrate|"
    r"Classify|Compare|Measure|Observe|Record|Calculate|Analyse|Analyze|"
    r"Evaluate|Investigate|Explore|Apply|Construct|Illustrate|Summarise|"
    r"Summarize|Perform|Prepare|Present|Predict|Distinguish|Differentiate)\b")
_CONCAT_LEADINS = frozenset(
    "can cannot could may might must shall should will would to and or then "
    "help let able ableto"
    .split())

# Incomplete-sentence endings: a sentence finishing on a dangling connector or
# preposition, or a truncation ellipsis left by clipped drafting.
_DANGLING_END_RE = re.compile(
    r"\b(?:and|or|but|to|of|in|on|for|with|from|the|a|an|their|its|by|about|"
    r"into|that|which|who|is|are|was|were|what|when|where|how|explain it in)\s*[\.\,]?\s*$",
    re.IGNORECASE,
)
_TRAILING_ELLIPSIS_RE = re.compile(r"(?:\.{3}|…)\s*$")

_DANGLING_TAIL_WORD = re.compile(
    r"^(?:and|or|but|to|of|in|on|for|with|from|the|a|an|their|its|by|about|"
    r"into|that|which|who|it|them|is|are|was|were|what|when|where|how|says?|"
    r"state|states)$", re.IGNORECASE)


def _trim_dangling_tail_sentence(text: str, min_words: int = 5) -> str:
    """Cut a trailing incomplete clause ("...and explain it in.") back to the
    last complete sentence, leaving prose that ends on a content word."""
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if not sentences:
        return text
    last = sentences[-1]
    words = last.split(" ")
    changed = False
    while (len(words) > min_words
           and (_DANGLING_TAIL_WORD.match(words[-1].strip(".,;:"))
                or words[-1].strip(".,;:").lower() in ("in",))):
        words.pop()
        changed = True
    if changed:
        rebuilt = " ".join(words).rstrip(" ,;:")
        if rebuilt and not rebuilt.endswith((".", "!", "?")):
            rebuilt += "."
        sentences[-1] = rebuilt
        return " ".join(sentences)
    return text


def normalize_prose(text: str) -> str:
    """Repair safe mechanical defects; returns clean prose.

    Order matters: drafting labels first (they may introduce duplicated
    words), then whitespace/punctuation repairs.
    """
    if not text:
        return text
    out = strip_drafting_markers(text)
    # Duplicated consecutive words (keep legitimate repeats like "had had"
    # out of scope: only 2+ letter words that repeat immediately).
    out = _DUPLICATE_WORD_RE.sub(
        lambda m: m.group(1) if len(m.group(1)) > 1 else m.group(0), out)
    # Missing sentence boundary between concatenated statements — but never
    # after a modal/infinitive lead-in ("can Identify" is capitalisation).
    def _concat_repl(m: "re.Match") -> str:
        if m.group(1).lower() in _CONCAT_LEADINS:
            return m.group(0)
        return f"{m.group(1)}. {m.group(2)}"
    out = _CONCAT_RE.sub(_concat_repl, out)
    # Tidy separators and spacing.
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", out)
    out = re.sub(r"\.{2,}", ".", out)
    out = _trim_dangling_tail_sentence(out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def fix_capitalisation(text: str) -> str:
    """Sentence-case ordinary words; protect acronyms, codes and proper nouns.

    Fixes "Learners can Identify by name..." → "Learners can identify by
    name..." without touching "GES", "B9.1.1.1" or a name like "Ghana".
    Words that start a sentence keep their capital.
    """
    if not text:
        return text
    out = []
    starts_sentence = True
    for w in text.split(" "):
        bare = w.strip("(),.;:'\"")
        if (not starts_sentence
                and bare
                and bare[0].isupper()
                and bare.lower() in _ORDINARY_CAP_WORDS
                and bare != "I"):
            w = w.replace(bare, bare.lower(), 1)
        out.append(w)
        # Sentence-boundary signal comes from the RAW word: "compounds." ends
        # a sentence even though the bare form is "compounds", and a token
        # ending in a digit is a curriculum code ("B9.1.1.1 Show ...") — the
        # word after it starts the statement.
        starts_sentence = w[-1:] in ".!?" or bool(w[-1:].isdigit())
    return " ".join(out)


def lowercase_after_lead(text: str, lead: str) -> str:
    """Lowercase the first ordinary word following ``lead`` (e.g. "Learners can")."""
    pattern = re.compile(
        re.escape(lead) + r"\s+([A-Z][a-z]+)", re.UNICODE)
    def _lower(m: "re.Match") -> str:
        word = m.group(1)
        if word.lower() in _ORDINARY_CAP_WORDS:
            return f"{lead} {word.lower()}"
        return m.group(0)
    return pattern.sub(_lower, text)


def title_case_resource(text: str) -> str:
    """Title-case an ordinary resource name, small words lowercase.

    "Charts And Pictures" → "Charts and Pictures"; "TLR cards" keeps its
    acronym; "NHIS card" keeps "NHIS".
    """
    words = (text or "").strip().split(" ")
    out = []
    for i, w in enumerate(words):
        bare = w.strip("(),.:")
        if not bare:
            out.append(w)
            continue
        if any(c.isupper() for c in bare[1:]):
            out.append(w)  # acronym or CamelTerm — never touch
            continue
        if i > 0 and bare.lower() in _TITLE_SMALL_WORDS:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower() if bare.islower() else w)
    return " ".join(out)


def fix_resource_capitalisation(text: str) -> str:
    """Repair ONLY the defective pattern in a resource name.

    Applies when EVERY word of the item is capitalised AND a small word sits
    wrongly capitalised mid-name ("Charts And Pictures"). Anything else —
    sentence case, acronyms, single words — is returned untouched, so
    legitimate names like "Holy Bible" or "NHIS card" never change.
    """
    words = (text or "").strip().split(" ")
    if len(words) < 2 or not all(w[:1].isupper() for w in words if w):
        return text
    out = []
    for i, w in enumerate(words):
        bare = w.strip("(),.:")
        if i > 0 and bare.lower() in _TITLE_SMALL_WORDS and bare[0].isupper():
            out.append(w.replace(bare, bare.lower(), 1))
        else:
            out.append(w)
    return " ".join(out)


def strip_drafting_markers(text: str) -> str:
    """Replace known internal drafting labels with teacher-facing wording."""
    out = text or ""
    for label, replacement in _DRAFTING_LABELS:
        out = out.replace(label, replacement)
    # Raw band markers "(NS: ...; MA: ...)" → teacher-facing differentiation.
    def _band_repl(m: "re.Match") -> str:
        body = m.group(0)
        parts = []
        for tag, name in (("NS", "For learners needing support"),
                          ("MA", "For learners ready for more"),
                          ("HP", "For learners working at a higher level")):
            seg = re.search(rf"{tag}\s*:\s*([^;)]*)", body)
            if seg and seg.group(1).strip():
                parts.append(f"{name}: {seg.group(1).strip().rstrip('.,;')}")
        return "; ".join(parts)
    out = _RAW_BAND_RE.sub(_band_repl, out)
    # Mid-dot step labels: "Step 2 · Classify:" → "Step 2:".
    out = _MID_DOT_LABEL_RE.sub(
        lambda m: re.match(r"Step\s+\d+", m.group(0)).group(0) + ": ", out)
    return out


def complete_or_clean_clause(text: str, max_words: int = 22) -> str:
    """Shorten a clause WITHOUT leaving a truncated "…" fragment.

    The old behaviour clipped mid-sentence and appended "…", which produced
    the fixture's "plus two key words from the…" defects. A clause longer
    than the cap is cut at a word boundary and closed with a full stop; the
    result is always a complete, punctuated fragment of prose.
    """
    out = _TRAILING_ELLIPSIS_RE.sub(".", (text or "").strip())
    if not out:
        return out
    words = out.split(" ")
    if len(words) > max_words:
        out = " ".join(words[:max_words]).rstrip(" ,;:.…")
        if not out.endswith((".", "!", "?")):
            out += "."
    if not out.endswith((".", "!", "?")):
        out += "."
    return out


def quality_issues(text: str) -> List[str]:
    """Defects that need regeneration or review — not safe to auto-fix.

    Returns human-readable issue strings; empty list means the text passed.
    """
    issues: List[str] = []
    if not text or not text.strip():
        return issues
    stripped = text.strip()
    if _TRAILING_ELLIPSIS_RE.search(stripped):
        issues.append("truncated ellipsis in an intended-complete sentence")
    if _DANGLING_END_RE.search(stripped.rstrip(" .").rstrip()) and len(
            stripped.split()) > 3:
        issues.append("sentence ends on a dangling connector or preposition")
    if re.search(r"[\(\[\{]", stripped) and not re.search(r"[\)\]\}]", stripped):
        issues.append("unbalanced bracket or quote")
    if re.search(r"Step\s+\d+\s*·", stripped):
        issues.append("internal mid-dot step label present")
    if re.search(r"\b(?:NS|MA|HP)\s*:", stripped):
        issues.append("raw differentiation band marker present")
    if "Quick check (unprompted)" in stripped:
        issues.append("internal drafting label present")
    return issues


def hygiene_pass(text: str) -> str:
    """Full deterministic cleanup for one generated prose field."""
    if not text:
        return text
    out = normalize_prose(text)
    out = fix_capitalisation(out)
    out = lowercase_after_lead(out, "Learners can")
    out = lowercase_after_lead(out, "learners can")
    return out

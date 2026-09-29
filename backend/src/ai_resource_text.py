"""
SchemeKnit Canonical Resource & List Text Normalization
=======================================================

ONE canonical definition of how scheme-sourced list text (resources / TLRs /
keywords / competencies / references) is normalized. Every layer that reads a
possibly-dirty stored value — parser, allocation, lesson builder, persistence,
API payloads, exports — funnels through this module so a serialized list can
never leak into the UI or an exported document:

  * ``["a", "b"]`` stored as text  ->  ["a", "b"]      (JSON string payload)
  * ``["Pictures showing Created things, Holy Bible, Holy Quran."]``
                                       ->  ["Pictures showing Created things",
                                            "Holy Bible",
                                            "Holy Quran"]
  * ``"A, B; C"``                  ->  ["A", "B", "C"]
  * ``"[]"`` / ``"[,]"`` / ``[""]``->  []              (empty stays truly empty)
  * ``"PicturesshowingCreatedthings"`` ->  reconstructed with spaces (best
    effort, using a built-in TLR/curriculum word list plus camel-hump splits)
  * ``"[Picturesshowing…]"``       ->  ["Pictures showing …"]  (no literal brackets)

Rules honoured (real-use remediation PART 6/7):
  * meaningful phrases are never split: a comma inside a single item only
    splits when the surrounding fragments are plausible standalone resources
    (>= 2 characters, not a dangling article/preposition fragment);
  * bracketed display text is unwrapped instead of shown literally;
  * empty representations are canonical ``[]`` — never null, never [""].
"""

from __future__ import annotations

import json
import re
from typing import Any, List

__all__ = [
    "normalize_text_items",
    "normalize_text",
    "clean_serialized_text",
    "normalize_structured_references",
    "strip_internal_markers",
    "looks_internal",
]

#: Internal artefacts that must NEVER reach a teacher-visible field or an
#: export (PART 21): acceptance-harness markers, epoch-millisecond stamps,
#: fixture/debug labels, and the icon/serialization leak that once printed
#: "svgSuggest" beside a workspace heading. These are matched as WHOLE tokens so
#: ordinary lesson prose is never damaged.
_INTERNAL_MARKER_RE = re.compile(
    r"\b(?:test|debug|fixture|internal|acceptance)\s*(?:marker|fixture|id|run)?\b"
    r"[^.!?\n]{0,80}?\b\d{9,13}\b",
    re.IGNORECASE,
)

#: A bare 13-digit integer starting with 1 or 2 is an epoch-millisecond
#: stamp (2001–2100), never prose. Exactly 12 digits is deliberately NOT
#: matched: that era ended in 2001, and a uuid4's 12-hex-character segment
#: is all-decimal often enough (~1 in 1300) to misfire on legitimate ids —
#: which ``strip_internal_markers`` would then delete.
_EPOCH_STAMP_RE = re.compile(r"\b[12]\d{12}\b")

#: Known icon/serialization leaks that have appeared in the workspace text.
_ICON_LEAK_RE = re.compile(r"\bsvg(?=[A-Z][a-z])")


def looks_internal(text: str) -> bool:
    """True when ``text`` contains an internal/test artefact (PART 21)."""
    if not text:
        return False
    return bool(
        _INTERNAL_MARKER_RE.search(text)
        or _EPOCH_STAMP_RE.search(text)
        or _ICON_LEAK_RE.search(text)
    )


def strip_internal_markers(text: Any) -> str:
    """Remove internal/test artefacts from a teacher-visible string.

    Applied at the persistence boundary so a harness marker, a debug label or an
    epoch stamp can never be saved onto a lesson and then exported. Ordinary
    prose is untouched: only unambiguous internal shapes are removed, and any
    leftover separator whitespace is collapsed. Never raises.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text or not looks_internal(text):
        return text
    cleaned = _INTERNAL_MARKER_RE.sub(" ", text)
    cleaned = _EPOCH_STAMP_RE.sub("", cleaned)
    cleaned = _ICON_LEAK_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t-–—,;:")
    return cleaned


#: Fragments too weak to stand alone as a resource after a comma split.
_FRAGILE_TAIL = (
    "and", "or", "with", "of", "for", "the", "a", "an", "in", "on", "to",
    "showing", "e.g", "eg", "including",
)

#: Dictionary-lite word list for reconstructing jammed words in the TLR /
#: curriculum domain. Word-boundary matched so short codes never collide.
_KNOWN_WORDS = (
    "pictures", "picture", "charts", "chart", "counters", "counter",
    "sticks", "stick", "flash", "cards", "card", "bible", "quran",
    "holy", "created", "things", "thing", "showing", "shapes", "shape",
    "blocks", "block", "beads", "bead", "buttons", "button",
    "bottles", "bottle", "caps", "cap", "leaves", "leaf", "stones",
    "stone", "pebbles", "pebble", "water", "sand", "soil", "clay",
    "pencils", "pencil", "crayons", "crayon", "pens", "pen",
    "markers", "marker", "rulers", "ruler", "scissors", "scissor",
    "glue", "paper", "books", "book", "story", "stories",
    "globes", "globe", "models", "model", "toys", "toy", "dolls", "doll",
    "plants", "plant", "animals", "animal", "seeds", "seed",
    "colours", "colour", "colors", "color", "numbers", "number",
    "letters", "letter", "words", "word", "sounds", "sound",
    "objects", "object", "materials", "material", "resources",
    "resource", "written", "cut", "out", "real", "objects",
)

_KNOWN_WORD_RE = re.compile(
    "|".join(re.escape(w) for w in _KNOWN_WORDS),
    re.IGNORECASE,
)


def _is_plausible_item(text: str) -> bool:
    """A fragment that can stand alone as one resource / keyword."""
    if not text:
        return False
    stripped = text.strip().strip(",;.")
    if len(stripped) < 2:
        return False
    tail = stripped.rsplit(" ", 1)[-1].lower().rstrip(".,;")
    if tail in _FRAGILE_TAIL:
        return False
    return True


def _looks_space_stripped(text: str) -> bool:
    """True when the string has letter runs that look like jammed words.

    Detects either a run of >= 8 letters with no space/digit AND a
    capital-letter transition inside it, OR a run of >= 14 letters whose
    whole body is lowercase-only (``holybiblequran`` style). Ordinary words,
    names and codes never match.
    """
    for run in re.findall(r"[A-Za-z]{8,}", text):
        if re.search(r"[a-z][A-Z]", run) or re.search(r"[A-Z][a-z]+[A-Z]", run):
            return True
        if len(run) >= 14 and run.isalpha() and run.islower():
            return True
    return False


def _reinsert_spaces(text: str) -> str:
    """Best-effort word reconstruction inside jammed letter runs.

    Strategy, applied only inside runs of >= 8 letters:
      1. Split before every uppercase letter that follows a lowercase one
         (``PicturesshowingCreatedthings`` -> ``Pictures showing Created
         things``).
      2. Inside each resulting chunk, split before known TLR/curriculum
         words (``HolyBible`` -> ``Holy Bible`` via the known-word list;
         ``Createdthings`` -> ``Created things`` likewise).
    Human-written text with normal spaces never reaches this path.
    """

    def _split_known_words(chunk: str) -> List[str]:
        # Split the chunk at known TLR/curriculum words, greedily left-to-right.
        out: List[str] = []
        pos = 0
        matches = list(_KNOWN_WORD_RE.finditer(chunk))
        if not matches:
            return [chunk]
        # The heuristic is only trusted when the known words account for the
        # WHOLE chunk ("Picturesshowing" -> Pictures|showing). A partial hit
        # ("happen" contains "pen") is coincidence — keep the chunk whole.
        covered = sum(m.end() - m.start() for m in matches)
        if covered < len(chunk):
            return [chunk]
        consumed_until = 0
        for m in matches:
            if m.start() < consumed_until:
                continue
            head = chunk[consumed_until:m.start()]
            word = chunk[m.start():m.end()]
            if head:
                out.append(head)
            out.append(word)
            consumed_until = m.end()
        tail = chunk[consumed_until:]
        if tail:
            out.append(tail)
        return out

    def _fix_run(match: re.Match) -> str:
        run = match.group(0)
        # 1. camel-hump split.
        pieces = re.findall(r"[A-Z][a-z]*|[^A-Z]+", run)
        words: List[str] = []
        for piece in pieces:
            if len(piece) <= 2 and words and words[-1].islower():
                words[-1] += piece  # glue stray capitals back
            else:
                words.append(piece)
        # 2. known-word split inside lowercase chunks.
        final: List[str] = []
        for chunk in words:
            final.extend(_split_known_words(chunk))
        if len(final) <= 1:
            return run
        return " ".join(w for w in final if w)

    return re.sub(r"[A-Za-z]{8,}", _fix_run, text)


def clean_serialized_text(text: str) -> str:
    """Repair one display string that carries serialized-list damage.

    ``"[PicturesshowingCreatedthings,HolyBible]"`` becomes
    ``"Pictures showing Created things, Holy Bible"`` — brackets removed and
    missing word gaps reconstructed. Human-written text with normal spaces is
    returned untouched.
    """
    if not isinstance(text, str):
        return text
    cleaned = text.strip()
    # Unwrap a single wrapping pair of [ ] (display damage, not JSON).
    if len(cleaned) >= 2 and cleaned[0] == "[" and cleaned[-1] == "]":
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return ""
    if not _looks_space_stripped(cleaned):
        return cleaned
    return _reinsert_spaces(cleaned)


def _split_items(text: str) -> List[str]:
    """Split one raw item on commas/semicolons/newlines/bullets safely.

    A comma only splits when both sides remain plausible standalone items —
    ``Pictures showing Created things`` survives as one resource, while a
    genuine list ``Counters, sticks, flash cards`` becomes three items.
    """
    parts = re.split(r"[;\n\r•·|]|•\s*", text)
    out: List[str] = []
    for chunk in parts:
        chunk = chunk.strip()
        if not chunk:
            continue
        subparts = [p.strip() for p in chunk.split(",")]
        # Fast path: single fragment, nothing to decide.
        if len(subparts) == 1:
            out.append(subparts[0])
            continue
        merged: List[str] = []
        for part in subparts:
            if not part:
                continue
            prev = merged[-1] if merged else None
            prev_fragile = prev is not None and not _is_plausible_item(prev)
            # Keep the comma when the previous fragment cannot stand alone
            # ("Pictures showing" + "Created things") or the fragment is a
            # bare short fragment (list numbering like "1)").
            if prev_fragile:
                merged[-1] = f"{prev}, {part}"
            elif not _is_plausible_item(part) and len(part) <= 2:
                merged[-1] = f"{prev}, {part}" if prev else part
            else:
                merged.append(part)
        if merged:
            out.extend(merged)
    return out


def _parse_bracketed(text: str) -> List[str] | None:
    """Parse a serialized python/json list payload into raw items."""
    s = text.strip()
    if not (s.startswith("[") or s.startswith("(")):
        return None
    try:
        value = json.loads(s)
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, tuple):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [value]
        return None
    except Exception:
        pass
    # Python-style payload with quotes json cannot read: take the inner text.
    inner = s[1:-1]
    if not inner.strip():
        return []
    # Quotes around elements are display damage; strip them.
    inner = inner.replace("'", '"')
    try:
        value = json.loads(f"[{inner}]")
        return [str(v) for v in value]
    except Exception:
        return [inner]


def normalize_text_items(value: Any) -> List[str]:
    """Canonical list[str] for ANY stored list-typed value (PART 11).

    Accepts a list, a JSON/python serialized string, or plain text and
    returns clean, individually-displayable items. Never returns ``[""]``,
    ``[" "]`` or bracket-wrapped display text; empty input returns ``[]``.
    """
    if value is None:
        return []

    items: List[str] = []
    if isinstance(value, str):
        parsed = _parse_bracketed(value)
        raw_items = parsed if parsed is not None else [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(v) for v in value]
    else:
        raw_items = [str(value)]

    for raw in raw_items:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text or text.lower() in ("null", "none", "undefined", "n/a", "na"):
            continue
        for piece in _split_items(clean_serialized_text(text)):
            piece = piece.strip().strip(",;.").strip()
            piece = re.sub(r"\s+", " ", piece)
            if piece:
                items.append(piece)

    # Deduplicate, case-insensitively, preserving order.
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def normalize_text(value: Any) -> str:
    """Canonical single-line text for values that must never show brackets."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return clean_serialized_text(text).strip()


def normalize_structured_references(value: Any) -> List[Any]:
    """Canonical structured-reference entries from ANY stored shape.

    Production rows stored ``structured_references`` in corrupted shapes —
    a JSON-encoded string (``"[]"`` / ``"[{...}]"``), a string that was
    iterated into characters (``["[", "]"]``), or a mix of dicts and junk.
    A raw read of any of those crashed exports with a pydantic
    ValidationError (unhandled 500). Every layer that reads this field
    funnels through here so only real entries (dicts or pydantic models)
    ever reach the UI or an export.

    * ``None`` / non-list shapes         -> ``[]``
    * JSON string (``"[...]"``, ``"[]"``) -> parsed entries
    * char-split garbage (``["[", "]"]``) -> recovered when possible, else `[]`
    * dict / pydantic entries            -> passed through untouched
    * anything else                      -> dropped
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            # Not JSON at all (plain text was stored) — not an entry.
            return []
        if isinstance(parsed, str):
            # Guard against pathological re-parses: a string never nests.
            return []
        return normalize_structured_references(parsed)
    if not isinstance(value, (list, tuple)):
        return []
    value = list(value)
    if value and all(isinstance(i, str) and len(i) <= 1 for i in value):
        # A string iterated into characters (list("[]") / list("[{...}]")).
        # Real entries are always dicts, so a list of 1-char strings can only
        # be this corruption — rejoin and re-parse.
        return normalize_structured_references("".join(value))
    out: List[Any] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            # Char-split garbage ('[', ']', '"', ...) or an embedded
            # JSON-encoded entry. Only a parseable dict/list is recoverable.
            try:
                parsed = json.loads(item)
            except Exception:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
            elif isinstance(parsed, list):
                out.extend(normalize_structured_references(parsed))
        elif hasattr(item, "model_dump"):
            # Pydantic ReferenceEntry instances (in-memory pipeline values).
            out.append(item)
    return out

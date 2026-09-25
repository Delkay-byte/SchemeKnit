"""
WAPEF special curriculum fields — canonical approved values.

The four WAPEF fields (Deep Hope, Storyline, Through lines, God's Story) are
STRUCTURED curriculum/context selections, not free text and not AI fields:

- the teacher selects them from the approved option lists below;
- the AI may use them as instructional context but must NEVER choose,
  rewrite or overwrite them ("Teacher selection wins");
- the selected values survive create → review → save → reload → generation
  → preview → DOCX export → PDF export verbatim.

The approved spellings are the source of truth and are preserved exactly
(including "Idolatry descerner" and "Beauty creator") — they must not be
silently converted to alternative labels such as "Earth-keeping".
"""

from typing import List, Optional

#: Current approved selectable Deep Hope values (the board may add more later;
#: the list is the single source of truth for the dropdown and validation).
WAPEF_DEEP_HOPES: List[str] = [
    "Learners will recognize and appreciate the beauty, order, and purpose "
    "of design in the physical world around them.",
]

#: Current approved selectable Storyline values.
WAPEF_STORYLINES: List[str] = [
    "Shaping our world.",
]

#: Approved Through lines, in approved display order. Multi-select; when
#: several are selected the export lists them in THIS order.
WAPEF_THROUGH_LINES: List[str] = [
    "God worshiper",
    "Image reflector",
    "Earth keeper",
    "Justice seeker",
    "Community builder",
    "Idolatry descerner",
    "Order discoverer",
    "Servant worker",
    "Creation enjoyer",
    "Beauty creator",
]

#: Approved God's Story categories.
WAPEF_GODS_STORY: List[str] = [
    "Creation",
    "Fall",
    "Redemption",
    "Restoration",
]


def _canonical(value: str, approved: List[str]) -> Optional[str]:
    """Match a stored value onto an approved label (case/whitespace-insensitive).

    Returns the canonical approved label, or None when the value is not an
    approved option (never invented).
    """
    if not value or not isinstance(value, str):
        return None
    wanted = " ".join(value.split()).strip().lower().rstrip(".")
    for option in approved:
        if " ".join(option.split()).strip().lower().rstrip(".") == wanted:
            return option
    return None


def normalize_deep_hope(value) -> str:
    """Canonical Deep Hope label or '' (unknown values are dropped, never kept loose)."""
    return _canonical(value, WAPEF_DEEP_HOPES) or ""


def normalize_storyline(value) -> str:
    """Canonical Storyline label or ''."""
    return _canonical(value, WAPEF_STORYLINES) or ""


def normalize_gods_story(value) -> str:
    """Canonical God's Story label or ''."""
    return _canonical(value, WAPEF_GODS_STORY) or ""


def normalize_through_lines(values) -> List[str]:
    """Canonical Through lines in APPROVED ORDER, deduplicated, options only.

    Unknown values are silently dropped (they are never invented labels), and
    the output order is always the approved option order regardless of the
    order the teacher clicked.
    """
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    canonical = []
    for option in WAPEF_THROUGH_LINES:
        for value in values:
            if _canonical(value, [option]) == option:
                if option not in canonical:
                    canonical.append(option)
                break
    return canonical


def normalize_wapef_payload(data) -> dict:
    """Normalize a teacher-supplied WAPEF selection payload to canonical form.

    Returns {"deep_hope", "storyline", "through_lines", "gods_story"} with
    only approved values; anything else becomes empty. Never raises.

    Accepts both key spellings — the bare canonical keys and the API/draft
    store convention (``wapef_deep_hope``, …). The prefixed keys win when both
    are present, so an API payload can never be silently dropped just because
    the caller used the frontend's field names.
    """
    data = data if isinstance(data, dict) else {}

    def _pick(bare: str):
        prefixed = f"wapef_{bare}"
        value = data.get(prefixed)
        if value is None or value == "" and bare in data:
            value = data.get(bare, value)
        return value

    return {
        "deep_hope": normalize_deep_hope(_pick("deep_hope")),
        "storyline": normalize_storyline(_pick("storyline")),
        "through_lines": normalize_through_lines(_pick("through_lines")),
        "gods_story": normalize_gods_story(_pick("gods_story")),
    }


def wapef_options() -> dict:
    """The approved option lists, for the review UI dropdowns."""
    return {
        "deep_hopes": list(WAPEF_DEEP_HOPES),
        "storylines": list(WAPEF_STORYLINES),
        "through_lines": list(WAPEF_THROUGH_LINES),
        "gods_story": list(WAPEF_GODS_STORY),
    }


def format_through_lines(lines: List[str]) -> str:
    """Render selected Through lines for the exported plan.

    Approved-order is enforced upstream; here two values join naturally with
    "and" (matching real WAPEF plan prose), more with commas.
    """
    lines = [l for l in (lines or []) if l]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    if len(lines) == 2:
        return f"{lines[0]} and {lines[1]}"
    return ", ".join(lines[:-1]) + f" and {lines[-1]}"

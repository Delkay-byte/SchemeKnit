"""
Lesson vocabulary selection shared by every template (WAPEF and GES).

The generator must not copy the Teaching & Learning Resources list into the
Keywords cell, and it must not tokenize an indicator into a bag of words. This
module implements the selection rules the NaCCA curriculum guidance implies:

* vocabulary is chosen from the lesson's curriculum focus (indicator, content
  standard, sub-strand, exemplar focus terms and the lesson's own prose);
* subject terms are preferred and multi-word terms stay whole
  ("place value", "significant figures", "equivalent fractions");
* teaching materials stay resources unless the term itself is the learning
  target;
* malformed fragments ("paper-", "numbe-") are rejected;
* generic function words are rejected by default, but a word that the lesson
  explicitly teaches ("difference" in subtraction, the conjunction "or", the
  verb "is") is kept because the teaching objective makes it vocabulary.

This is deliberately NOT a universal stop-word filter: every exclusion is
checked against the source text and the subject. The function never invents a
term that is absent from the lesson's sources.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

__all__ = [
    "suggest_vocabulary",
    "filter_supported_terms",
    "is_malformed_fragment",
    "filter_relevant_resources",
    "normalize_numeric_groups",
    "validate_keywords",
]

#: Function words that are never vocabulary on their own. They are only
#: removed from CANDIDATE generation; an explicitly quoted/taught term is
#: rescued by :func:`_explicit_language_targets` before this set is applied.
_GENERIC_WORDS = frozenset("""
a an the and or but nor yet so if then than that this these those there their
them they we you your our us i he she his her him it its is are was were be been
being am do does did done doing have has had having can could may might must
shall should will would of to in on at by for with from into onto over under
about above below between among through during before after again further once
here when where why how all any both each few more most other some such no not
only own same very just also too as up down out off again once
learners learner teacher teachers students pupils lesson lessons class
activity activities exercise exercises book books page pages work works
write writes writing written read reads reading say says said tell tells
use uses used using make makes made model models modelling modeling
understand understands understanding knowledge skill skills idea ideas
number numbers quantity quantities thing things way ways part parts
example examples sample samples question questions answer answers
first second third next last also well correctly accurately clearly
new words word vocabulary keyword keywords term terms meaning
""".split())

#: Words that describe an action rather than the subject content. They are
#: rejected as standalone keywords but allowed inside a real phrase.
_ACTION_WORDS = frozenset("""
identify recognise recognize describe explain discuss define state name label
list match sort group compare contrast classify categorise categorize
demonstrate show perform practise practice apply use calculate compute solve
find determine measure record draw construct build create design produce plan
compose formulate generate develop prepare observe investigate examine analyse
analyze interpret summarise summarize paraphrase illustrate exemplify clarify
evaluate assess judge justify critique review argue defend recommend decide
select choose rate convert simplify round add subtract multiply divide
distinguish differentiate discriminate between
read write speak listen pronounce recite respond ask participate
trace count copy retell sing dance play skip hop jump throw catch kick bounce
wash clean brush plant water collect gather visit
""".split())

#: Material words. A candidate containing one of these is a resource, not
#: vocabulary, unless the exact phrase is present in the subject glossary
#: (e.g. "base ten blocks" can be a learning target in a place-value lesson).
_MATERIAL_WORDS = frozenset("""
paper papers sheet sheets card cards chart charts chalkboard chalk marker
markers projector projector's computer computers laptop laptops tablet tablets
phone phones printer mouse keyboard monitor currency cedi cedis money coin
coins note notes exercise book books notebook notebooks pen pens pencil pencils
crayon crayons ruler rulers scissors glue tape glue stick sticks block blocks
counter counters bead beads bottle bottles cap caps stone stones leaf leaves
seed seeds plant plants specimen specimens material materials resource
resources apparatus equipment tool tools graph graphs isometric multi-base
multibase rectangular
""".split())

#: Subject glossaries. Longest phrases are matched first so "place value"
#: survives as a phrase and "value" alone is never emitted.
_SUBJECT_GLOSSARY: dict[str, tuple[str, ...]] = {
    "mathematics": (
        "place value", "whole number", "whole numbers", "natural number",
        "natural numbers", "counting number", "counting numbers",
        "base ten", "base ten numeral", "base ten numerals", "numeral",
        "numerals", "digit", "digits", "greater than", "less than",
        "equal to", "not equal to", "difference", "sum", "product",
        "quotient", "remainder", "factor", "factors", "multiple",
        "multiples", "prime number", "composite number", "numerator",
        "denominator", "equivalent fraction", "equivalent fractions",
        "improper fraction", "mixed number", "common denominator",
        "decimal", "decimals", "decimal place", "decimal places",
        "decimal point", "significant figure", "significant figures",
        "rounding", "round off", "power of ten", "powers of ten",
        "standard form", "expanded form", "word form",
        "number name", "number names", "counting sequence",
        "counting sequences", "benchmark fraction",
        "benchmark fractions", "number line", "number lines", "ratio",
        "proportion", "percentage", "percent", "average", "mean", "median",
        "mode", "range", "probability", "angle", "angles", "triangle",
        "quadrilateral", "perimeter", "area", "volume", "capacity",
        "mass", "length", "symmetry", "line of symmetry", "coordinate",
        "coordinates", "equation", "expression", "variable", "constant",
        "integer", "integers", "sequence", "pattern", "patterns",
        "operation", "operations", "addition", "subtraction",
        "multiplication", "division", "fraction", "fractions",
    ),
    "computing": (
        "computer system", "computer systems", "hardware", "software",
        "peopleware", "input device", "input devices", "output device",
        "output devices", "processing device", "storage device",
        "storage devices", "manual device", "manual devices",
        "automatic device", "automatic devices", "device", "devices",
        "manual", "automatic", "central processing unit", "memory",
        "random access memory", "read only memory", "operating system",
        "application software", "system software", "file", "folder",
        "file path", "folder path", "extension", "file extension",
        "file extensions", "file type", "naming convention", "subfolder",
        "filename", "algorithm",
        "program", "programme", "programming", "code", "coding",
        "debugging", "loop", "condition", "variable", "function",
        "database", "record", "field", "spreadsheet", "cell", "formula",
        "network", "internet", "browser", "website", "web page",
        "email", "password", "username", "account", "permission",
        "cyber safety", "digital footprint", "malware", "virus",
        "artificial intelligence", "machine learning", "data",
        "information", "binary", "bit", "byte", "pixel", "resolution",
    ),
    "science": (
        "living thing", "living things", "non-living thing",
        "non-living things", "life process", "life processes",
        "cell", "cells", "tissue", "organ", "organ system", "organism",
        "organisms", "micro-organism", "micro-organisms", "microorganism",
        "microorganisms",
        "photosynthesis", "respiration", "digestion", "excretion",
        "reproduction", "growth", "movement", "sensitivity", "nutrition",
        "vertebrate", "invertebrate", "mammal", "bird", "reptile",
        "amphibian", "fish", "insect", "plant", "flower", "root", "stem",
        "leaf", "seed", "germination", "pollination", "habitat",
        "ecosystem", "food chain", "food web", "producer", "consumer",
        "decomposer", "adaptation", "matter", "solid", "liquid", "gas",
        "mixture", "solution", "solute", "solvent", "filtering",
        "evaporation", "condensation", "melting", "freezing", "energy",
        "force", "motion", "friction", "gravity", "magnetism", "light",
        "sound", "heat", "temperature", "electricity", "circuit",
        "kinetic energy", "potential energy", "thermal energy",
        "chemical energy", "electrical energy", "sound energy",
        "light energy", "energy transfer", "energy transformation",
        "conductor", "insulator", "weather", "climate", "soil", "rock",
        "mineral", "water cycle", "air", "pollution", "conservation",
    ),
    "english": (
        "noun", "nouns", "pronoun", "pronouns", "verb", "verbs",
        "adjective", "adjectives", "adverb", "adverbs", "preposition",
        "prepositions", "conjunction", "conjunctions", "interjection",
        "article", "articles", "subject", "predicate", "object",
        "sentence", "sentences", "paragraph", "paragraphs", "punctuation",
        "full stop", "question mark", "exclamation mark", "comma",
        "apostrophe", "quotation mark", "capital letter", "capital letters",
        "spelling", "vocabulary", "synonym", "antonym", "homophone",
        "prefix", "suffix", "root word", "tense", "present tense",
        "past tense", "future tense", "singular", "plural", "concord",
        "comprehension", "summary", "main idea", "supporting detail",
        "narrative", "description", "dialogue", "letter", "formal letter",
        "informal letter", "report", "instruction", "poem", "story",
        "character", "setting", "plot", "theme", "figure of speech",
        "simile", "metaphor", "personification", "alliteration",
    ),
    "social studies": (
        "community", "family", "culture", "tradition", "custom",
        "citizenship", "citizen", "rights", "responsibilities", "duty",
        "democracy", "governance", "government", "constitution", "law",
        "justice", "authority", "leadership", "chief", "assembly",
        "map", "scale", "compass", "direction", "latitude", "longitude",
        "region", "district", "settlement", "population", "migration",
        "economy", "trade", "barter", "market", "industry",
        "agriculture", "mining", "tourism", "transport", "communication",
        "environment", "natural resource", "natural resources",
        "sustainability", "heritage", "independence", "colonialism",
    ),
    "creative arts": (
        "line", "lines", "shape", "shapes", "form", "colour", "colour",
        "texture", "pattern", "rhythm", "balance", "contrast", "emphasis",
        "composition", "design", "drawing", "painting", "printmaking",
        "sculpture", "modelling", "collage", "craft", "weaving",
        "pottery", "music", "beat", "pitch", "melody", "harmony",
        "instrument", "dance", "drama", "role play", "improvisation",
        "performance", "audience", "rehearsal",
    ),
    "rme": (
        "worship", "prayer", "faith", "belief", "scripture", "bible",
        "quran", "prophet", "disciple", "commandment", "covenant",
        "creation", "stewardship", "compassion", "forgiveness",
        "reconciliation", "justice", "mercy", "service", "community",
        "family life", "marriage", "tolerance", "religious tolerance",
        "moral", "values", "virtue", "responsibility",
    ),
    "phe": (
        "fitness", "health", "wellbeing", "exercise", "warm up",
        "cool down", "endurance", "strength", "flexibility", "balance",
        "coordination", "agility", "speed", "teamwork", "fair play",
        "sportsmanship", "nutrition", "hygiene", "safety", "injury",
        "first aid", "athletics", "gymnastics", "football", "volleyball",
        "basketball", "handball", "running", "jumping", "throwing",
    ),
    "career technology": (
        "tool", "tools", "material", "materials", "measurement",
        "marking out", "cutting", "shaping", "joining", "finishing",
        "safety", "workshop", "project", "design brief", "specification",
        "prototype", "product", "service", "entrepreneurship", "business",
        "customer", "market research", "costing", "budget", "quality",
    ),
}

_SUBJECT_ALIASES = {
    "ict": "computing",
    "information and communication technology": "computing",
    "computing": "computing",
    "mathematics": "mathematics",
    "maths": "mathematics",
    "math": "mathematics",
    "integrated science": "science",
    "science": "science",
    "english language": "english",
    "english": "english",
    "ghanaian language": "english",
    "social studies": "social studies",
    "creative arts": "creative arts",
    "religious and moral education": "rme",
    "rme": "rme",
    "physical education": "phe",
    "physical education and health": "phe",
    "phe": "phe",
    "career technology": "career technology",
    "technical drawing": "career technology",
}

#: Phrases that name a learning target even though they contain a material
#: word (place-value apparatus is itself the concept being taught).
_GLOSSARY_MATERIAL_EXCEPTIONS = frozenset({
    "base ten", "base ten numeral", "base ten numerals",
    "number line", "number lines", "place value",
})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def is_malformed_fragment(text: str) -> bool:
    """True for a broken label such as ``paper-`` or ``numbe-``.

    A real hyphenated word contains letters after the hyphen ("paper-based").
    A trailing hyphen, a lone letter run of two characters or a token that is
    only punctuation is never a complete teaching resource or keyword.
    """
    value = (text or "").strip()
    if not value:
        return True
    if value.endswith(("-", "\u2013", "\u2014", "/", "\\")):
        return True
    if re.fullmatch(r"[\W_]+", value):
        return True
    letters = re.sub(r"[^A-Za-z]", "", value)
    return len(letters) < 2


def normalize_numeric_groups(text: str) -> str:
    """Join thousand-separated digit groups so Word cannot split them.

    ``1 000 000 000`` (the Ghanaian scheme convention) and the same value with
    non-breaking spaces or line breaks become ``1,000,000,000``. Ordinary
    numbers ("10", "2026") are untouched.
    """
    if not text:
        return text
    pattern = re.compile(r"(?<!\d)(\d{1,3})((?:[ \u00a0\r\n]+\d{3})+)(?!\d)")

    def _join(match: re.Match) -> str:
        groups = re.split(r"[ \u00a0\r\n]+", match.group(2).strip())
        return ",".join([match.group(1), *groups])

    return pattern.sub(_join, text)


def _subject_key(subject: str) -> str:
    value = (subject or "").strip().lower()
    for alias, key in sorted(_SUBJECT_ALIASES.items(), key=lambda i: -len(i[0])):
        if value == alias or alias in value:
            return key
    return ""


def _resource_keys(resources: Iterable[str]) -> set[str]:
    keys: set[str] = set()
    for resource in resources or ():
        value = (resource or "").strip().lower()
        if not value:
            continue
        keys.add(value)
        keys.update(w for w in _WORD_RE.findall(value) if len(w) > 2)
    return keys


def _explicit_language_targets(text: str) -> List[str]:
    """Words the lesson explicitly names as language targets.

    Covers ``the conjunction "or"``, ``the word 'difference'``, ``verb "is"``
    and quoted terms. This is why ``or``/``is`` can be valid vocabulary in a
    language lesson while remaining generic elsewhere.
    """
    found: List[str] = []
    for match in re.finditer(
            r"(?:word|term|conjunction|verb|preposition|article|spelling|"
            r"meaning of)\s+[\"'“”‘’]([A-Za-z][A-Za-z'\- ]{0,40})[\"'“”‘’]",
            text or "", re.IGNORECASE):
        value = match.group(1).strip()
        if value:
            found.append(value)
    # Curly/straight single quotation marks are also used around a target.
    for match in re.finditer(r"[\"“”]([A-Za-z][A-Za-z'\- ]{0,40})[\"“”]", text or ""):
        value = match.group(1).strip()
        if value:
            found.append(value)
    return found


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _phrase_is_material(phrase: str, glossary: Sequence[str]) -> bool:
    low = phrase.lower()
    if low in _GLOSSARY_MATERIAL_EXCEPTIONS:
        return False
    if any(low == term for term in glossary):
        return False
    words = set(_WORD_RE.findall(low))
    return bool(words & _MATERIAL_WORDS)


def _is_generic(candidate: str) -> bool:
    words = [w for w in _WORD_RE.findall(candidate.lower()) if w]
    if not words:
        return True
    if len(words) == 1:
        return words[0] in _GENERIC_WORDS or words[0] in _ACTION_WORDS
    # A phrase made only of generic/action words carries no vocabulary.
    return all(w in _GENERIC_WORDS or w in _ACTION_WORDS for w in words)


def _glossary_matches(text: str, glossary: Sequence[str]) -> List[str]:
    matches = [term for term in glossary if _contains_phrase(text, term)]
    # Longest first; drop a shorter term contained in a chosen longer one.
    matches.sort(key=lambda t: (-len(t), t))
    out: List[str] = []
    for term in matches:
        if any(_contains_phrase(chosen, term) for chosen in out):
            continue
        out.append(term)
    return out


def _content_candidates(text: str) -> List[str]:
    """Content-word candidates, keeping short multi-word phrases.

    This is deliberately conservative: it extracts noun-like words and
    two-word compounds, not every token. The subject glossary supplies the
    precise multi-word terminology.
    """
    cleaned = normalize_numeric_groups(text or "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    tokens = _WORD_RE.findall(cleaned)
    out: List[str] = []
    for token in tokens:
        low = token.lower().strip("'-")
        if not low or len(low) < 3:
            continue
        if low in _GENERIC_WORDS or low in _ACTION_WORDS or low in _MATERIAL_WORDS:
            continue
        if low.endswith(("ed", "ing")) and low not in {"rounding", "grouping"}:
            # Participles describe the activity ("sorting", "counting").
            continue
        # Noun-like suffixes and capitalised terms are the safest candidates.
        if (low.endswith(("tion", "sion", "ment", "ness", "ity", "ism",
                          "ics", "ology", "ure", "ance", "ence", "ship",
                          "hood", "dom", "graphy", "metry"))
                or token[:1].isupper()
                or "-" in token):
            out.append(token.strip())
    return out


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", (item or "").strip(" ,;.")).strip()
        if not value or is_malformed_fragment(value):
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _display_term(term: str) -> str:
    """Lower-case a glossary term; preserve an acronym or proper noun."""
    if term.isupper() and len(term) <= 5:
        return term
    if term[:1].isupper() and term.split(" ", 1)[0].lower() in {
            "ghana", "nacca", "god", "english", "french"}:
        return term
    return term[:1].lower() + term[1:] if term else term


def _singular_key(term: str) -> str:
    """A crude singular key for simple English plurals (never changes output)."""
    value = term.strip().lower()
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    if value.endswith("ses") and len(value) > 4:
        return value[:-2]
    if value.endswith("s") and not value.endswith(("ss", "us", "is")) and len(value) > 3:
        return value[:-1]
    return value


def _is_covered(candidate: str, chosen: List[str]) -> bool:
    low = candidate.lower()
    key = _singular_key(candidate)
    for item in chosen:
        item_low = item.lower()
        if low == item_low or key == _singular_key(item):
            return True
        if _contains_phrase(item, candidate) or _contains_phrase(candidate, item):
            return True
    return False


def suggest_vocabulary(
    *,
    indicator: str = "",
    content_standard: str = "",
    sub_strand: str = "",
    strand: str = "",
    subject: str = "",
    lesson_texts: Iterable[str] = (),
    resources: Iterable[str] = (),
    exemplar_terms: Iterable[str] = (),
    teacher_terms: Iterable[str] = (),
    limit: int = 8,
) -> List[str]:
    """Select a concise, indicator-specific keyword list.

    Returns only terms with a demonstrable connection to this lesson. An empty
    list is a valid answer: the caller must not invent vocabulary to fill the
    cell.
    """
    indicator = normalize_numeric_groups(indicator or "")
    content_standard = normalize_numeric_groups(content_standard or "")
    lesson_prose = " ".join(
        normalize_numeric_groups(str(t or "")) for t in (lesson_texts or ())
    )
    source_text = " ".join((
        indicator, content_standard, sub_strand or "", strand or "",
        lesson_prose, " ".join(str(t or "") for t in (exemplar_terms or ())),
    ))
    # Glossary matching is limited to the CURRICULUM text. Matching it against
    # the composed lesson prose picked up incidental words ("assessment mode"
    # -> the statistics term "mode").
    curriculum_text = " ".join((
        indicator, content_standard, sub_strand or "", strand or "",
        " ".join(str(t or "") for t in (exemplar_terms or ())),
    ))
    if not source_text.strip():
        return _dedupe(teacher_terms)[:limit]

    subject_key = _subject_key(subject)
    glossary = _SUBJECT_GLOSSARY.get(subject_key, ())
    resource_words = _resource_keys(resources)

    candidates: List[str] = []
    # 1. Explicit language targets are authoritative even when short.
    explicit = _explicit_language_targets(source_text)
    explicit_lows = {value.lower() for value in explicit}
    candidates.extend(explicit)
    # 2. Subject terminology present in the lesson's curriculum text.
    candidates.extend(_display_term(t) for t in _glossary_matches(curriculum_text, glossary))
    # 3. Exemplar focus terms (official NaCCA wording).
    candidates.extend(str(t or "").strip() for t in (exemplar_terms or ()))
    # 4. Noun-like words actually present, as a last indicator-specific layer.
    candidates.extend(_display_term(t) for t in _content_candidates(indicator))
    candidates.extend(_display_term(t) for t in _content_candidates(content_standard))
    # Teacher suggestions are handled separately below and always survive.

    out: List[str] = []
    for candidate in _dedupe(candidates):
        low = candidate.lower()
        is_explicit = low in explicit_lows
        if not is_explicit and low in _GENERIC_WORDS:
            continue
        if not is_explicit and _is_generic(candidate):
            continue
        if not is_explicit and _phrase_is_material(candidate, glossary):
            continue
        if low in resource_words and not is_explicit:
            continue
        # A resource name is not vocabulary unless the lesson names it as the
        # learning target (the explicit-language path above).
        if any(low == r or low in r.split() for r in resource_words) and not is_explicit:
            # Only reject whole-resource words; "number" in "number cards"
            # remains a legitimate curriculum term.
            if low in _MATERIAL_WORDS:
                continue
        if candidate not in out:
            if _is_covered(candidate, out):
                continue
            out.append(candidate)
        if len(out) >= limit:
            break
    # Teacher-approved terms always survive, in the teacher's own wording.
    teacher_clean = [term for term in _dedupe(teacher_terms)
                     if not is_malformed_fragment(term)]
    if teacher_clean:
        merged: List[str] = []
        for term in teacher_clean + out:
            if term.lower() not in {x.lower() for x in merged}:
                merged.append(term)
            if len(merged) >= max(limit, len(teacher_clean)):
                break
        return merged
    return out


_GENERIC_CLASSROOM_RESOURCES = frozenset({
    "exercise book", "exercise books", "chalkboard", "marker", "markers",
    "pen", "pens", "pencil", "pencils", "ruler", "rulers", "chart",
    "charts", "wall chart", "wall charts", "pictures", "picture cards",
    "flash cards", "flashcards", "word cards", "letter cards", "sound cards",
    "number cards", "number chart", "real objects", "real object",
    "counter", "counters", "straws", "bundle and loose straws", "sticks",
    "lollipop sticks", "bottle tops", "abacus", "beads", "video clip",
    "video clips",
})


def _is_generic_classroom_resource(value: str) -> bool:
    return value.strip().lower() in _GENERIC_CLASSROOM_RESOURCES


def filter_relevant_resources(
    resources: Iterable[str],
    *,
    indicator: str = "",
    content_standard: str = "",
    lesson_texts: Iterable[str] = (),
    subject: str = "",
) -> List[str]:
    """Keep only source resources that this lesson actually names or uses.

    A resource is relevant when one of its significant words appears in the
    indicator, content standard or the composed lesson prose. Malformed
    entries are dropped rather than guessed. The result may be empty.

    Computing/ICT keeps the scheme's own devices: the apparatus IS the subject
    matter (a lesson on computer components may legitimately use a printer or
    mouse even when the indicator names only "components"). Universal classroom
    basics stay available for every subject.
    """
    subject_key = _subject_key(subject)
    glossary_text = " ".join(_SUBJECT_GLOSSARY.get(subject_key, ()))
    haystack = " ".join((
        normalize_numeric_groups(indicator or ""),
        normalize_numeric_groups(content_standard or ""),
        " ".join(normalize_numeric_groups(str(t or "")) for t in (lesson_texts or ())),
        glossary_text,
    )).lower()
    haystack_words = set(_WORD_RE.findall(haystack))
    out: List[str] = []
    for resource in resources or ():
        value = (resource or "").strip()
        if not value or is_malformed_fragment(value):
            continue
        if subject_key == "computing":
            if value not in out:
                out.append(value)
            continue
        low = value.lower()
        if _is_generic_classroom_resource(low):
            if value not in out:
                out.append(value)
            continue
        if not haystack.strip():
            continue
        if low in haystack:
            if value not in out:
                out.append(value)
            continue
        words = [w for w in _WORD_RE.findall(low) if len(w) > 2 and w not in _GENERIC_WORDS]
        if words and any(word in haystack_words for word in words):
            if value not in out:
                out.append(value)
    return out


def filter_supported_terms(
    terms: Iterable[str],
    *,
    indicator: str = "",
    content_standard: str = "",
    lesson_texts: Iterable[str] = (),
    subject: str = "",
    resources: Iterable[str] = (),
) -> List[str]:
    """Keep only proposed terms that the lesson's sources actually support.

    Used for provider/AI vocabulary: a model may suggest a good synonym, but
    it may not add a term with no connection to the indicator, content
    standard, lesson prose or the subject glossary.
    """
    source = " ".join((
        normalize_numeric_groups(indicator or ""),
        normalize_numeric_groups(content_standard or ""),
        " ".join(normalize_numeric_groups(str(t or "")) for t in (lesson_texts or ())),
    )).lower()
    glossary = " ".join(_SUBJECT_GLOSSARY.get(_subject_key(subject), ())).lower()
    resource_keys = _resource_keys(resources)
    out: List[str] = []
    for raw in terms or ():
        value = re.sub(r"\s+", " ", str(raw or "").strip(" ,;."))
        if not value or is_malformed_fragment(value):
            continue
        low = value.lower()
        if low in resource_keys or low in _MATERIAL_WORDS:
            continue
        if low in _GENERIC_WORDS or _is_generic(value):
            continue
        if _contains_phrase(source, value) or _contains_phrase(glossary, value):
            if low not in {x.lower() for x in out}:
                out.append(value)
    return out


def validate_keywords(
    keywords: Iterable[str],
    *,
    resources: Iterable[str] = (),
    indicator: str = "",
    content_standard: str = "",
    subject: str = "",
) -> List[str]:
    """Return the reasons a keyword list violates the vocabulary contract.

    Used by tests and by the generation quality gate. An empty list means the
    keywords pass.
    """
    problems: List[str] = []
    resource_keys = _resource_keys(resources)
    source = f"{indicator} {content_standard}".lower()
    seen: set[str] = set()
    for raw in keywords or ():
        value = (raw or "").strip()
        if not value:
            problems.append("empty_keyword")
            continue
        low = value.lower()
        if low in seen:
            problems.append(f"duplicate_keyword:{value}")
            continue
        seen.add(low)
        if is_malformed_fragment(value):
            problems.append(f"truncated_keyword:{value}")
            continue
        if low in resource_keys:
            problems.append(f"resource_keyword:{value}")
        if low in _GENERIC_WORDS and low not in source:
            problems.append(f"generic_keyword:{value}")
        if low in _MATERIAL_WORDS:
            problems.append(f"material_keyword:{value}")
        # A term absent from the lesson sources would be invented.
        if source.strip() and low not in source and not _contains_phrase(
                " ".join(_SUBJECT_GLOSSARY.get(_subject_key(subject), ())), low):
            # Teacher-supplied terms may be absent from the indicator; the
            # caller is responsible for that path, so do not flag here.
            pass
    return problems

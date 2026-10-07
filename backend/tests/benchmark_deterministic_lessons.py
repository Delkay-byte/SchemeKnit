"""Priority 2 — Deterministic lesson-authoring benchmark (BEFORE/AFTER).

Runs the REAL deterministic generation path (GenerationPipeline, AI OFF, Zeli
OFF) over a fixed corpus of real SchemeKnit curriculum occurrences spanning
Mathematics, Science, English, Computing, Creative Arts and Social Studies,
then scores every lesson on the fixed 15-criterion rubric (1-5, max 75) plus
the hard-failure list from the Priority 2 spec.

Usage (from backend/):
    ./venv/Scripts/python tests/benchmark_deterministic_lessons.py --out ../docs/benchmark/before.json

A lesson counts as TEACHER-READY only when it has no hard failures, exact
timing, an indicator-specific objective, three concrete phases, an aligned
assessment and usable resources. Scores are deterministic heuristics over the
stored lesson text — no AI is involved at any point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import (  # noqa: E402
    AIMode,
    ClassLevel,
    SchemeOfWork,
    Subject,
    TermConfig,
    Week,
    WeekType,
)

# ── Benchmark corpus ────────────────────────────────────────────────────────
#
# Every entry is a REAL existing SchemeKnit curriculum occurrence: indicator
# texts are either verbatim NaCCA indicators already used as fixtures in this
# repository, or the official-corpus learning focus of a registered exemplar
# record (src/curriculum/exemplars). Provenance is recorded per entry.

BASIC7 = ClassLevel.BASIC_7

CORPUS = [
    # Mathematics (incl. the required repeated indicator across weeks)
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Use place value to read and write numbers",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of place value of digits in whole numbers",
        resources=["multi-base blocks", "place value chart", "exercise books"],
        provenance="NaCCA B7 indicator used in tests/test_curriculum_v2.py; exemplar record B7.1.1.1.1",
    ),
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=2,
        code="B7.1.1.1.1",
        indicator="Use place value to read and write numbers",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of place value of digits in whole numbers",
        resources=["multi-base blocks", "place value chart", "exercise books"],
        provenance="REPEAT of week 1 occurrence (progression probe)",
    ),
    dict(
        subject=Subject.MATHEMATICS, class_level=BASIC7, week=3,
        code="B7.1.1.1.3",
        indicator="Solve word problems involving addition and subtraction",
        strand="Number", sub_strand="Number and Numeration Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Apply number operations to solve everyday problems",
        resources=["exercise books", "chalkboard", "word problem cards"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py MATH_CODES)",
    ),
    # Science
    dict(
        subject=Subject.SCIENCE, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Classify materials as solids, liquids and gases",
        strand="Matter", sub_strand="Classification of Materials",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of the states of matter",
        resources=["local samples (water, sand, stone)", "containers", "recording sheets"],
        provenance="Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/science.py)",
    ),
    dict(
        subject=Subject.SCIENCE, class_level=BASIC7, week=2,
        code="B7.2.1.1.1",
        indicator="Describe the characteristics of living things",
        strand="Diversity of Life", sub_strand="Living Things",
        content_standard_code="B7.2.1.1",
        content_standard="Demonstrate understanding of characteristics of living things",
        resources=["leaf samples", "chalkboard", "exercise books"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py SCI_CODES)",
    ),
    # English Language
    dict(
        subject=Subject.ENGLISH, class_level=BASIC7, week=1,
        code="B7.1.1.1.1",
        indicator="Use formal and informal register in conversation",
        strand="Communication", sub_strand="Speaking and Listening",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate the ability to communicate appropriately in different situations",
        resources=["conversation cards", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1.1.1.1.1 (src/curriculum/exemplars/english.py)",
    ),
    dict(
        subject=Subject.ENGLISH, class_level=BASIC7, week=2,
        code="B7.1.1.1.2",
        indicator="Ask questions to elicit elaboration in conversation",
        strand="Communication", sub_strand="Speaking and Listening",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate the ability to communicate appropriately in different situations",
        resources=["question cards", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1.1.1.1.2 (src/curriculum/exemplars/english.py)",
    ),
    # Computing
    dict(
        subject=Subject.ICT, class_level=BASIC7, week=1,
        code="B7.1.1.1.2",
        indicator="Distinguish between manual and automatic devices",
        strand="Introduction to Computing", sub_strand="Components of Computers and Computer Systems",
        content_standard_code="B7.1.1.1",
        content_standard="Demonstrate understanding of computer systems and their components",
        resources=["sample input devices (keyboard, mouse, scanner)", "chart", "exercise books"],
        provenance="Fixture occurrence (tests/test_lesson_quality_remediation.py) + exemplar record B7.1.1.1.2",
    ),
    dict(
        subject=Subject.ICT, class_level=BASIC7, week=2,
        code="B7.1.1.2.1",
        indicator="Demonstrate how to use the Start screen, tiles and taskbar",
        strand="Introduction to Computing", sub_strand="Windows and the Desktop",
        content_standard_code="B7.1.1.2",
        content_standard="Demonstrate understanding of the operating system and its interface",
        resources=["computer or projected screen where available", "unplugged keyboard diagram", "exercise books"],
        provenance="Derived from exemplar record B7.1.1.2.1 learning focus + curriculum action verbs",
    ),
    # Creative Arts & Design
    dict(
        subject=Subject.CREATIVE_ARTS, class_level=BASIC7, week=1,
        code="B7.5.1.1.1",
        indicator="Create a simple pattern using local materials",
        strand="Design", sub_strand="Pattern and Decoration",
        content_standard_code="B7.5.1.1",
        content_standard="Demonstrate ability to create designs and works using local materials",
        resources=["local materials (seeds, leaves, cloth scraps)", "manila paper", "glue"],
        provenance="SchemeKnit fixture occurrence (tests/test_generation_quality_v3.py CRE_CODES)",
    ),
    # Social Studies
    dict(
        subject=Subject.SOCIAL_STUDIES, class_level=BASIC7, week=1,
        code="B7.1.1.2.1",
        indicator="Explain sources of energy in Ghana and ways of conserving energy",
        strand="Our Environment", sub_strand="Energy Resources",
        content_standard_code="B7.1.1.2",
        content_standard="Demonstrate understanding of energy resources and their conservation",
        resources=["chart of local energy sources", "chalkboard", "exercise books"],
        provenance="Exemplar record B7/JHS1 1.1.2.1 (src/curriculum/exemplars/social_studies.py)",
    ),
]

SUBJECT_STRAND_KEY = {
    Subject.MATHEMATICS: "mathematics",
    Subject.SCIENCE: "science",
    Subject.ENGLISH: "english",
    Subject.ICT: "computing",
    Subject.CREATIVE_ARTS: "creative arts",
    Subject.SOCIAL_STUDIES: "social studies",
}


def build_scheme(entry_list):
    """One SchemeOfWork per subject, one Week per source occurrence."""
    weeks = []
    for entry in entry_list:
        weeks.append(Week(
            week_number=entry["week"],
            start_date=date(2026, 9, 7) + (date(2026, 9, 14) - date(2026, 9, 7)) * (entry["week"] - 1),
            end_date=date(2026, 9, 11) + (date(2026, 9, 18) - date(2026, 9, 11)) * (entry["week"] - 1),
            week_type=WeekType.INSTRUCTION,
            strand=entry["strand"], sub_strand=entry["sub_strand"],
            content_standards=[entry["content_standard"]],
            indicators=[f'{entry["code"]} {entry["indicator"]}'],
            resources=list(entry["resources"]),
            scheme_of_work_id="bench",
        ))
    first = entry_list[0]
    return SchemeOfWork(
        id="bench", filename="benchmark.docx",
        class_level=first["class_level"], subject=first["subject"],
        term="First Term", academic_year="2026/2027",
        weeks=weeks, upload_date=date(2026, 9, 1),
    )


def build_config(subject, class_level):
    return TermConfig(
        scheme_of_work_id="bench", academic_year="2026/2027", term="First Term",
        class_level=class_level, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=1, lesson_duration_minutes=60,
        teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
        school_name="Benchmark School", teacher_name="Benchmark Teacher",
    )


def run_generation():
    """Generate lessons for every corpus subject on the real pipeline.

    Returns a list of (entry, lesson) pairs in corpus order.
    """
    from src.engines.generation_pipeline import GenerationPipeline

    by_subject = {}
    for entry in CORPUS:
        by_subject.setdefault(entry["subject"], []).append(entry)

    results = []
    for subject, entries in by_subject.items():
        scheme = build_scheme(entries)
        config = build_config(subject, entries[0]["class_level"])
        job = GenerationPipeline().generate_all(scheme, config)
        plans = sorted(job._lesson_plans, key=lambda lp: (lp.week_number, lp.lesson_sequence))
        assert len(plans) == len(entries), (
            f"{subject}: expected {len(entries)} lessons, got {len(plans)}")
        for entry, lp in zip(entries, plans):
            results.append((entry, lp))
    return results


# ── Text analysis helpers ─────────────────────────────────────────────────────

_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "their",
    "they", "them", "will", "can", "are", "was", "were", "has", "have",
    "had", "but", "not", "you", "your", "our", "its", "it's", "his", "her",
    "one", "two", "three", "four", "five", "each", "every", "then", "them",
    "than", "when", "what", "which", "who", "how", "why", "all", "any",
    "out", "get", "got", "set", "use", "used", "using", "also", "may",
    "can", "could", "should", "would", "about", "after", "before", "over",
    "under", "between", "more", "most", "some", "such", "only", "own",
    "same", "too", "very", "just", "like", "well", "back", "even", "still",
    "through", "during", "above", "below", "both", "few", "other", "while",
    "does", "done", "make", "makes", "made", "take", "taken", "give",
    "given", "know", "known", "see", "seen", "now", "new", "next", "last",
    "first", "second", "third", "today", "yesterday", "lesson", "lessons",
    "learners", "learner", "teacher", "class", "school", "week", "weeks",
    "learners'", "children", "pupils",
}

_MEASURABLE_VERBS = {
    "identify", "describe", "demonstrate", "compare", "classify",
    "classify", "explain", "apply", "investigate", "distinguish",
    "examine", "categorise", "categorize", "design", "state", "list",
    "model", "represent", "determine", "analyse", "analyze", "evaluate",
    "outline", "create", "perform", "measure", "calculate", "interpret",
    "justify", "name", "match", "arrange", "sort", "construct", "draw",
    "solve", "round", "express", "use", "ask", "respond", "record",
    "research", "reflect", "role play", "participate", "write", "read",
    "practise", "practice", "distinguish between", "give examples",
}

_GENERIC_OBJECTIVE_RE = re.compile(
    r"learners can (explore|understand|discuss|learn|talk about|know|be aware)\b",
    re.I,
)
_FILLER_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"discuss the topic\b",
        r"explore the topic\b",
        r"understand the topic\b",
        r"talk about the topic\b",
        r"learn about the topic\b",
        r"teacher explains further",
        r"learners practise\s*[.;]",
        r"learners share their answers\s*[.;]",
        r"using\s*;",
        r"using\s*\.",
        r"\{\s*[a-z_]+\s*\}",
        r"\bNaN\b",
        r"\bNone\b",
        r"\(\s*\)",
        r";\s*[.;]",
        r"[a-z]\s+[,;]\s*$",
        r"\s[,;]",
        r",\s*,",
    )
]
_PLACEHOLDER_REF_RE = re.compile(
    r"curriculum title for this subject|for this subject and class|\[insert|"
    r"na(n|[- ]?)cca\s*/\s*ges curriculum title|insert_",
    re.I,
)
_IMPOSSIBLE_RESOURCES = [
    "projector", "internet", "smartboard", "smart board", "interactive board",
    "laptop", "tablet", "computer lab", "laboratory equipment",
]
_COMMON_RESOURCES = [
    "chalkboard", "board", "exercise book", "chart", "paper", "pencil",
    "ruler", "textbook", "book", "card", "picture", "manila", "dictionary",
    "counter", "string", "box", "bottle", "cloth", "leaflet", "globus",
    "globe", "map", "specimen", "sample", "container", "chalk", "marker",
    "drawing", "paint", "brush", "needle", "thread", "scissors", "glue",
    "stick", "stone", "leaf", "seed", "stickers", "chart paper",
]
_GROUPING_RE = re.compile(r"\b(in (pairs|groups)|pairs|groups|group of|whole class|each learner|individually)\b", re.I)
_QUANTITY_RE = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b", re.I)
_PRODUCT_RE = re.compile(
    r"\b(record|write|sort|sketch|draw|list|table|chart|solve|answer|"
    r"present|label|complete|complete|construct|design|create|justify|"
    r"classify|match|choose|select|circle|note|jot|prepare|perform)\b", re.I)
_TEACHER_VERBS = re.compile(
    r"\b(teacher|models?|demonstrates?|asks?|shows?|poses?|circulates?|checks?|"
    r"corrects?|observes?|explains?|elicits?|guides?|prompts?|gives?|sets?|"
    r"plays?|reads?|writes?|presents?|reviews?|lead|invites?|introduces?)\b", re.I)
_MONITOR_RE = re.compile(r"\b(check|check[s]? that|listen|observe|note|look for|feedback|correct|mark|record which|eye|circulate)\b", re.I)
_EVIDENCE_RE = re.compile(
    r"\b(success|evidence|check that|check[s]?|observe|mark|rubric|"
    r"look for|correct|accurate|accuracy|at least|out of|\d\s*/\s*\d)\b", re.I)
_CLOSURE_RE = re.compile(
    r"\b(exit question|summaris|summariz|recap|report|one sentence|"
    r"in their own words|reflect|conclude|conclusion|preview|what they learned|"
    r"what you learned|state the rule|explain to|teach)\b", re.I)
_STARTER_ACTION_RE = re.compile(
    r"\b(ask|show|model|pose|play|write|present|demonstrate|read|give|tell|"
    r"quick|invite|lead|start|begin|review|retrieve|recall|predict|pose)\b", re.I)

_SUBJECT_MARKERS = {
    "mathematics": re.compile(r"\b(example|method|working|problem|solve|solving|calculate|calculation|sum|product|quotient|place value|number line|sum)\b", re.I),
    "science": re.compile(r"\b(observe|observation|predict|evidence|investigat|experiment|demonstrat|result|hypothesis|measure|specimen)\b", re.I),
    "english": re.compile(r"\b(model|sentence|read|reading|write|writing|communicat|role|language|express|pronoun|adjective|verb|paragraph|sound|word)\b", re.I),
    "computing": re.compile(r"\b(device|screen|keyboard|mouse|software|hardware|file|folder|windows|start screen|tile|taskbar|input|output|troubleshoot|icon|menu)\b", re.I),
    "creative arts": re.compile(r"\b(design|create|make|drawing|draw|pattern|material|sketch|art|colour|shape|craft|perform|sing|dance|compose)\b", re.I),
    "social studies": re.compile(r"\b(community|ghana|family|society|societal|citizen|role|culture|government|resource|conserv|energy|tradition)\b", re.I),
    "rme": re.compile(r"\b(value|behaviour|behavior|role play|god|prayer|respect|honest|faith|religion|moral)\b", re.I),
}

_GHANA_CONTEXT_RE = re.compile(
    r"\b(ghana|ghanaian|market|community|local|neighbour|neighbor|village|"
    r"home|town|cedi|trotro|kente|adinkra|mosque|church|compound|household|"
    r"farm|our own|nearby|household|region|district)\b", re.I)


def content_words(text):
    words = re.findall(r"[A-Za-z][A-Za-z\-']+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in _STOPWORDS]


def overlap_recall(source, target):
    """Fraction of source content words present in target."""
    src = set(content_words(source))
    if not src:
        return 0.0
    tgt = set(content_words(target))
    return len(src & tgt) / len(src)


def distinct_markers(pattern, text):
    return len(set(m.group(0).lower() for m in pattern.finditer(text or "")))


def first_indicator_verb(indicator):
    """The first measurable action verb of the indicator text."""
    # Strip a leading GES code only ("B7.1.1.1.1 ", "7.1.2 ") — never the
    # opening words of the sentence itself ("Demonstrate how to use the
    # Start screen …" must still start with its own verb).
    text = re.sub(r"^\s*[A-Za-z]{0,3}\d[\d.]*\s+", "", indicator or "").lower()
    words = re.findall(r"[a-z]+", text)
    for i, word in enumerate(words):
        for verb in _MEASURABLE_VERBS:
            parts = verb.split()
            if word == parts[0] and words[i:i + len(parts)] == parts:
                return verb
        if word.endswith("ate") or word.endswith("ise") or word.endswith("ize"):
            if word in _MEASURABLE_VERBS:
                return word
    return ""


def verb_stem_matches(verb, text):
    """True when the indicator's verb (or a close form) appears in text."""
    if not verb:
        return False
    text_l = (text or "").lower()
    stem = verb.split()[0]
    for suffix in ("ing", "ed", "es", "s", "ation", "ations"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if len(stem) < 4:
        stem = verb.split()[0]
    return stem in text_l


def phase_rows(lp):
    """(phase1_rows, phase2_rows, phase3_rows) split from stored activity rows."""
    p1, p2, p3 = [], [], []
    for act in lp.main_activities:
        label = (act.phase or "").upper()
        if "STARTER" in label or "PHASE 1" in label:
            p1.append(act)
        elif "PLENARY" in label or "PHASE 3" in label or "REFLECTION" in label or "CLOSING" in label:
            p3.append(act)
        else:
            p2.append(act)
    return p1, p2, p3


def lesson_body(lp):
    """The lesson text a teacher actually reads (what every renderer prints).

    ONE sentence, ONE place: the stored PHASE 1 / PHASE 3 boundary rows restate
    the starter and the conclusion so the timeline's minutes sum exactly to the
    lesson duration (Priority 2 §10), and each renderer prints those rows only
    in their own phase next to the prose fields that carry them. Rows that are
    verbatim mirrors of introduction/starter/conclusion are therefore skipped —
    a sentence genuinely repeated across fields still counts as repetition.
    """
    def norm(text):
        return re.sub(r"\s+", " ", (text or "")).strip().lower()

    canonical = {norm(v) for v in (lp.introduction, lp.starter_activity,
                                   lp.conclusion) if (v or "").strip()}

    def rows(items):
        kept = []
        for act in items or []:
            description = act.description or ""
            if description.strip() and norm(description) not in canonical:
                kept.append(description)
        return " ".join(kept)

    parts = [
        lp.learning_objectives[0].description if lp.learning_objectives else "",
        lp.lesson_topic or "", lp.introduction or "", lp.starter_activity or "",
        rows(lp.main_activities),
        rows(lp.learner_activities),
        rows(lp.teacher_activities),
        lp.assessment or "", lp.class_assignment or "", lp.home_assignment or "",
        lp.conclusion or "", " ".join(lp.teaching_learning_resources or []),
    ]
    return " ".join(p for p in parts if p)


# ── The 15-criterion rubric (1-5 each, max 75) ───────────────────────────────


def c01_indicator_fidelity(entry, lp):
    body = lesson_body(lp)
    recall = overlap_recall(entry["indicator"], body)
    stored_ok = any(
        entry["indicator"].lower() in (ind or "").lower()
        for ind in (lp.indicators or []))
    if not stored_ok:
        return 1
    if recall >= 0.70:
        return 5
    if recall >= 0.55:
        return 4
    if recall >= 0.40:
        return 3
    if recall >= 0.25:
        return 2
    return 1


def c02_objective_specificity(entry, lp):
    if not lp.learning_objectives:
        return 1
    obj = lp.learning_objectives[0].description or ""
    if not obj.strip():
        return 1
    if _GENERIC_OBJECTIVE_RE.search(obj):
        return 1
    verb = first_indicator_verb(entry["indicator"])
    has_verb = verb_stem_matches(verb, obj) or any(
        v in obj.lower().split() for v in _MEASURABLE_VERBS)
    recall = overlap_recall(entry["indicator"], obj)
    if has_verb and recall >= 0.50:
        return 5
    if has_verb and recall >= 0.35:
        return 4
    if has_verb and recall >= 0.20:
        return 3
    if recall >= 0.20:
        return 2
    return 1


def c03_topic_specificity(entry, lp):
    topic = (lp.lesson_topic or "").strip()
    if not topic:
        return 1
    low = topic.lower()
    concat = f'{entry["strand"]} - {entry["sub_strand"]}'.lower()
    if low == concat:
        return 2
    if low == entry["strand"].lower() or low == entry["sub_strand"].lower():
        return 2
    if low.startswith("introduction to "):
        return 2
    recall = overlap_recall(entry["indicator"], topic)
    topic_words = content_words(topic)
    if recall >= 0.50:
        return 5
    if recall >= 0.30:
        return 4
    if len(topic_words) >= 3 and overlap_recall(entry["sub_strand"], topic) >= 0.5:
        return 3
    if len(topic_words) >= 3:
        return 3
    return 2


def c04_phase1_usefulness(entry, lp):
    p1_rows, _, _ = phase_rows(lp)
    starter = " ".join(a.description for a in p1_rows) or (lp.starter_activity or "")
    if not starter.strip():
        return 1
    if len(starter) < 50:
        return 2
    weak = re.search(r"what they (already )?know about the topic|review the previous lesson\.?\s*$",
                     starter, re.I)
    if weak:
        return 2
    has_teacher = bool(_TEACHER_VERBS.search(starter))
    has_learner = "learner" in starter.lower() or "learner" in starter.lower() or re.search(r"\bthey\b|\bpairs?\b|\bgroups?\b", starter, re.I)
    focus = overlap_recall(entry["indicator"], starter) > 0 or overlap_recall(entry["sub_strand"], starter) > 0.3
    if has_teacher and has_learner and focus:
        if _MONITOR_RE.search(starter) or _COMMON_CONNECT(starter):
            return 5
        return 4
    if (has_teacher or has_learner) and focus:
        return 3
    return 2


def _COMMON_CONNECT(text):
    """Starter links to today's indicator/next step explicitly."""
    return bool(re.search(r"today|this lesson|link to|frames? the|prepares?", text, re.I))


def c05_phase2_usefulness(entry, lp):
    _, p2, _ = phase_rows(lp)
    rows = [a for a in p2 if (a.description or "").strip()]
    if len(rows) < 2:
        return 1 if rows else 1
    long_enough = all(len(a.description or "") >= 60 for a in rows)
    marker = _SUBJECT_MARKERS.get(SUBJECT_STRAND_KEY.get(entry["subject"], ""))
    marker_hits = len(set(m.group(0).lower() for m in marker.finditer(lesson_body(lp)))) if marker else 0
    if long_enough and len(rows) >= 3 and marker_hits >= 3:
        return 5
    if long_enough and len(rows) >= 3:
        return 4
    if long_enough:
        return 3
    return 2


def c06_phase3_usefulness(entry, lp):
    _, _, p3 = phase_rows(lp)
    closing = " ".join(a.description for a in p3) or (lp.conclusion or "")
    if not closing.strip():
        return 1
    if len(closing) < 50:
        return 2
    focus = overlap_recall(entry["indicator"], closing) > 0
    if _CLOSURE_RE.search(closing) and focus and _EVIDENCE_RE.search(closing):
        return 5
    if _CLOSURE_RE.search(closing) and focus:
        return 4
    if _CLOSURE_RE.search(closing) or focus:
        return 3
    return 2


def c07_activity_specificity(entry, lp):
    _, p2, _ = phase_rows(lp)
    rows = [a for a in p2 if (a.description or "").strip()]
    if not rows:
        return 1
    scores = []
    for act in rows:
        text = act.description or ""
        hits = 0
        if _GROUPING_RE.search(text):
            hits += 1
        if _QUANTITY_RE.search(text):
            hits += 1
        if _PRODUCT_RE.search(text):
            hits += 1
        if overlap_recall(entry["indicator"], text) >= 0.2:
            hits += 1
        if _COMMON_CONNECT and re.search(r"\b(with|using|on|from|of)\b[^,.;]{3,}", text, re.I):
            hits += 1
        scores.append(hits)
    avg = sum(scores) / len(scores)
    joined = " ".join(a.description for a in rows)
    if any(p.search(joined) for p in _FILLER_PATTERNS):
        return 2
    if avg >= 3.5:
        return 5
    if avg >= 2.5:
        return 4
    if avg >= 1.5:
        return 3
    if avg >= 0.5:
        return 2
    return 1


def c08_teacher_action_clarity(entry, lp):
    rows = [a for a in lp.teacher_activities if (a.description or "").strip()]
    if not rows:
        # Fall back to the phase prose when no teacher column exists.
        rows = [a for a in lp.main_activities if (a.description or "").strip()]
    if not rows:
        return 1
    hits = 0
    total = 0
    for act in rows:
        text = act.description or ""
        total += 1
        generic = re.search(r"facilitate the activity|watch and listen carefully", text, re.I)
        if generic:
            continue
        if _TEACHER_VERBS.search(text) and overlap_recall(entry["indicator"], text) >= 0.15:
            hits += 1
            if _MONITOR_RE.search(text):
                hits += 1
    per = hits / total
    if per >= 1.5:
        return 5
    if per >= 1.0:
        return 4
    if per >= 0.5:
        return 3
    if per > 0:
        return 2
    return 1


def c09_learner_action_clarity(entry, lp):
    rows = [a for a in lp.learner_activities if (a.description or "").strip()]
    if not rows:
        return 1
    hits = 0
    total = 0
    for act in rows:
        text = act.description or ""
        total += 1
        if re.search(r"take an active part|complete the task for", text, re.I):
            continue
        concrete = _GROUPING_RE.search(text) or _QUANTITY_RE.search(text) or _PRODUCT_RE.search(text)
        if concrete and overlap_recall(entry["indicator"], text) >= 0.15:
            hits += 1
        elif _PRODUCT_RE.search(text) or _GROUPING_RE.search(text):
            hits += 0.5
    per = hits / total
    if per >= 1.0:
        return 5
    if per >= 0.75:
        return 4
    if per >= 0.5:
        return 3
    if per > 0:
        return 2
    return 1


def c10_assessment_alignment(entry, lp):
    text = lp.assessment or ""
    if not text.strip():
        return 1
    verb = first_indicator_verb(entry["indicator"])
    verb_ok = verb_stem_matches(verb, text)
    focus_hits = len(set(content_words(entry["indicator"])) & set(content_words(text)))
    evidence = bool(_EVIDENCE_RE.search(text))
    if verb_ok and focus_hits >= 1 and evidence:
        return 5
    if verb_ok and focus_hits >= 1:
        return 4
    if focus_hits >= 2 and evidence:
        return 4
    if focus_hits >= 1 and evidence:
        return 3
    if focus_hits >= 1 or evidence:
        return 2
    return 1


def c11_resource_realism(entry, lp):
    resources = [r for r in (lp.teaching_learning_resources or []) if (r or "").strip()]
    if not resources:
        return 1
    blob = " ".join(resources).lower()
    banned = [b for b in _IMPOSSIBLE_RESOURCES if b in blob]
    if banned and entry["subject"] not in (Subject.ICT,):
        return 2
    common = [c for c in _COMMON_RESOURCES if c in blob]
    activity_blob = " ".join(a.description for a in lp.main_activities).lower()
    linked = any(w in activity_blob for c in common for w in [c.split()[0]])
    scheme_link = any(
        (r or "").lower() in activity_blob for r in entry.get("resources", []))
    if common and (linked or scheme_link):
        return 5
    if common or linked or scheme_link:
        return 4
    if resources:
        return 3
    return 2


def c12_timing_integrity(entry, lp):
    rows = list(lp.main_activities)
    total = sum(int(a.duration_minutes or 0) for a in rows)
    duration = int(lp.duration_minutes or 0)
    if duration <= 0:
        return 1
    if total == duration and rows:
        return 5
    diff = abs(total - duration)
    if diff <= 3:
        return 4
    if total < duration and diff <= duration * 0.25:
        return 3
    if total < duration:
        return 2
    return 1


def c13_subject_pedagogy_fit(entry, lp):
    marker = _SUBJECT_MARKERS.get(SUBJECT_STRAND_KEY.get(entry["subject"], ""))
    if marker is None:
        return 3
    text = lesson_body(lp)
    hits = len(set(m.group(0).lower() for m in marker.finditer(text)))
    if hits >= 5:
        return 5
    if hits >= 3:
        return 4
    if hits >= 2:
        return 3
    if hits >= 1:
        return 2
    return 1


def c14_ghana_context(entry, lp):
    text = lesson_body(lp) + " " + lp.starter_activity + " " + lp.conclusion
    banned = [b for b in _IMPOSSIBLE_RESOURCES if b in text.lower()]
    hits = distinct_markers(_GHANA_CONTEXT_RE, text)
    if banned and entry["subject"] not in (Subject.ICT,):
        return 2
    if hits >= 4:
        return 5
    if hits >= 2:
        return 4
    if hits >= 1:
        return 3
    return 3


def c15_teachability(entry, lp):
    body = lesson_body(lp)
    words = len(body.split())
    score = 3
    if words >= 300:
        score += 1
    else:
        score -= 1
    if not any(p.search(body) for p in _FILLER_PATTERNS):
        score += 1
    else:
        score -= 1
    sentences = re.split(r"(?<=[.!?]) +", body)
    seen = set()
    dup = False
    for s in sentences:
        key = re.sub(r"\s+", " ", s.strip().lower())
        if len(key) > 60 and key in seen:
            dup = True
            break
        seen.add(key)
    if dup:
        score -= 2
    obj = lp.learning_objectives[0].description if lp.learning_objectives else ""
    if len(obj.split()) > 40:
        score -= 1
    return max(1, min(5, score))


RUBRIC = [
    ("indicator_fidelity", c01_indicator_fidelity),
    ("objective_specificity", c02_objective_specificity),
    ("topic_specificity", c03_topic_specificity),
    ("phase1_usefulness", c04_phase1_usefulness),
    ("phase2_usefulness", c05_phase2_usefulness),
    ("phase3_usefulness", c06_phase3_usefulness),
    ("activity_specificity", c07_activity_specificity),
    ("teacher_action_clarity", c08_teacher_action_clarity),
    ("learner_action_clarity", c09_learner_action_clarity),
    ("assessment_alignment", c10_assessment_alignment),
    ("resource_realism", c11_resource_realism),
    ("timing_integrity", c12_timing_integrity),
    ("subject_pedagogy_fit", c13_subject_pedagogy_fit),
    ("ghana_context", c14_ghana_context),
    ("teachability", c15_teachability),
]


# ── Hard failures + teacher-ready decision ───────────────────────────────────


def hard_failures(entry, lp):
    failures = []

    # wrong indicator
    stored = [(ind or "").strip().lower() for ind in (lp.indicators or [])]
    if not stored or not any(entry["indicator"].lower() in s or s in entry["indicator"].lower()
                             for s in stored):
        failures.append("wrong_indicator")

    if not (lp.content_standard or "").strip():
        failures.append("missing_content_standard")

    if not lp.learning_objectives or not (lp.learning_objectives[0].description or "").strip():
        failures.append("missing_objective")
    else:
        obj = lp.learning_objectives[0].description
        if _GENERIC_OBJECTIVE_RE.search(obj):
            failures.append("generic_objective")
        else:
            recall = overlap_recall(entry["indicator"], obj)
            has_verb = any(v in obj.lower() for v in _MEASURABLE_VERBS)
            if not has_verb or recall < 0.15:
                failures.append("generic_objective")

    _, p2, _ = phase_rows(lp)
    p2_rows = [a for a in p2 if (a.description or "").strip()]
    if not p2_rows:
        failures.append("generic_activity")
    else:
        joined = " ".join(a.description for a in p2_rows)
        if any(len((a.description or "").strip()) < 40 for a in p2_rows):
            failures.append("generic_activity")
        elif any(p.search(joined) for p in _FILLER_PATTERNS):
            failures.append("generic_activity")

    total = sum(int(a.duration_minutes or 0) for a in lp.main_activities)
    if total != int(lp.duration_minutes or 0):
        failures.append("incomplete_timing")

    full_text = lesson_body(lp)
    if any(p.search(full_text) for p in _FILLER_PATTERNS):
        failures.append("filler_text")

    refs = list(lp.references or []) + [
        (r.title or "") for r in (lp.structured_references or [])]
    if any(_PLACEHOLDER_REF_RE.search(r or "") for r in refs):
        failures.append("placeholder_reference")

    resources = [r for r in (lp.teaching_learning_resources or []) if (r or "").strip()]
    if not resources or all(len((r or "").strip()) < 3 for r in resources):
        failures.append("invalid_or_empty_resources")

    seen = set()
    for act in p2_rows:
        key = re.sub(r"\s+", " ", (act.description or "").strip().lower())
        if key and key in seen:
            failures.append("duplicate_phases")
            break
        seen.add(key)

    # WAPEF: only meaningful when the lesson uses a WAPEF template. The
    # benchmark runs the default template, so this check is N/A here.
    return failures


def teacher_ready(entry, lp, scores, failures):
    if failures:
        return False
    required = {
        "timing_integrity": 5,
        "objective_specificity": 4,
        "topic_specificity": 3,
        "phase1_usefulness": 3,
        "phase2_usefulness": 3,
        "phase3_usefulness": 3,
        "assessment_alignment": 3,
        "resource_realism": 3,
    }
    return all(scores[name] >= floor for name, floor in required.items())


def score_lesson(entry, lp):
    scores = {name: fn(entry, lp) for name, fn in RUBRIC}
    failures = hard_failures(entry, lp)
    _, p2, _ = phase_rows(lp)
    excerpt = {
        "objective": lp.learning_objectives[0].description if lp.learning_objectives else "",
        "topic": lp.lesson_topic,
        "starter": lp.starter_activity,
        "phase2": [
            {"phase": a.phase, "minutes": a.duration_minutes,
             "description": a.description}
            for a in lp.main_activities
        ],
        "learner_sample": [a.description for a in lp.learner_activities[:2]],
        "assessment": lp.assessment,
        "resources": lp.teaching_learning_resources,
        "class_assignment": lp.class_assignment,
        "home_assignment": lp.home_assignment,
        "conclusion": lp.conclusion,
        "duration_minutes": lp.duration_minutes,
        "stored_minutes_total": sum(int(a.duration_minutes or 0)
                                    for a in lp.main_activities),
    }
    return {
        "subject": entry["subject"].value if hasattr(entry["subject"], "value") else str(entry["subject"]),
        "week": entry["week"],
        "code": entry["code"],
        "indicator": entry["indicator"],
        "provenance": entry["provenance"],
        "scores": scores,
        "total": sum(scores.values()),
        "max": 75,
        "hard_failures": failures,
        "teacher_ready": teacher_ready(entry, lp, scores, failures),
        "excerpt": excerpt,
    }


def run_benchmark():
    results = []
    for entry, lp in run_generation():
        results.append(score_lesson(entry, lp))
    ready = sum(1 for r in results if r["teacher_ready"])
    summary = {
        "lessons": len(results),
        "subjects": sorted({r["subject"] for r in results}),
        "teacher_ready": ready,
        "teacher_ready_rate": round(ready / len(results), 3) if results else 0.0,
        "mean_total": round(sum(r["total"] for r in results) / len(results), 1) if results else 0,
        "mean_scores": {
            name: round(sum(r["scores"][name] for r in results) / len(results), 2)
            for name, _ in RUBRIC
        },
        "hard_failure_counts": {},
        "ai_mode": "OFF",
        "zeli": "OFF",
    }
    for r in results:
        for f in r["hard_failures"]:
            summary["hard_failure_counts"][f] = summary["hard_failure_counts"].get(f, 0) + 1
    return {"summary": summary, "lessons": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="write JSON results here")
    args = parser.parse_args(argv)

    report = run_benchmark()
    summary = report["summary"]

    print("\n== Deterministic lesson benchmark (AI OFF) ==")
    print(f'lessons: {summary["lessons"]}  subjects: {", ".join(summary["subjects"])}')
    print(f'teacher-ready: {summary["teacher_ready"]}/{summary["lessons"]} '
          f'({summary["teacher_ready_rate"] * 100:.0f}%)  mean rubric: {summary["mean_total"]}/75')
    print("\n%-28s %5s  %-4s %s" % ("indicator", "total", "ready", "failures"))
    for r in report["lessons"]:
        label = f'{r["code"]} {r["indicator"]}'[:28]
        print("%-28s %5d  %-4s %s" % (
            label, r["total"], "YES" if r["teacher_ready"] else "no",
            ", ".join(r["hard_failures"])))
    print("\nmean criterion scores:")
    for name, value in summary["mean_scores"].items():
        print(f"  {name:26s} {value}")
    if summary["hard_failure_counts"]:
        print("\nhard failures:")
        for name, count in sorted(summary["hard_failure_counts"].items()):
            print(f"  {name:26s} {count}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.out}")
    return report


if __name__ == "__main__":
    main()

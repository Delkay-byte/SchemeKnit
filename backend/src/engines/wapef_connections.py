"""
Lesson-specific WAPEF faith-integration content.

WAPEF uses four distinct Teaching for Transformation concepts. They must not be
treated as four interchangeable labels:

* **Throughline** — a character-forming discipleship habit the learner can
  practise in this lesson.
* **God's Story** — a truthful Biblical connection to the subject matter, with
  an accurate Scripture reference and a short explanation.
* **Deep Hope** — an enduring desire for the learner's formation, not a
  restatement of the lesson objective.
* **Storyline** — the learner's place in the larger narrative of God's story,
  including how the learning can serve others.

The suggestions below are deterministic and curriculum-grounded. They are
offered as defaults when the teacher has not chosen; a teacher-selected value
always wins. No Scripture text is quoted, so no verse can be misquoted: the
reference is named and its theme is summarised accurately. When the lesson has
no honest Biblical connection the generic theme still speaks about faithful
learning rather than forcing an unrelated Bible story onto the subject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from .wapef_fields import (
    WAPEF_GODS_STORY,
    WAPEF_STORYLINES,
    WAPEF_THROUGH_LINES,
    format_through_lines,
    normalize_through_lines,
)

__all__ = ["suggest_wapef_fields", "throughline_connection", "gods_story_for_label"]


#: What each approved throughline looks like in a classroom task. These are
#: practices, not definitions, so the field explains how learners can LIVE the
#: throughline in this lesson.
_THROUGHLINE_HABITS = {
    "God worshiper": "offering their work as worship",
    "Image reflector": "reflecting God's creativity and the dignity of every person",
    "Earth keeper": "caring for the created world",
    "Justice seeker": "acting fairly and defending what is right",
    "Community builder": "building others up and listening well",
    "Idolatry descerner": "testing what they value and refusing what harms",
    "Order discoverer": "looking for order and preserving it",
    "Servant worker": "working carefully for the good of others",
    "Creation enjoyer": "receiving creation with wonder",
    "Beauty creator": "making careful, beautiful work",
}

#: A truthful one-sentence narrative for each approved God's Story label,
#: used when the teacher's selected label differs from the suggested theme.
_STORY_LABELS = {
    "Creation": (
        "God created the world good, ordered and full of purpose; human "
        "beings are made in his image and entrusted with its care."
    ),
    "Fall": (
        "Humanity turned away from God, and sin brought brokenness into "
        "relationships, work and the created world."
    ),
    "Redemption": (
        "God's grace reaches into a broken world through Jesus Christ, "
        "forgiving sin and restoring people to God and one another."
    ),
    "Restoration": (
        "God promises to make all things new, and his people live and work "
        "now in the hope of that coming restoration."
    ),
}


@dataclass(frozen=True)
class _Theme:
    key: str
    keywords: Tuple[str, ...]
    subject_keys: Tuple[str, ...]
    throughline: str
    story_label: str
    story_text: str
    scripture: str
    virtue: str
    habit: str
    creation_truth: str
    invitation: str


#: A deliberately small, hand-checked set. Each Scripture reference is used for
#: the theme it actually addresses; nothing is invented and no verse is quoted.
_THEMES: Tuple[_Theme, ...] = (
    _Theme(
        key="order_pattern",
        keywords=("place value", "rounding", "round", "number", "numbers",
                  "quantity", "quantities", "sequence", "pattern", "order",
                  "decimal", "significant figure", "base ten", "numeral",
                  "symmetry", "geometry", "angle", "shape"),
        subject_keys=("mathematics",),
        throughline="Order discoverer",
        story_label="Creation",
        story_text=(
            "God created the world with order, number and pattern, and he "
            "invites people to handle that order faithfully. Psalm 147:4 "
            "describes God counting the stars and calling each one by name — "
            "a picture of careful, personal attention to number."
        ),
        scripture="Psalm 147:4",
        virtue="wonder at God's order and careful, honest work",
        habit="looking for order and preserving it in their number work",
        creation_truth="accurate number work makes truthful communication and fair dealing possible",
        invitation="use careful number work to serve their families, classrooms and communities",
    ),
    _Theme(
        key="faithful_number",
        keywords=("add", "subtract", "difference", "sum", "product",
                  "quotient", "fraction", "percentage", "money", "cost",
                  "price", "profit", "loss", "measure", "measurement",
                  "multiplication", "division", "operation", "operations"),
        subject_keys=("mathematics",),
        throughline="Servant worker",
        story_label="Redemption",
        story_text=(
            "God calls his people to be faithful in small things and honest in "
            "every transaction. Luke 16:10 connects faithfulness in little with "
            "faithfulness in much, and Proverbs 11:1 contrasts dishonest scales "
            "with accurate weights that please God."
        ),
        scripture="Luke 16:10; Proverbs 11:1",
        virtue="honesty, patience and dependable service",
        habit="checking their work carefully so others can rely on it",
        creation_truth="faithful, accurate work is a way of loving our neighbour",
        invitation="use dependable number skills to serve customers, families and the wider community",
    ),
    _Theme(
        key="data_truth",
        keywords=("data", "information", "graph", "chart", "table", "average",
                  "mean", "median", "mode", "probability", "statistics",
                  "survey", "record", "records", "spreadsheet", "database"),
        subject_keys=("mathematics", "computing"),
        throughline="Justice seeker",
        story_label="Redemption",
        story_text=(
            "God is a God of truth, and his people are called to speak and "
            "handle information truthfully. Ephesians 4:25 tells believers to "
            "put away falsehood and speak truth to their neighbour; accurate "
            "data is one practical form of that honesty."
        ),
        scripture="Ephesians 4:25",
        virtue="truthfulness and fairness in handling information",
        habit="checking evidence before making a claim",
        creation_truth="truthful information helps a community make fair decisions",
        invitation="present data honestly so that decisions at home, school and in the community are just",
    ),
    _Theme(
        key="design_parts",
        keywords=("computer", "hardware", "software", "peopleware", "device",
                  "devices", "component", "components", "part", "parts",
                  "input", "output", "processor", "memory", "storage",
                  "system", "systems", "machine", "machines"),
        subject_keys=("computing",),
        throughline="Image reflector",
        story_label="Creation",
        story_text=(
            "Human beings are made in God's image and given the capacity to "
            "design, build and care for the created world (Genesis 1:27-28). "
            "Psalm 139:14 celebrates that people are fearfully and wonderfully "
            "made — a fitting starting point for studying the parts of a system."
        ),
        scripture="Genesis 1:27-28; Psalm 139:14",
        virtue="reverence for God's design and responsible stewardship of tools",
        habit="naming and caring for each part of a system",
        creation_truth="understanding how something is designed helps us use it responsibly",
        invitation="use and maintain technology in ways that help others flourish",
    ),
    _Theme(
        key="digital_wisdom",
        keywords=("internet", "online", "email", "website", "network",
                  "password", "account", "cyber", "safety", "digital",
                  "social media", "browser", "search", "communication"),
        subject_keys=("computing",),
        throughline="Community builder",
        story_label="Fall",
        story_text=(
            "Digital tools can build community or damage it. Scripture warns "
            "that the tongue is small but powerful (James 3:5-6) and calls "
            "believers to build others up (Ephesians 4:29). Online speech and "
            "sharing are modern expressions of that same responsibility."
        ),
        scripture="James 3:5-6; Ephesians 4:29",
        virtue="wisdom, self-control and respect for others",
        habit="choosing words and online actions that build people up",
        creation_truth="technology is a gift to be used with self-control and care for others",
        invitation="use digital tools to encourage, inform and protect others rather than harm them",
    ),
    _Theme(
        key="life_systems",
        keywords=("plant", "plants", "animal", "animals", "living", "cell",
                  "cells", "organ", "organism", "habitat", "ecosystem",
                  "photosynthesis", "respiration", "reproduction",
                  "classification", "characteristic", "characteristics"),
        subject_keys=("science",),
        throughline="Creation enjoyer",
        story_label="Creation",
        story_text=(
            "God made living things with remarkable variety and order, and he "
            "delights in what he has made. Psalm 104:24 celebrates the earth "
            "being full of God's creatures and works; careful observation is a "
            "way of attending to that goodness."
        ),
        scripture="Psalm 104:24",
        virtue="reverence, curiosity and care for living things",
        habit="observing carefully before drawing conclusions",
        creation_truth="life is a gift with order, value and interdependence",
        invitation="observe and care for living things so that their community and environment can thrive",
    ),
    _Theme(
        key="earth_stewardship",
        keywords=("water", "soil", "environment", "pollution", "climate",
                  "weather", "rock", "mineral", "conservation", "waste",
                  "energy", "force", "matter", "ecosystem", "earth"),
        subject_keys=("science",),
        throughline="Earth keeper",
        story_label="Creation",
        story_text=(
            "God placed human beings in the garden to work it and keep it "
            "(Genesis 2:15). Creation is not a backdrop for human use alone; "
            "it is a trust to be cared for. Science helps us understand that "
            "trust more clearly."
        ),
        scripture="Genesis 2:15",
        virtue="stewardship, restraint and hope for the created world",
        habit="using resources carefully and repairing damage where possible",
        creation_truth="the earth belongs to God and is entrusted to human care",
        invitation="apply their learning to protect water, soil and living spaces in their community",
    ),
    _Theme(
        key="language_truth",
        keywords=("noun", "verb", "sentence", "sentences", "reading",
                  "writing", "comprehension", "story", "poem", "letter",
                  "speech", "pronunciation", "vocabulary", "language",
                  "conjunction", "punctuation", "spelling", "meaning"),
        subject_keys=("english",),
        throughline="Community builder",
        story_label="Redemption",
        story_text=(
            "God communicates with people through words and calls his people to "
            "use language truthfully and kindly. Ephesians 4:29 asks believers "
            "to speak only what builds others up, and Proverbs 18:21 describes "
            "the tongue as holding the power of life and death."
        ),
        scripture="Ephesians 4:29; Proverbs 18:21",
        virtue="truthful, kind and courageous communication",
        habit="choosing words that are clear, true and helpful",
        creation_truth="language is a gift that can heal or wound, build or divide",
        invitation="use reading, writing and speech to encourage others and tell the truth",
    ),
    _Theme(
        key="justice_community",
        keywords=("community", "citizen", "citizenship", "rights", "duty",
                  "democracy", "government", "law", "justice", "family",
                  "culture", "tradition", "migration", "population", "trade",
                  "market", "environment", "heritage"),
        subject_keys=("social studies", "rme"),
        throughline="Justice seeker",
        story_label="Redemption",
        story_text=(
            "God calls his people to act justly, love mercy and walk humbly "
            "with him (Micah 6:8). The Bible's vision of community is not "
            "merely fair rules but restored relationships in which the "
            "vulnerable are protected."
        ),
        scripture="Micah 6:8",
        virtue="justice, mercy and humble service",
        habit="listening to those affected and acting fairly",
        creation_truth="a healthy community reflects God's justice and care for the vulnerable",
        invitation="take one practical action that makes their classroom or community fairer",
    ),
    _Theme(
        key="creativity_craft",
        keywords=("design", "draw", "drawing", "paint", "painting", "colour",
                  "colour", "shape", "shapes", "craft", "sculpture", "music",
                  "rhythm", "dance", "drama", "performance", "tool", "tools",
                  "material", "materials", "construct", "build", "product"),
        subject_keys=("creative arts", "career technology"),
        throughline="Beauty creator",
        story_label="Creation",
        story_text=(
            "God is the first maker, and human creativity reflects his image. "
            "Exodus 31:1-5 describes Bezalel being filled with God's Spirit for "
            "skilful craftsmanship — a reminder that careful making is a "
            "spiritual calling, not a trivial extra."
        ),
        scripture="Exodus 31:1-5",
        virtue="patient craftsmanship and generous creativity",
        habit="planning, practising and refining their work",
        creation_truth="beauty and good craft can point people toward the goodness of the Creator",
        invitation="make and share work that serves people and adds beauty to their community",
    ),
    _Theme(
        key="worship_faith",
        keywords=("god", "worship", "prayer", "faith", "bible", "quran",
                  "prophet", "disciple", "commandment", "covenant",
                  "creation", "stewardship", "forgiveness", "reconciliation",
                  "religious", "moral", "values"),
        subject_keys=("rme",),
        throughline="God worshiper",
        story_label="Redemption",
        story_text=(
            "The greatest commandments are to love God with all the heart, "
            "soul and mind, and to love one's neighbour as oneself "
            "(Matthew 22:37-39). Worship is not only words; it shapes how "
            "believers treat God, other people and the world."
        ),
        scripture="Matthew 22:37-39",
        virtue="wholehearted love for God and neighbour",
        habit="connecting what they learn to how they live",
        creation_truth="faith is lived through concrete choices of love and obedience",
        invitation="put their learning into one act of love, forgiveness or service this week",
    ),
    _Theme(
        key="body_discipline",
        keywords=("fitness", "health", "exercise", "warm up", "strength",
                  "endurance", "flexibility", "balance", "coordination",
                  "agility", "speed", "teamwork", "fair play", "sportsmanship",
                  "nutrition", "hygiene", "safety", "injury", "first aid"),
        subject_keys=("phe",),
        throughline="God worshiper",
        story_label="Creation",
        story_text=(
            "The body is described in 1 Corinthians 6:19-20 as a temple of the "
            "Holy Spirit, so believers are called to care for it and use it "
            "with self-control. Sport also gives a concrete place to practise "
            "fair play and service."
        ),
        scripture="1 Corinthians 6:19-20",
        virtue="self-control, perseverance and fair play",
        habit="training safely and honouring opponents",
        creation_truth="the body is a gift to be cared for and offered in service",
        invitation="use their physical abilities to encourage teammates and serve others",
    ),
    _Theme(
        key="wisdom_work",
        keywords=("work", "job", "career", "business", "entrepreneur",
                  "customer", "service", "quality", "safety", "procedure",
                  "skills", "skill", "diligence", "responsibility"),
        subject_keys=("career technology",),
        throughline="Servant worker",
        story_label="Creation",
        story_text=(
            "Work is part of God's good design before the fall, and Colossians "
            "3:23 calls believers to work heartily as for the Lord. Proverbs "
            "22:29 commends diligence and skill. The classroom workshop is a "
            "place to practise both."
        ),
        scripture="Colossians 3:23; Proverbs 22:29",
        virtue="diligence, integrity and service",
        habit="working carefully and finishing what they start",
        creation_truth="good work serves real people and reflects God's own faithfulness",
        invitation="use their skills honestly to serve customers, families and the community",
    ),
    _Theme(
        key="faithful_learning",
        keywords=(),
        subject_keys=(),
        throughline="Community builder",
        story_label="Creation",
        story_text=(
            "Every good gift comes from God, including the ability to learn "
            "(James 1:17). A classroom is a place where learners can practise "
            "honesty, patience and care for one another."
        ),
        scripture="James 1:17",
        virtue="humility, curiosity and care for classmates",
        habit="asking good questions and helping a classmate understand",
        creation_truth="learning is a gift that grows when it is shared",
        invitation="use what they learn to help another person and to serve their community",
    ),
)

_SUBJECT_TO_THEME = {
    "mathematics": "order_pattern",
    "computing": "design_parts",
    "science": "life_systems",
    "english": "language_truth",
    "social studies": "justice_community",
    "creative arts": "creativity_craft",
    "rme": "worship_faith",
    "phe": "body_discipline",
    "career technology": "wisdom_work",
}


def _get(lesson: Any, name: str, default=None):
    if isinstance(lesson, dict):
        return lesson.get(name, default)
    return getattr(lesson, name, default)


def _display(value: Any) -> str:
    """Enum/display value without the ``Subject.MATHEMATICS`` prefix."""
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _subject_key(subject: str) -> str:
    value = (subject or "").strip().lower()
    for key in _SUBJECT_TO_THEME:
        if value == key or key in value:
            return key
    if "ict" in value or "computer" in value:
        return "computing"
    if "science" in value:
        return "science"
    if "math" in value:
        return "mathematics"
    if "english" in value or "language" in value:
        return "english"
    if "social" in value:
        return "social studies"
    if "creative" in value or "art" in value:
        return "creative arts"
    if "religious" in value or value == "rme":
        return "rme"
    if "physical" in value or value == "phe":
        return "phe"
    return ""


def _source_text(lesson: Any) -> str:
    parts: Iterable[Any] = (
        _display(_get(lesson, "subject", "")),
        _display(_get(lesson, "strand", "")),
        _display(_get(lesson, "sub_strand", "")),
        _display(_get(lesson, "content_standard", "")),
        " ".join(_display(i) for i in (_get(lesson, "indicators", []) or [])),
        _display(_get(lesson, "lesson_topic", "")),
        " ".join(_display(k) for k in (_get(lesson, "keywords", []) or [])),
    )
    return " ".join(str(p or "") for p in parts).lower()


def _choose_theme(lesson: Any) -> _Theme:
    subject_key = _subject_key(_display(_get(lesson, "subject", "")))
    text = _source_text(lesson)
    best = None
    best_score = 0
    for theme in _THEMES:
        score = sum(1 for keyword in theme.keywords
                    if keyword and keyword in text)
        if subject_key and subject_key in theme.subject_keys:
            score += 2
        if theme.keywords and score > best_score:
            best, best_score = theme, score
    if best is not None:
        return best
    fallback = _SUBJECT_TO_THEME.get(subject_key, "")
    for theme in _THEMES:
        if theme.key == fallback:
            return theme
    return _THEMES[-1]


def _focus_phrase(lesson: Any) -> str:
    text = ""
    indicators = list(_get(lesson, "indicators", []) or [])
    if indicators:
        text = str(indicators[0] or "")
    if not text:
        text = str(_get(lesson, "lesson_topic", "") or "")
    from ..curriculum.vocabulary import normalize_numeric_groups
    text = normalize_numeric_groups(" ".join(text.split()))
    text = text.strip(" .;:,")
    if not text:
        return "this lesson's focus"
    # Drop a trailing apparatus clause: the resource list is not the topic.
    text = re.split(
        r"\s+(?:using|with the use of|through the use of|by means of|with|through)\s+.+$",
        text, maxsplit=1, flags=re.IGNORECASE,
    )[0].strip(" ,;:")
    # Stop at the first sentence break.
    text = re.split(r"[.;]", text)[0].strip() or text
    # Drop the leading measurable verb so the phrase reads after "as they".
    words = text.split()
    if words and words[0].lower() in {
            "model", "identify", "describe", "explain", "discuss", "state",
            "use", "apply", "solve", "calculate", "demonstrate", "show",
            "read", "write", "classify", "compare", "investigate", "design",
            "create", "perform", "measure", "construct", "draw", "name",
            "list", "define", "recognise", "recognize", "illustrate"}:
        words = words[1:]
    dangling = {"using", "with", "from", "of", "in", "on", "to", "for", "by",
                "and", "or", "at", "as", "the", "a", "an"}
    while len(words) > 3 and words[-1].lower().strip(".,:;") in dangling:
        words.pop()
    if len(words) > 14:
        words = words[:14]
        while len(words) > 3 and words[-1].lower().strip(".,:;") in dangling:
            words.pop()
    phrase = " ".join(words).strip(" .;:,")
    return phrase or "this lesson's focus"


def throughline_connection(theme: _Theme, focus: str, label: str = "") -> str:
    """A brief practice note for a throughline label (not a definition)."""
    chosen = _safe_label(label, WAPEF_THROUGH_LINES) if label else ""
    if chosen:
        habit = _THROUGHLINE_HABITS.get(chosen, theme.habit)
        return (
            f"{chosen} — Learners practise {habit} as they work with {focus}."
        )
    return (
        f"{theme.throughline} — Learners practise {theme.habit} as they work "
        f"with {focus}."
    )


def gods_story_for_label(label: str, theme: _Theme, focus: str) -> str:
    """Compose God's Story around the selected approved label."""
    chosen = _safe_label(label, WAPEF_GODS_STORY)
    narrative = _STORY_LABELS.get(chosen) if chosen else ""
    if not narrative:
        narrative = theme.story_text
        chosen = theme.story_label
    return (
        f"{chosen} — {narrative} In this lesson, learners work with {focus}, "
        f"and the teacher helps them see that {theme.creation_truth}. "
        f"Reference: {theme.scripture}."
    )



def _safe_label(value: str, approved: Iterable[str]) -> str:
    wanted = " ".join((value or "").split()).strip().lower().rstrip(".")
    for option in approved:
        if " ".join(option.split()).strip().lower().rstrip(".") == wanted:
            return option
    return ""


def _subject_domain(subject: str) -> str:
    """A natural domain phrase for Deep Hope (not an enum label)."""
    value = (subject or "").strip()
    low = value.lower()
    if not low:
        return "their learning"
    if "comput" in low or low == "ict" or "digital" in low:
        return "technology"
    if "english" in low:
        return "English"
    if "ghanaian language" in low or low in {"fante", "twi", "ewe", "ga"}:
        return "language"
    if "mathematics" in low or "math" in low:
        return "mathematics"
    if "science" in low:
        return "science"
    if "social" in low:
        return "social studies"
    if "creative" in low or "art" in low:
        return "the creative arts"
    if "religious" in low or low == "rme":
        return "faith and life"
    if "physical" in low or low == "phe":
        return "health and movement"
    return low


def suggest_wapef_fields(lesson: Any) -> Dict[str, Any]:
    """Suggested WAPEF values for one lesson.

    Returns ``deep_hope``, ``storyline``, ``through_lines`` and ``gods_story``.
    The values are complete, lesson-specific prose (except ``through_lines``,
    which is the approved label list) so a teacher can accept them as-is.
    """
    theme = _choose_theme(lesson)
    focus = _focus_phrase(lesson)
    subject = _display(_get(lesson, "subject", ""))
    domain = _subject_domain(subject)

    deep_hope = (
        f"That learners will grow in {theme.virtue}, so that they practise "
        f"{theme.habit} and use {domain} to serve God and their neighbours."
    )
    storyline = (
        f"God's story tells of creation, human failure, redemption and "
        f"restoration. In this lesson, learners work with {focus}. They "
        f"discover that {theme.creation_truth}, and they are invited to "
        f"{theme.invitation}."
    )
    gods_story = (
        f"{theme.story_label} — {theme.story_text} In this lesson, learners "
        f"work with {focus}, and the teacher helps them see that "
        f"{theme.creation_truth}. Reference: {theme.scripture}."
    )
    through_label = _safe_label(theme.throughline, WAPEF_THROUGH_LINES)
    through_lines = [through_label] if through_label else []
    return {
        "deep_hope": deep_hope,
        "storyline": storyline,
        "through_lines": through_lines,
        "gods_story": gods_story,
        "throughline_note": throughline_connection(theme, focus),
        "story_label": _safe_label(theme.story_label, WAPEF_GODS_STORY),
        "theme": theme.key,
        "scripture": theme.scripture,
    }


def wapef_field_text(lesson: Any, field: str) -> str:
    """Render one WAPEF cell: teacher value first, generated connection second.

    A teacher-selected approved label is preserved exactly and followed by a
    lesson-specific PRACTICE sentence, so the cell is meaningful without the
    label being rewritten. A teacher's own free text is returned verbatim.
    """
    theme = _choose_theme(lesson)
    focus = _focus_phrase(lesson)
    suggestion = suggest_wapef_fields(lesson)

    if field == "through_lines":
        raw = _get(lesson, "wapef_through_lines", [])
        if isinstance(raw, str):
            raw = [line.strip() for line in raw.splitlines() if line.strip()]
        labels = [str(line).strip() for line in (raw or []) if str(line).strip()]
        if not labels:
            labels = list(suggestion.get("through_lines") or [])
            if not labels:
                return ""
        approved = normalize_through_lines(labels)
        approved_lower = {line.lower() for line in approved}
        custom = [line for line in labels
                  if line.lower() not in approved_lower]
        ordered = approved + [line for line in custom
                              if line.lower() not in {x.lower() for x in approved}]
        # Keep the approved list as one readable phrase (the form's established
        # presentation), then explain how learners practise each habit.
        notes: List[str] = []
        for label in ordered:
            chosen = _safe_label(label, WAPEF_THROUGH_LINES)
            habit = _THROUGHLINE_HABITS.get(chosen, theme.habit) if chosen else label
            notes.append(f"{habit} while working with {focus}")
        sentence = format_through_lines(ordered)
        if notes:
            if len(notes) == 1:
                sentence += f". Learners practise {notes[0]}."
            else:
                sentence += ". Learners practise " + "; ".join(notes[:-1]) + f"; and {notes[-1]}."
        return sentence

    if field == "deep_hope":
        raw = str(_get(lesson, "wapef_deep_hope", "") or "").strip()
        if not raw:
            return suggestion["deep_hope"]
        # The approved Deep Hope is already a complete formative statement;
        # never pad or rewrite it. Teacher free text is equally authoritative.
        return raw

    if field == "storyline":
        raw = str(_get(lesson, "wapef_storyline", "") or "").strip()
        if not raw:
            return suggestion["storyline"]
        if _safe_label(raw, WAPEF_STORYLINES):
            return (
                f"{raw} In this lesson, learners work with {focus} and "
                f"discover that {theme.creation_truth}."
            )
        return raw

    if field == "gods_story":
        raw = str(_get(lesson, "wapef_gods_story", "") or "").strip()
        if not raw:
            return suggestion["gods_story"]
        if _safe_label(raw, WAPEF_GODS_STORY):
            return gods_story_for_label(raw, theme, focus)
        return raw

    return ""

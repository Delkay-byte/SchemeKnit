"""
SchemeKnit Indicator Interpreter
=================================

Analyzes a single curriculum indicator and derives structured pedagogical
information BEFORE the AI generation step.

This is deterministic — no AI calls. It uses verb analysis, subject heuristics,
and curriculum knowledge to inform the generation engine what the indicator
REQUIRES learners to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import Indicator, CurriculumWeekType


# ── Verb Taxonomy ──────────────────────────────────────────────────────────

# Bloom's Revised Taxonomy mapped to observable verbs
BLOOM_CATEGORIES = {
    "remember": [
        "list", "recall", "identify", "name", "state", "define", "label",
        "match", "recognise", "recognize", "describe", "enumerate",
    ],
    "understand": [
        "explain", "describe", "summarise", "summarize", "interpret",
        "classify", "compare", "contrast", "discuss", "paraphrase",
        "illustrate", "give examples", "exemplify", "clarify",
    ],
    "apply": [
        "apply", "use", "demonstrate", "solve", "calculate", "perform",
        "execute", "implement", "construct", "build", "make", "draw",
        "record", "measure", "complete", "practice", "practise",
    ],
    "analyze": [
        "analyze", "analyse", "examine", "investigate", "compare",
        "differentiate", "distinguish", "categorize", "categorise",
        "break down", "organise", "organize", "find", "determine",
    ],
    "evaluate": [
        "evaluate", "assess", "judge", "justify", "critique", "review",
        "argue", "defend", "prioritise", "prioritize", "recommend",
        "decide", "select", "choose", "rate",
    ],
    "create": [
        "create", "design", "construct", "develop", "formulate",
        "compose", "produce", "plan", "invent", "devise", "originate",
        "write", "compose", "assemble",
    ],
}

# Activity type keywords
ACTIVITY_KEYWORDS = {
    "demonstration": ["demonstrate", "show", "illustrate", "model"],
    "investigation": ["investigate", "explore", "examine", "enquiry", "inquiry"],
    "discussion": ["discuss", "debate", "talk", "share views"],
    "practical": ["construct", "build", "make", "create", "perform", "practise", "practice"],
    "problem_solving": ["solve", "calculate", "compute", "find", "determine"],
    "classification": ["classify", "categorise", "categorize", "sort", "group", "match"],
    "observation": ["observe", "watch", "notice", "identify"],
    "reading": ["read", "study", "review text", "comprehend"],
    "writing": ["write", "compose", "draft", "record"],
    "reflection": ["reflect", "evaluate", "assess", "review"],
    "comparison": ["compare", "contrast", "differentiate", "distinguish"],
    "creation": ["create", "design", "invent", "develop", "plan"],
    "analysis": ["analyze", "analyse", "examine", "break down"],
}


@dataclass
class IndicatorInterpretation:
    """Structured interpretation of a single curriculum indicator."""
    indicator_code: str
    indicator_text: str

    # Bloom's taxonomy
    bloom_level: str                        # primary Bloom's level
    bloom_verbs: List[str]                  # verbs found in the indicator

    # Activity type
    activity_type: str                      # primary activity type
    activity_keywords: List[str]            # matching keywords

    # Pedagogical implications
    primary_action: str                     # what learners must DO (paraphrased)
    expected_performance: str               # observable outcome
    knowledge_focus: str                    # content domain
    evidence_of_achievement: str            # how to verify learning
    prerequisite_knowledge: str             # what learners need first
    misconception_risks: str                # common misunderstandings
    assessment_mode: str                    # recommended assessment approach

    # Strategy hints
    suggested_phases: List[str]             # e.g. ["predict", "observe", "explain"]
    suggested_resources: List[str]          # contextually appropriate resources
    subject_context: str                    # subject-specific guidance


# ── Subject-Specific Strategy Maps ────────────────────────────────────────

SUBJECT_STRATEGIES = {
    "science": {
        "verbs": ["predict", "observe", "explain", "demonstrate", "investigate",
                  "classify", "construct", "analyze", "compare", "measure"],
        "phases": ["predict", "observe", "explain", "practical_task"],
        "resources": ["specimens", "charts", "diagrams", "practical materials",
                      "locally available materials"],
        "context": "Use practical inquiry and observation. Connect to everyday Ghanaian life.",
    },
    "mathematics": {
        "verbs": ["calculate", "solve", "construct", "draw", "measure",
                  "identify", "classify", "compare", "explain", "demonstrate"],
        "phases": ["worked_example", "guided_practice", "independent_practice"],
        "resources": ["manipulatives", "chalkboard", "rulers", "protractors",
                      "grid paper", "locally available materials"],
        "context": "Use concrete-pictorial-abstract approach. Connect to real-life Ghanaian contexts.",
    },
    "english": {
        "verbs": ["read", "write", "speak", "listen", "discuss", "compose",
                  "identify", "explain", "demonstrate", "create"],
        "phases": ["model", "guided_practice", "independent_practice"],
        "resources": ["textbook", "charts", "real objects", "role play",
                      "picture cards", "writing materials"],
        "context": "Emphasize communication skills. Use oral tradition and local contexts.",
    },
    "social_studies": {
        "verbs": ["discuss", "explain", "identify", "compare", "analyze",
                  "describe", "illustrate", "justify", "evaluate"],
        "phases": ["scenario", "source_analysis", "discussion", "application"],
        "resources": ["maps", "charts", "local scenarios", "case studies",
                      "newspaper clippings"],
        "context": "Use local Ghanaian scenarios. Connect to community and national issues.",
    },
    "creative_arts": {
        "verbs": ["create", "design", "draw", "paint", "model", "perform",
                  "sing", "dance", "demonstrate", "observe", "critique"],
        "phases": ["observe", "demonstrate", "create", "critique", "present"],
        "resources": ["art materials", " locally available materials", "colours",
                      "paper", "clay", "instruments"],
        "context": "Hands-on creative work. Use local cultural contexts and materials.",
    },
    "computing": {
        "verbs": ["demonstrate", "apply", "create", "troubleshoot", "design",
                  "program", "debug", "analyze", "explain"],
        "phases": ["demonstration", "guided_practice", "hands_on_task", "challenge"],
        "resources": ["computers", "unplugged activities", "diagrams",
                      "flowcharts", "locally available materials"],
        "context": "Use both digital and unplugged activities. Connect to everyday technology.",
    },
    "rme": {
        "verbs": ["discuss", "compare", "reflect", "explain", "identify",
                  "illustrate", "demonstrate", "apply", "justify"],
        "phases": ["story", "discussion", "compare_values", "reflection", "application"],
        "resources": ["Bible/Quran", "real-life scenarios", "community examples",
                      "charts", "role play"],
        "context": "Use stories and scenarios. Respect diverse beliefs. Connect to moral life.",
    },
    "career_technology": {
        "verbs": ["demonstrate", "construct", "identify", "apply", "explain",
                  "design", "evaluate", "practise", "practice"],
        "phases": ["demonstration", "materials_identification", "practical_activity",
                    "reflection"],
        "resources": ["raw materials", "tools", "locally available materials",
                      "workshop items"],
        "context": "Practical hands-on work. Use locally available materials and tools.",
    },
    "ghanaian_language": {
        "verbs": ["read", "write", "speak", "listen", "discuss", "compose",
                  "identify", "explain", "demonstrate", "perform"],
        "phases": ["oral_practice", "reading", "writing", "discussion"],
        "resources": ["textbook", "charts", "local materials", "role play",
                      "picture cards"],
        "context": "Emphasize oral language and cultural connection. Use proverbs and stories.",
    },
    "french": {
        "verbs": ["listen", "speak", "read", "write", "role-play", "demonstrate",
                  "identify", "compare", "describe", "practice"],
        "phases": ["listen", "repeat", "practice", "communicate"],
        "resources": ["textbook", "audio materials", "picture cards", "real objects"],
        "context": "Emphasize communication and practical use. Connect to everyday situations.",
    },
}

# Subject name → strategy key mapping
SUBJECT_TO_STRATEGY = {
    "science": "science",
    "integrated science": "science",
    "mathematics": "mathematics",
    "core mathematics": "mathematics",
    "english": "english",
    "english language": "english",
    "social studies": "social_studies",
    "creative arts and design": "creative_arts",
    "creative arts": "creative_arts",
    "computing": "computing",
    "ict": "computing",
    "religious and moral education": "rme",
    "rme": "rme",
    "career technology": "career_technology",
    "career and technology": "career_technology",
    "ghanaian language": "ghanaian_language",
    "french": "french",
    "french language": "french",
}


# ── Core Interpretation Functions ──────────────────────────────────────────

def _extract_verbs(text: str) -> List[str]:
    """Extract action verbs from indicator text."""
    words = re.findall(r'\b[a-z]+(?:ed|ing|s)?\b', text.lower())
    verbs = []
    all_bloom_verbs = []
    for level, verb_list in BLOOM_CATEGORIES.items():
        all_bloom_verbs.extend(verb_list)

    for word in words:
        for verb in all_bloom_verbs:
            if word == verb or word.startswith(verb):
                if verb not in verbs:
                    verbs.append(verb)
    return verbs


def _determine_bloom_level(verbs: List[str]) -> str:
    """Determine the primary Bloom's taxonomy level from verbs."""
    for level in ["create", "evaluate", "analyze", "apply", "understand", "remember"]:
        level_verbs = BLOOM_CATEGORIES[level]
        for v in verbs:
            if v in level_verbs:
                return level
    return "understand"


def _determine_activity_type(verbs: List[str], text: str) -> str:
    """Determine the primary activity type from verbs and context."""
    text_lower = text.lower()
    for act_type, keywords in ACTIVITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower or any(kw in v for v in verbs):
                return act_type
    return "discussion"


def _derive_evidence_of_achievement(bloom_level: str, activity_type: str,
                                     indicator_text: str) -> str:
    """Derive what evidence would show the learner achieved the indicator."""
    evidence_map = {
        "remember": "Learner can recall and list key facts or terms.",
        "understand": "Learner can explain or describe the concept in own words.",
        "apply": "Learner can correctly use the concept in a given situation.",
        "analyze": "Learner can break down the concept and identify relationships.",
        "evaluate": "Learner can make justified judgments based on criteria.",
        "create": "Learner can produce original work applying the concept.",
    }
    return evidence_map.get(bloom_level, "Learner demonstrates understanding.")


def _derive_misconception_risks(indicator_text: str, subject: str) -> str:
    """Identify likely misconception risks based on content."""
    risks = []
    text_lower = indicator_text.lower()

    if any(kw in text_lower for kw in ["energy", "force", "motion"]):
        risks.append("Confusing energy forms or force directions.")
    if any(kw in text_lower for kw in ["fraction", "ratio", "percentage"]):
        risks.append("Incorrect operations with parts of a whole.")
    if any(kw in text_lower for kw in ["photosynthesis", "respiration", "plant"]):
        risks.append("Confusing plant processes or organism roles.")
    if any(kw in text_lower for kw in ["volta", "river", "lake"]):
        risks.append("Mixing up geographical features of Ghana.")
    if any(kw in text_lower for kw in ["adjective", "verb", "noun", "tense"]):
        risks.append("Confusing grammar categories or their usage.")

    return "; ".join(risks) if risks else "Monitor for general misconceptions."


def _derive_assessment_mode(bloom_level: str, activity_type: str) -> str:
    """Recommend assessment approach."""
    assessment_map = {
        "demonstration": "Observation of practical performance with checklist.",
        "investigation": "Lab report or investigation record with findings.",
        "discussion": "Oral questions and observation of participation.",
        "practical": "Practical task assessment with rubric.",
        "problem_solving": "Written problem-solving with step marks.",
        "classification": "Classification exercise with accuracy check.",
        "observation": "Guided observation record.",
        "reading": "Comprehension questions or oral reading assessment.",
        "writing": "Writing sample assessment with rubric.",
        "reflection": "Written reflection or journal entry.",
        "comparison": "Comparison chart or Venn diagram assessment.",
        "creation": "Product or performance assessment with rubric.",
        "analysis": "Written analysis with structured questions.",
    }
    return assessment_map.get(activity_type, "Oral questions and observation.")


def _derive_suggested_phases(activity_type: str, bloom_level: str) -> List[str]:
    """Suggest lesson phases based on activity and cognitive level."""
    phase_map = {
        "demonstration": ["introduction", "demonstration", "guided_practice", "assessment"],
        "investigation": ["introduction", "prediction", "investigation", "discussion", "conclusion"],
        "discussion": ["introduction", "presentation", "discussion", "application", "reflection"],
        "practical": ["introduction", "demonstration", "practice", "assessment", "reflection"],
        "problem_solving": ["introduction", "worked_example", "guided_practice", "independent_practice", "assessment"],
        "classification": ["introduction", "presentation", "classification_activity", "assessment", "reflection"],
        "observation": ["introduction", "observation_task", "recording", "discussion", "reflection"],
        "reading": ["introduction", "vocabulary_work", "reading_activity", "comprehension", "discussion"],
        "writing": ["introduction", "model_text", "guided_writing", "independent_writing", "sharing"],
        "reflection": ["introduction", "experience_review", "reflection_activity", "sharing", "conclusion"],
        "comparison": ["introduction", "first_item", "second_item", "comparison_activity", "conclusion"],
        "creation": ["introduction", "inspiration", "creation_time", "critique", "revision"],
        "analysis": ["introduction", "data_presentation", "analysis_activity", "findings", "conclusion"],
    }
    return phase_map.get(activity_type, ["introduction", "main_activity", "assessment", "reflection"])


def _derive_subject_context(subject: str) -> str:
    """Get subject-specific pedagogical guidance."""
    subject_lower = subject.lower().strip()
    strategy_key = SUBJECT_TO_STRATEGY.get(subject_lower, "")
    if strategy_key and strategy_key in SUBJECT_STRATEGIES:
        return SUBJECT_STRATEGIES[strategy_key]["context"]
    return "Use contextually appropriate methods for Ghanaian classrooms."


def _derive_suggested_resources(subject: str, activity_type: str) -> List[str]:
    """Suggest resources based on subject and activity type."""
    subject_lower = subject.lower().strip()
    strategy_key = SUBJECT_TO_STRATEGY.get(subject_lower, "")
    if strategy_key and strategy_key in SUBJECT_STRATEGIES:
        return SUBJECT_STRATEGIES[strategy_key]["resources"]
    return ["chalkboard", "charts", "locally available materials"]


# ── Main Interpretation Function ──────────────────────────────────────────

def interpret_indicator(indicator: Indicator, subject: str) -> IndicatorInterpretation:
    """Interpret a single indicator and derive pedagogical information.

    This is DETERMINISTIC — no AI calls. It analyzes the indicator text
    using verb taxonomy, subject heuristics, and curriculum knowledge.
    """
    text = indicator.description or indicator.exact_text
    code = indicator.code

    # Extract verbs and determine Bloom's level
    verbs = _extract_verbs(text)
    bloom_level = _determine_bloom_level(verbs)
    activity_type = _determine_activity_type(verbs, text)

    # Derive pedagogical fields
    evidence = _derive_evidence_of_achievement(bloom_level, activity_type, text)
    misconceptions = _derive_misconception_risks(text, subject)
    assessment = _derive_assessment_mode(bloom_level, activity_type)
    phases = _derive_suggested_phases(activity_type, bloom_level)
    resources = _derive_suggested_resources(subject, activity_type)
    context = _derive_subject_context(subject)

    # Primary action: the first verb phrase
    primary_action = verbs[0] if verbs else "learn"

    # Expected performance: paraphrase the indicator
    expected = text.strip()
    if expected.lower().startswith("learners can"):
        expected = expected[len("learners can"):].strip()
    if expected.lower().startswith("students can"):
        expected = expected[len("students can"):].strip()

    # Knowledge focus: the sub-strand or topic context
    knowledge_focus = indicator.source_subject

    # Prerequisite knowledge
    prereq = f"Prior understanding of {indicator.source_subject} concepts."

    interpretation = IndicatorInterpretation(
        indicator_code=code,
        indicator_text=text,
        bloom_level=bloom_level,
        bloom_verbs=verbs,
        activity_type=activity_type,
        activity_keywords=ACTIVITY_KEYWORDS.get(activity_type, []),
        primary_action=primary_action,
        expected_performance=expected,
        knowledge_focus=knowledge_focus,
        evidence_of_achievement=evidence,
        prerequisite_knowledge=prereq,
        misconception_risks=misconceptions,
        assessment_mode=assessment,
        suggested_phases=phases,
        suggested_resources=resources,
        subject_context=context,
    )

    # Back-fill the Indicator dataclass
    indicator.primary_action = primary_action
    indicator.expected_performance = expected
    indicator.knowledge_focus = knowledge_focus
    indicator.evidence_of_achievement = evidence
    indicator.prerequisite_knowledge = prereq
    indicator.misconception_risks = misconceptions
    indicator.assessment_mode = assessment
    indicator.activity_type = activity_type

    return interpretation


def interpret_indicators(indicators: List[Indicator], subject: str) -> List[IndicatorInterpretation]:
    """Interpret a list of indicators for a given subject."""
    return [interpret_indicator(ind, subject) for ind in indicators]

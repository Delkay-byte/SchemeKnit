"""
SchemeKnit V2 Generation Prompt Builder
=========================================

Constructs structured, indicator-grounded prompts for AI lesson generation.

The prompt is built from:
- Deterministic curriculum context (no guessing)
- Indicator interpretation (verb analysis, activity type)
- Subject-specific pedagogical strategy
- Ghanaian classroom context
- Structured output schema

Every generated lesson is anchored to ONE verified indicator.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .indicator_interpreter import (
    IndicatorInterpretation,
    SUBJECT_STRATEGIES,
    SUBJECT_TO_STRATEGY,
)


# ── Structured Output Schema ──────────────────────────────────────────────

LESSON_OUTPUT_SCHEMA = """
{
  "lesson_identity": {
    "subject": "string",
    "class_level": "string",
    "strand": "string",
    "sub_strand": "string",
    "indicator_code": "string",
    "indicator_text": "string",
    "lesson_topic": "string"
  },
  "curriculum_context": {
    "content_standard": "string",
    "bloom_level": "string",
    "activity_type": "string"
  },
  "learning_objectives": [
    "Learners can <measurable verb> <specific content>"
  ],
  "prior_knowledge": "What learners need to know before this lesson",
  "key_vocabulary": ["term1", "term2", "term3"],
  "resources": {
    "source_resources": ["from the scheme"],
    "suggested_alternatives": ["locally available alternatives"]
  },
  "starter": {
    "activity": "Description of starter activity",
    "duration_minutes": 10,
    "teacher_action": "What the teacher does",
    "learner_action": "What learners do"
  },
  "main_learning": {
    "phase1": {
      "name": "Phase name",
      "activity": "Description",
      "duration_minutes": 20,
      "teacher_action": "What the teacher does",
      "learner_action": "What learners do",
      "resources_used": ["resources for this phase"]
    },
    "phase2": { ... }
  },
  "assessment": {
    "method": "How learning is checked",
    "activity": "Specific assessment task",
    "success_criteria": "How to know learners achieved the indicator",
    "duration_minutes": 10
  },
  "plenary": {
    "activity": "Reflection/summary activity",
    "duration_minutes": 5,
    "teacher_action": "What the teacher does",
    "learner_action": "What learners do"
  },
  "differentiation": {
    "support": "How to help struggling learners",
    "core": "Main task for most learners",
    "extension": "Challenge for advanced learners"
  },
  "homework_or_extension": "Optional homework or extension task",
  "teacher_notes": "Additional notes for the teacher"
}
"""


# ── System Prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Ghanaian educator and curriculum specialist.

You generate lesson plans that are:
1. INDICATOR-GROUNDED: Every element traces back to the specific curriculum indicator.
2. SUBJECT-AWARE: Pedagogy matches the subject discipline.
3. MEASURABLE: Objectives use observable verbs, not vague terms.
4. COHERENT: Starter → Main → Assessment → Plenary form a logical instructional story.
5. PRACTICAL: Activities work in ordinary Ghanaian classrooms with available resources.
6. DIFFERENTIATED: Support, core, and extension are compact and actionable.

RULES:
- NEVER invent curriculum codes, textbook page numbers, or official references.
- NEVER use vague objectives like "understand", "know", or "appreciate".
- NEVER produce the same lesson structure for every subject.
- ALWAYS connect assessment to the indicator and objectives.
- ALWAYS use the indicator's action verb in the objectives.
- ALWAYS provide realistic Ghanaian classroom activities.
- Output MUST be valid JSON matching the provided schema.
"""


# ── Subject Strategy Builders ─────────────────────────────────────────────

def _get_strategy_context(subject: str) -> Dict[str, Any]:
    """Get the subject-specific strategy context."""
    subject_lower = subject.lower().strip()
    strategy_key = SUBJECT_TO_STRATEGY.get(subject_lower, "")
    if strategy_key and strategy_key in SUBJECT_STRATEGIES:
        return SUBJECT_STRATEGIES[strategy_key]
    return {
        "verbs": [],
        "phases": ["introduction", "main_activity", "assessment", "reflection"],
        "resources": ["chalkboard", "charts", "locally available materials"],
        "context": "Use contextually appropriate methods for Ghanaian classrooms.",
    }


def _build_phases_guidance(interpretation: IndicatorInterpretation) -> str:
    """Build the lesson phase guidance from interpretation."""
    phases = interpretation.suggested_phases
    phase_descriptions = {
        "introduction": "Brief review of prior knowledge, hook to engage learners.",
        "demonstration": "Teacher shows or models the concept/process.",
        "presentation": "Teacher presents new content with examples.",
        "guided_practice": "Learners practice with teacher support.",
        "independent_practice": "Learners work independently.",
        "practical_task": "Hands-on activity with materials.",
        "investigation": "Learners explore and discover.",
        "discussion": "Structured class or group discussion.",
        "prediction": "Learners predict before observing.",
        "observation": "Learners observe and record.",
        "explanation": "Learners explain their findings.",
        "classification": "Learners sort, categorize, or group.",
        "comparison": "Learners compare and contrast items.",
        "reflection": "Learners reflect on what they learned.",
        "application": "Learners apply learning to new situations.",
        "assessment": "Check understanding of the indicator.",
        "conclusion": "Summarize key learning and set homework.",
        "reading": "Guided or independent reading activity.",
        "writing": "Guided or independent writing activity.",
        "oral_practice": "Speaking and listening practice.",
        "vocabulary_work": "Key term introduction and practice.",
        "model_text": "Example text for analysis.",
        "model": "Teacher models the skill or process.",
        "worked_example": "Teacher works through an example step by step.",
        "scenario": "Real-life or hypothetical scenario for analysis.",
        "source_analysis": "Analyzing primary or secondary sources.",
        "case_study": "Case study analysis.",
        "story": "Story, scenario, or narrative for engagement.",
        "compare_values": "Comparing different perspectives or values.",
        "materials_identification": "Identifying and describing materials.",
        "hands_on_task": "Hands-on practical activity.",
        "challenge": "Extension or challenge activity.",
        "creation_time": "Time for learners to create.",
        "critique": "Peer or self-assessment.",
        "revision": "Review and refine work.",
        "inspiration": "Exposure to examples or ideas.",
        "data_presentation": "Presenting data or information.",
        "findings": "Sharing and discussing findings.",
        "recording": "Recording observations or results.",
        "sharing": "Sharing work with peers.",
        "comprehension": "Checking understanding of text.",
        "second_item": "Analyzing the second item for comparison.",
    }

    guidance_lines = []
    for i, phase in enumerate(phases, 1):
        desc = phase_descriptions.get(phase, "Activity phase.")
        guidance_lines.append(f"  Phase {i} ({phase}): {desc}")

    return "\n".join(guidance_lines) if guidance_lines else "  Standard lesson phases."


# ── Main Prompt Builder ───────────────────────────────────────────────────

def build_generation_prompt(
    *,
    subject: str,
    class_level: str,
    strand: str,
    sub_strand: str,
    content_standard: str,
    indicator_code: str,
    indicator_text: str,
    interpretation: IndicatorInterpretation,
    class_size: int = 35,
    duration_minutes: int = 60,
    previous_lesson_context: Optional[str] = None,
    next_lesson_context: Optional[str] = None,
    source_resources: Optional[List[str]] = None,
    teaching_day: Optional[str] = None,
    week_number: Optional[int] = None,
) -> str:
    """Build a structured, indicator-grounded generation prompt.

    Returns the user message content for the AI provider.
    """
    strategy = _get_strategy_context(subject)

    # Build the prompt
    sections = []

    # Curriculum context
    sections.append(f"""CURRICULUM CONTEXT
Subject: {subject}
Class Level: {class_level}
Strand: {strand}
Sub-Strand: {sub_strand}
Content Standard: {content_standard}
Indicator Code: {indicator_code}
Indicator: {indicator_text}""")

    # Indicator interpretation
    sections.append(f"""INDICATOR ANALYSIS
Primary Action: {interpretation.primary_action}
Bloom's Level: {interpretation.bloom_level}
Activity Type: {interpretation.activity_type}
Expected Performance: {interpretation.expected_performance}
Evidence of Achievement: {interpretation.evidence_of_achievement}
Assessment Mode: {interpretation.assessment_mode}
Misconception Risks: {interpretation.misconception_risks}""")

    # Class context
    sections.append(f"""CLASS CONTEXT
Class Size: {class_size} learners
Duration: {duration_minutes} minutes
{f'Teaching Day: {teaching_day}' if teaching_day else ''}
{f'Week: {week_number}' if week_number else ''}""")

    # Subject-specific pedagogy
    sections.append(f"""SUBJECT PEDAGOGY
{strategy.get('context', 'Use appropriate methods for Ghanaian classrooms.')}
Suggested Phases: {', '.join(strategy.get('phases', []))}""")

    # Lesson phase guidance
    sections.append(f"""LESSON PHASES (in order)
{_build_phases_guidance(interpretation)}""")

    # Previous/next lesson context
    if previous_lesson_context:
        sections.append(f"""PREVIOUS LESSON CONTEXT
{previous_lesson_context}""")
    if next_lesson_context:
        sections.append(f"""NEXT LESSON CONTEXT
{next_lesson_context}""")

    # Resources
    if source_resources:
        sections.append(f"""SOURCE RESOURCES (from the scheme)
{chr(10).join(f'- {r}' for r in source_resources)}""")
    else:
        sections.append("SOURCE RESOURCES: None specified in scheme — suggest realistic alternatives.")

    # Output requirements
    sections.append(f"""OUTPUT REQUIREMENTS
Return a JSON object matching this schema:

{LESSON_OUTPUT_SCHEMA}

CRITICAL RULES:
1. Learning objectives MUST start with "Learners can" followed by a measurable verb.
2. Assessment MUST directly check the indicator, not a general topic.
3. Starter MUST prepare learners for the main activity.
4. Main activities MUST address the objectives.
5. Plenary MUST connect to the same learning.
6. Resources MUST be realistic for Ghanaian classrooms.
7. NO invented textbook references, page numbers, or curriculum codes.
8. NO ICT/projector/smartboard assumptions unless clearly appropriate.
9. Differentiation must be COMPACT — not three separate lessons.
10. The lesson must form a COHERENT instructional story.""")

    return "\n\n".join(sections)


# ── Section Regeneration Prompt ───────────────────────────────────────────

def build_section_regeneration_prompt(
    *,
    section: str,
    current_content: str,
    subject: str,
    class_level: str,
    strand: str,
    sub_strand: str,
    indicator_text: str,
    interpretation: Optional[IndicatorInterpretation] = None,
    additional_context: str = "",
) -> str:
    """Build a prompt for regenerating a single lesson section."""
    strategy = _get_strategy_context(subject)

    prompt = f"""REGENERATE THE '{section.upper()}' SECTION

Subject: {subject}
Class Level: {class_level}
Strand: {strand}
Sub-Strand: {sub_strand}
Indicator: {indicator_text}"""

    if interpretation:
        prompt += f"""
Activity Type: {interpretation.activity_type}
Bloom's Level: {interpretation.bloom_level}"""

    prompt += f"""
Subject Pedagogy: {strategy.get('context', '')}

Current content:
{current_content or '(empty)'}

{f'Additional context: {additional_context}' if additional_context else ''}

RULES:
- Keep the content appropriate for {class_level} learners in Ghana.
- Use observable verbs, not vague terms.
- Connect to the specific indicator.
- Use locally available resources.
- Return ONLY the regenerated content for the '{section}' section.
- No invented references or page numbers."""

    return prompt

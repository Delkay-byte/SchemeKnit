"""
SchemeKnit Section-Level AI Regeneration

Allows regenerating individual sections of a lesson plan
while preserving all other content.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from ..database import get_db, User, LessonPlanDB, AIEnrichmentCacheDB, generate_id
from ..auth import get_current_user
from ..models import AIMode, ContentSource, SectionRegenerationRequest
from ..engines.ai_provider import (
    get_provider, resolve_provider_mode, NAMED_PROVIDERS, AIProvider,
)
from ..entitlements import require_ai_entitlement, consume_ai_generation
from ..logging_config import get_logger, log_event

router = APIRouter()
logger = get_logger()

#: Named real providers plus the legacy mode token accepted for enrichment.
REAL_AI_MODES = ("ollama", "gemini", "groq", "openai", "minimax", "opencode-zen")


def _require_ai_entitlement(user: User, db) -> User:
    """Commercial gate for AI assistance.

    Delegates to the single shared rule in entitlements so every AI entry point
    (section regeneration, lesson enrichment, generation-time enrichment) makes
    the same decision. Provider reachability is a separate, later check: an
    installed local provider never implies entitlement.
    """
    return require_ai_entitlement(user, db)

REGENERATABLE_SECTIONS = [
    "introduction", "starter_activity", "main_activities",
    "learner_activities", "teacher_activities", "assessment",
    "differentiation", "remediation", "extension",
    "conclusion", "reflection", "homework",
    "class_assignment", "home_assignment",
    "essential_questions", "learning_objectives",
    "teaching_learning_resources", "previous_knowledge",
]

#: The two AI affordances a teacher sees (never an internal pattern name).
#: AI is OFF by default and only ever runs for one section at a time.
REWRITE_MODES = {
    "suggest_another_version": (
        "Suggest ANOTHER VERSION of this section only: a different but "
        "equally valid way to deliver the SAME curriculum objective."
    ),
    "make_more_practical": (
        "Make this section MORE PRACTICAL: concrete, hands-on, using local "
        "Ghanaian materials a teacher can actually put on the table."
    ),
}
DEFAULT_REWRITE_MODE = "suggest_another_version"

#: Provider output schema keys for each regeneratable lesson section (PART W).
#: The V2 provider contract returns ``starter``/``main_learning``/``plenary``
#: (and the template validators map phases), NOT the lesson-row column names —
#: so extracting ``result["introduction"]`` from a Gemini/Groq response found
#: nothing, fell back to ``result["introduction"]`` (still empty), and the old
#: generic ``len(...) < 10`` heuristic then reported "AI response too short or
#: empty" even though the model HAD returned a valid structured lesson.
SECTION_TO_PROVIDER_KEYS = {
    "introduction": ("starter", "introduction"),
    "starter_activity": ("starter", "introduction"),
    "main_activities": ("main_learning", "main_activities"),
    "learner_activities": ("learner_activities", "main_learning"),
    "teacher_activities": ("teacher_activities", "main_learning"),
    "assessment": ("assessment",),
    "differentiation": ("differentiation", "assessment"),
    "remediation": ("differentiation", "assessment"),
    "extension": ("differentiation", "assessment"),
    "conclusion": ("plenary", "conclusion"),
    "reflection": ("plenary", "reflection", "conclusion"),
    "homework": ("homework_or_extension", "homework", "assessment"),
    "class_assignment": ("class_assignment", "assessment"),
    "home_assignment": ("home_assignment", "homework_or_extension", "homework",
                        "assessment"),
    "essential_questions": ("essential_questions", "learning_objectives"),
    "learning_objectives": ("learning_objectives",),
    "teaching_learning_resources": ("teaching_learning_resources", "resources"),
    "previous_knowledge": ("previous_knowledge", "teacher_notes"),
}

#: Minimum usable length for a REGENERATED SECTION (not the whole response).
#: Applied AFTER the provider payload is parsed and mapped; a valid structured
#: JSON response is never rejected because some OTHER field is short.
MIN_SECTION_CHARS = 10

#: Sane bounds for a single main-learning activity duration (minutes). A
#: provider that returns nonsense (0, negative, or hours) is treated as an
#: unusable suggestion rather than silently written into the lesson.
MIN_ACTIVITY_MINUTES = 1
MAX_ACTIVITY_MINUTES = 180


def _ai_error(status_code: int, code: str, message: str, diagnostic: str = "") -> HTTPException:
    """Build an HTTPException whose ``detail`` carries BOTH the safe, teacher-
    facing message and the raw provider diagnostic.

    PART H/I: the review UI must never show ``LIVE_ERROR``, provider state
    codes, exception text or HTTP codes. The frontend reads ``message``; the
    ``diagnostic`` is what backend logs / service-status surface. Keeping them
    in one payload means the detailed cause is NOT lost from diagnostics while
    still never reaching the teacher as-is.
    """
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "diagnostic": diagnostic},
    )


class SectionRegenerateRequest(BaseModel):
    lesson_plan_id: str
    section: str
    ai_mode: str = "BASIC"
    additional_context: str = ""
    #: Which affordance the teacher clicked. AI is OFF by default and only
    #: runs per-section on one of the two named rewrite actions.
    rewrite_mode: str = DEFAULT_REWRITE_MODE
    #: Client-generated id for THIS user action. Used to make the lifetime
    #: AI-generation consumption idempotent across duplicate submissions.
    request_id: str = ""


class SectionRegenerateResponse(BaseModel):
    section: str
    previous_content: str
    new_content: str
    #: Structured activities for ``main_activities`` (PART F/X). None for every
    #: other section. The frontend renders this array directly — it never has to
    #: parse provider JSON itself.
    new_activities: Optional[List[dict]] = None
    provider: str
    model: str
    mode: str
    timestamp: str
    source: str


@router.post("/regenerate-section")
async def regenerate_section(
    req: SectionRegenerateRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Regenerate a single section of a lesson plan using AI."""
    if req.section not in REGENERATABLE_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Section '{req.section}' is not regeneratable. Allowed: {', '.join(REGENERATABLE_SECTIONS)}"
        )

    lp = db.query(LessonPlanDB).filter(
        LessonPlanDB.id == req.lesson_plan_id,
        LessonPlanDB.owner_id == user.id,
    ).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson plan not found")

    _require_ai_entitlement(user, db)

    previous_content = _get_section_content(lp, req.section)

    # Named providers (gemini/groq/ollama/…) bypass the OFF/BASIC/ENHANCED
    # enum (which resolves to the deterministic Mock provider). BASIC/
    # ENHANCED resolve through the same helper as batch generation so every
    # entry point reaches the same real provider when one is configured.
    mode_in = (req.ai_mode or "").strip().lower()
    if mode_in in NAMED_PROVIDERS:
        mode_label = mode_in
        provider = get_provider(mode_in)
    else:
        ai_mode = AIMode(req.ai_mode) if req.ai_mode in [m.value for m in AIMode] else AIMode.BASIC
        mode_label = ai_mode.value
        provider = get_provider(resolve_provider_mode(ai_mode))

    if not provider or not provider.is_available():
        from ..engines.ai_provider import provider_status
        state = provider_status(provider)
        resolved = provider.get_name() if provider else "none"
        logger.warning("section_regen_provider_unavailable",
                       provider=resolved, state=state, section=req.section)
        raise _ai_error(
            503,
            "AI_UNAVAILABLE",
            "AI suggestion is currently unavailable. "
            "Your existing content was preserved.",
            diagnostic=(
                f"AI provider '{resolved}' is not available (state: {state}). "
                "No real AI provider is configured on the server."
            ),
        )

    try:
        prompt = _build_section_prompt(
            lp, req.section, previous_content, req.additional_context,
            req.rewrite_mode)
        gen_kwargs = dict(
            indicator=lp.indicators[0] if lp.indicators else "",
            strand=lp.strand or "",
            sub_strand=lp.sub_strand or "",
            content_standard=lp.content_standard or "",
        )
        if provider.get_name() == "ollama":
            # Section-targeted prompt: smaller, faster, section-relevant output.
            gen_kwargs["section"] = req.section

        # The section prompt reaches the provider through the method the
        # provider actually implements. Real providers implement
        # ``generate_structured`` and receive the per-section prompt VERBATIM
        # (a rewrite of one section, not a whole-lesson regeneration). Mocks
        # and providers without that override fall back to the legacy
        # whole-lesson call, whose payload is then mined for the section.
        result = _section_generation(provider, prompt, gen_kwargs)

        # ``main_activities`` is a STRUCTURED section: the provider's
        # ``main_learning`` object must be normalized to
        # ``[{description, duration_minutes}]`` rather than flattened to text
        # (PART F/X). Every other section keeps the flat-text contract.
        new_activities: Optional[List[dict]] = None
        if req.section == "main_activities":
            new_activities = _normalize_main_activities(result)
            new_content = "\n".join(a["description"] for a in new_activities)
        else:
            new_content = _extract_section_text(result, req.section)

        # One bounded retry for empty/short results BEFORE surfacing a provider
        # diagnostic: local models occasionally return empty/truncated output,
        # and a transient failure should be retried, not reported.
        if (not new_content or len(new_content.strip()) < MIN_SECTION_CHARS) and provider.get_name() == "ollama":
            logger.warning("ai_empty_retry", section=req.section)
            result = _section_generation(provider, prompt, gen_kwargs)
            if req.section == "main_activities":
                new_activities = _normalize_main_activities(result)
                new_content = "\n".join(a["description"] for a in new_activities)
            else:
                new_content = _extract_section_text(result, req.section)

        # A still-empty payload is a provider DIAGNOSTIC, not a generic "too
        # short" failure (PART W): map the recorded error code (rate_limit /
        # malformed_json / empty_output …) to a TEACHER-SAFE message (PART H/I)
        # while keeping the raw detail in the diagnostic field for logs.
        if not result or not new_content or not new_content.strip():
            from ..engines.ai_provider import provider_status
            state = provider_status(provider)
            raw = (
                f"AI provider '{provider.get_name()}' returned no usable "
                f"content (state: {state}, last_error: {provider.last_error})."
            )
            logger.warning("section_regen_no_content", section=req.section,
                           provider=provider.get_name(), state=state,
                           last_error=str(provider.last_error))
            if provider.last_error == "rate_limit":
                raise _ai_error(
                    502, "AI_RATE_LIMITED",
                    "AI is busy right now. Your existing content was preserved. "
                    "Please try again in a moment.",
                    diagnostic=raw,
                )
            raise _ai_error(
                502, "AI_NO_SUGGESTION",
                "AI suggestion unavailable right now. Your existing content "
                "was preserved. You can edit it manually or try again later.",
                diagnostic=raw,
            )

        # The length floor applies to the REGENERATED SECTION text only, after
        # the structured payload was mapped (PART W) — never to the raw model
        # output, and never to unrelated fields of a valid JSON response.
        if len(new_content.strip()) < MIN_SECTION_CHARS:
            raise _ai_error(
                502, "AI_NO_SUGGESTION",
                "AI suggestion unavailable right now. Your existing content "
                "was preserved. You can edit it manually or try again later.",
                diagnostic=(
                    f"No content mapped to section '{req.section}' from a valid "
                    "provider response."
                ),
            )

        _save_enrichment_cache(db, lp.id, req.section, new_content, provider.__class__.__name__, mode_label)

        # Only a SUCCESSFUL generation consumes one lifetime AI generation.
        # Failed/empty/provider-unavailable attempts above never reach here.
        consume_ai_generation(user, db, request_id=req.request_id or None)

        log_event("section_regenerated",
                  user_id=user.id, lesson_plan_id=req.lesson_plan_id,
                  section=req.section, mode=mode_label)

        return SectionRegenerateResponse(
            section=req.section,
            previous_content=previous_content,
            new_content=new_content,
            new_activities=new_activities,
            provider=provider.get_name(),
            model=getattr(provider, 'model', 'unknown'),
            mode=mode_label,
            timestamp=datetime.utcnow().isoformat(),
            source=ContentSource.AI.value,
        )

    except HTTPException:
        # Teacher-safe provider errors keep the lesson untouched and pass
        # through unchanged (the raw cause is in the diagnostic field).
        raise
    except Exception as e:
        logger.error("section_regeneration_failed",
                     section=req.section, error=str(e), exc_info=True)
        raise _ai_error(
            500, "AI_UNAVAILABLE",
            "AI suggestion unavailable right now. Your existing content was "
            "preserved. You can edit it manually or try again later.",
            diagnostic=f"Regeneration failed: {str(e)}",
        )


@router.get("/sections")
async def list_regeneratable_sections():
    """List sections that can be regenerated."""
    return {"sections": REGENERATABLE_SECTIONS}


def _section_generation(provider, prompt: str, gen_kwargs: dict) -> dict:
    """Send the per-section rewrite prompt through the provider's channel.

    Every real provider (Gemini / Groq / OpenAI / Ollama / …) OVERRIDES
    :meth:`AIProvider.generate_structured`; those receive the curated section
    prompt verbatim — a rewrite of ONE section, never a whole-lesson
    regeneration whose unrelated fields then leak into the section. Providers
    that only implement the legacy whole-lesson call get that instead; the
    caller mines the returned lesson for the requested section.
    """
    impl = getattr(type(provider), "generate_structured", None)
    base = getattr(AIProvider, "generate_structured", None)
    if impl is not None and base is not None and impl is not base:
        return provider.generate_structured(prompt)
    return provider.generate_lesson_content(**gen_kwargs)


def _as_text_list(raw) -> list:
    """Normalize a stored list field (JSON list of str/dict) to strings."""
    import json as _json
    if not raw:
        return []
    try:
        items = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return [str(raw)]
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            out.append(it.get("description") or it.get("text") or "")
    return [x for x in out if x]


def _get_section_content(lp: LessonPlanDB, section: str) -> str:
    """Resolve current content for any regeneratable section.

    getattr-safe: sections without a dedicated column fall back to the
    closest stored field instead of raising AttributeError.
    """
    direct = getattr(lp, section, None)
    if section in ("learning_objectives", "teaching_learning_resources",
                   "essential_questions", "main_activities",
                   "learner_activities", "teacher_activities",
                   "indicators", "references", "core_competencies"):
        # JSON columns may deserialize as str (SQLite) or list (PostgreSQL).
        return "\n".join(_as_text_list(direct))
    if isinstance(direct, str):
        return direct
    if isinstance(direct, list):
        return "\n".join(_as_text_list(direct))
    fallbacks = {
        "starter_activity": "introduction",
        "reflection": "conclusion",
        "differentiation": "conclusion",
        "remediation": "assessment",
        "extension": "assessment",
        "homework": "assessment",
        "essential_questions": "learning_objectives",
    }
    if section in fallbacks:
        return _get_section_content(lp, fallbacks[section])
    return ""


def _flatten_text(value) -> str:
    """Coerce provider payload fragments (str | dict | list) to plain text."""
    import re as _re
    if value is None:
        return ""
    if isinstance(value, str):
        m = _re.search(r"```(?:json)?\s*(.*?)```", value, _re.DOTALL)
        return (m.group(1).strip() if m else value)
    if isinstance(value, dict):
        for key in ("description", "text", "content"):
            if isinstance(value.get(key), str) and value[key].strip():
                extras = " ".join(
                    str(v) for k, v in value.items()
                    if k != key and isinstance(v, str) and v.strip())
                return (value[key] + (" " + extras if extras else "")).strip()
        nested = [v for v in value.values() if isinstance(v, (str, dict, list))]
        return " ".join(_flatten_text(v) for v in nested).strip()
    if isinstance(value, list):
        return "\n".join(_flatten_text(v) for v in value).strip()
    return str(value)


def _extract_section_text(result: dict, section: str) -> str:
    """Find section text in a provider payload, unwrapping common wrappers
    (e.g. {"lesson_content": {"assessment": ...}}) and dict fragments.

    ``section`` is the LESSON-row name (e.g. ``introduction``); the provider V2
    schema uses different keys (``starter``, ``main_learning``, ``plenary``).
    The mapping in ``SECTION_TO_PROVIDER_KEYS`` (PART W) resolves the provider
    keys BEFORE the old direct/nested lookups, so a valid structured Gemini or
    Groq response is never treated as empty just because the row column name
    does not literally appear in the JSON.
    """
    if not isinstance(result, dict):
        return ""
    # 1. Provider-schema keys for this section (V2 contract).
    for key in SECTION_TO_PROVIDER_KEYS.get(section, ()):  # mapped first
        if key in result:
            text = _flatten_text(result.get(key, ""))
            if text.strip():
                return text
    # 2. Legacy literal-key payloads (older providers/tests).
    direct = _flatten_text(result.get(section, ""))
    if direct.strip():
        return direct
    nested = result.get("lesson_content")
    if isinstance(nested, dict):
        inner = _flatten_text(nested.get(section, ""))
        if inner.strip():
            return inner
    return ""


def _normalize_activity(phase, fallback_phase: str) -> Optional[dict]:
    """Map ONE provider phase fragment to a canonical main activity item.

    Providers may return an object (``{name, activity, duration_minutes,
    resources_used}``) or a bare string. Anything that carries no usable
    description (or an out-of-range duration) is dropped, never written as an
    empty/``null``/``undefined`` activity.
    """
    if isinstance(phase, dict):
        desc = phase.get("activity") or phase.get("description") or phase.get("text") or ""
        if isinstance(desc, (dict, list)):
            desc = _flatten_text(desc)
        desc = str(desc).strip()
        raw_dur = phase.get("duration_minutes")
        try:
            dur = int(raw_dur) if raw_dur is not None else None
        except (TypeError, ValueError):
            dur = None
        if dur is not None and not (MIN_ACTIVITY_MINUTES <= dur <= MAX_ACTIVITY_MINUTES):
            dur = None
        resources = phase.get("resources_used")
        if resources is None:
            resources = phase.get("resources")
        if not isinstance(resources, list):
            resources = [resources] if resources else []
        item = {
            "phase": str(phase.get("name") or phase.get("phase") or fallback_phase).upper(),
            "description": desc,
            "duration_minutes": dur,
            "resources": [str(r).strip() for r in resources if str(r).strip()],
        }
        return item if item["description"] else None
    if isinstance(phase, str) and phase.strip():
        return {
            "phase": fallback_phase,
            "description": phase.strip(),
            "duration_minutes": None,
            "resources": [],
        }
    return None


def _normalize_main_activities(result) -> List[dict]:
    """Normalize a provider payload into canonical main-learning activities.

    Canonical shape (PART X): ``[{phase, description, duration_minutes,
    resources}]``. Handles the V2 ``main_learning`` object keyed by phase, a
    list of phase objects, and a bare string. Returns ``[]`` when the provider
    produced nothing usable — the caller turns that into a teacher-safe
    failure, never a blank replacement.
    """
    if not isinstance(result, dict):
        return []
    raw = None
    for key in ("main_learning", "main_activities"):
        if result.get(key):
            raw = result[key]
            break
    if raw is None:
        nested = result.get("lesson_content")
        if isinstance(nested, dict):
            for key in ("main_learning", "main_activities"):
                if nested.get(key):
                    raw = nested[key]
                    break
    if raw is None:
        return []

    items: List[dict] = []
    if isinstance(raw, dict):
        for phase_key, phase in raw.items():
            item = _normalize_activity(phase, str(phase_key).upper())
            if item:
                items.append(item)
    elif isinstance(raw, list):
        for i, phase in enumerate(raw):
            item = _normalize_activity(phase, f"MAIN {i + 1}")
            if item:
                items.append(item)
    else:
        item = _normalize_activity(raw, "MAIN")
        if item:
            items.append(item)
    return items


def _evidence_brief(lp) -> str:
    """Layer-1 curriculum evidence for the AI prompt, with provenance.

    The AI is a REWRITE tool: it may never invent curriculum content, so it
    is handed the retrieved NaCCA exemplar row (if any). ``""`` when the
    corpus has no record for this indicator — an empty retrieval is valid and
    the prompt simply says so.
    """
    from ..curriculum.evidence import (
        EvidenceRequest, evidence_for_lesson, get_evidence_provider,
    )

    try:
        provider = get_evidence_provider()
    except Exception:
        return ""
    codes = lp.indicator_codes or []
    request = EvidenceRequest(
        subject=(lp.subject or "").strip(),
        level=(lp.class_level or "").strip(),
        indicator_code=(codes[0] if codes else "").strip(),
        content_standard_code=(lp.content_standard_code or "").strip(),
        terms=_signal_words(" ".join(lp.indicators or [])),
        source_week=lp.week_number or None,
    )
    ev = evidence_for_lesson(request, provider=provider)
    if ev is None:
        return ("No structured curriculum exemplar is on file for this "
                "indicator — do not invent one.")
    src = (ev.provenance.source_name or ev.provenance.source_type) if ev.provenance else ""
    header = f"NaCCA exemplar ({src}):" if src else "NaCCA exemplar:"
    bits = []
    if ev.learning_focus:
        bits.append(f"Learning focus: {ev.learning_focus}.")
    if ev.exemplar_activity_patterns:
        bits.append("Exemplar activities: " + "; ".join(
            ev.exemplar_activity_patterns[:3]) + ".")
    if ev.assessment_patterns:
        bits.append("Exemplar assessment: " + ev.assessment_patterns[0] + ".")
    if not bits:
        return header + " record found; no exemplar detail fields."
    return header + " " + " ".join(bits)


def _signal_words(text: str) -> List[str]:
    """Content words of the indicator text (for evidence keyword retrieval)."""
    import re as _re
    stop = {"the", "and", "for", "with", "use", "able", "learners", "learner"}
    words = [w for w in _re.findall(r"[a-z]{4,}", (text or "").lower())
             if w not in stop]
    return sorted(set(words))[:8]


def _resource_brief(lp) -> str:
    """Every resource line attached to the lesson (scheme + teacher-added)."""
    rows: List[str] = []
    for column in ("teaching_learning_resources", "source_tlrs", "other_tlrs"):
        rows.extend(_as_text_list(getattr(lp, column, None)))
    rows = [r for r in rows if r]
    if not rows:
        return "None listed."
    return "; ".join(dict.fromkeys(rows))


def _objective_brief(lp) -> str:
    return " ".join(_as_text_list(lp.learning_objectives)).strip()


def _current_approach(lp) -> str:
    """The pedagogical shape of the lesson as rendered (the pattern's visible
    result). The internal pattern id is never persisted or shown, so the AI
    receives the *structure* — it must respect it, not fight it."""
    descs = _as_text_list(lp.main_activities)
    if not descs:
        return ""
    first = descs[0].lower()
    if "worked example" in first or "teacher works through" in first:
        return "worked example followed by guided then independent practice"
    if "investigate" in first or "observe" in first:
        return "guided observation and investigation"
    if "discuss" in first:
        return "structured discussion"
    return "teacher modelling followed by learner practice"


def _json_contract(section: str) -> str:
    if section == "main_activities":
        return (
            'Return JSON: {"main_learning": {"phase1": {"activity": "...", '
            '"duration_minutes": 15}, "phase2": {...}, "phase3": {...}}} '
            "with three to five sequenced phases.")
    return f'Return JSON: {{"{section}": "the rewritten section text"}}'


def _build_section_prompt(
    lp,
    section: str,
    current_content: str,
    additional_context: str,
    rewrite_mode: str = DEFAULT_REWRITE_MODE,
) -> str:
    """Build the per-section AI rewrite prompt.

    Contract (Layer wiring): the AI receives the ORIGINAL section, the
    indicator + objective, the curriculum evidence, the subject, the
    resources, the current pedagogical approach, the teacher's instruction,
    and the WAPEF/duration/context it must NOT change. It rewrites ONE
    section's delivery wording — never the curriculum meaning.
    """
    indicators = lp.indicators or []
    indicator_line = "; ".join(
        f"{code} {text}".strip() for code, text in
        zip(lp.indicator_codes or [], indicators)) or " ".join(indicators) or "(none)"
    mode_instruction = REWRITE_MODES.get(rewrite_mode, REWRITE_MODES[DEFAULT_REWRITE_MODE])

    preserve = [
        "Keep the SAME curriculum indicator code and objective meaning — never "
        "renumber, retitle or drift from it.",
        f"Keep the SAME subject ({lp.subject}), class ({lp.class_level}) and "
        f"duration ({getattr(lp, 'duration_minutes', 60)} minutes).",
        "Keep the SAME resources listed for this lesson and the same WAPEF "
        "selections (deep hope / storyline) if the school uses them.",
        "Rewrite ONLY the delivery wording of this ONE section.",
    ]
    wapef = (lp.wapef_deep_hope or "").strip()
    if wapef:
        preserve.append(f"WAPEF deep hope to honour: {wapef}")

    return f"""You are a Ghanaian educator rewriting ONE section of a real lesson plan.

{mode_instruction}

SUBJECT: {lp.subject}
CLASS: {lp.class_level}
STRAND / SUB-STRAND: {lp.strand} / {lp.sub_strand}
INDICATOR: {indicator_line}
OBJECTIVE: {_objective_brief(lp) or current_content[:120]}
RESOURCES: {_resource_brief(lp)}
TEACHING APPROACH: {_current_approach(lp)}

CURRICULUM EVIDENCE:
{_evidence_brief(lp)}

ORIGINAL '{section}' SECTION (rewrite THIS):
{current_content or '(empty)'}

{f'TEACHER INSTRUCTION: {additional_context}' if additional_context else ''}

You MUST:
{chr(10).join('- ' + p for p in preserve)}
- Use concrete local Ghanaian examples and materials.
- No ICT, projector or smartboard references.
- Sound like a teacher's plan, not a textbook.

{_json_contract(section)}
"""


class EnrichLessonRequest(BaseModel):
    lesson_plan_id: str
    ai_mode: str = "ollama"
    #: Export template the enrichment is for. Lesson rows do not persist a
    #: template id, so the caller states it; empty means the approved
    #: organizational format.
    template_id: str = ""
    #: Client-generated id for THIS user action (idempotent consumption).
    request_id: str = ""


def _existing_texts(raw) -> list:
    import json as _json
    if not raw:
        return []
    try:
        items = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            out.append(it.get("description") or it.get("text") or "")
    return [x for x in out if x]


def _append_new(existing: list, new_items: list) -> list:
    """Append items not already present (substring-aware), preserving order."""
    blob = "\n".join(existing)
    out = list(existing)
    for item in new_items or []:
        if item and item.strip() and item.strip() not in blob:
            out.append(item.strip())
            blob += "\n" + item.strip()
    return out


@router.post("/enrich-lesson")
async def enrich_lesson(
    req: EnrichLessonRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Enrich a lesson's activity-family fields with structured AI output.

    Pipeline: deterministic lesson → provider (template schema prompt) →
    server-side JSON validation → merge into stored fields. Curriculum and
    metadata columns are NEVER written by AI. Deterministic data is preserved
    on any AI failure.
    """
    from ..engines.approved_template import (
        APPROVED_SYSTEM_PROMPT, validate_approved_lesson_json,
    )
    from ..engines.official_ges_levels import spec_for_template_id
    from ..engines.official_ges_template import (
        ges_system_prompt, validate_ges_lesson_json,
    )
    lp = db.query(LessonPlanDB).filter(
        LessonPlanDB.id == req.lesson_plan_id,
        LessonPlanDB.owner_id == user.id,
    ).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson plan not found")

    _require_ai_entitlement(user, db)

    mode = (req.ai_mode or "").strip().lower()
    if mode not in REAL_AI_MODES:
        # BASIC/ENHANCED may still resolve to a configured real provider.
        if mode in ("basic", "enhanced", "off"):
            mode = resolve_provider_mode(mode)
        if mode not in REAL_AI_MODES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Enrichment requires a real AI provider mode "
                    "(e.g. gemini, groq, ollama)."
                ),
            )
    provider = get_provider(mode)
    if not provider or not provider.is_available():
        from ..engines.ai_provider import provider_status
        state = provider_status(provider)
        raise HTTPException(
            status_code=503,
            detail=(
                f"AI provider '{mode}' is not available (state: {state}). "
                "Deterministic lesson data is unchanged — configure a provider "
                "or start local Ollama to enable AI enrichment."
            ),
        )
    gen = getattr(provider, "generate_structured", None)
    if gen is None:
        raise HTTPException(
            status_code=503,
            detail="This provider does not support structured enrichment.",
        )

    # Every official GES/NaCCA form names its phases differently (and frames the
    # level differently) from the approved organizational format, while both
    # renderers read the same stored columns.
    ges_spec = spec_for_template_id(req.template_id)
    if ges_spec is not None:
        system_prompt = ges_system_prompt(ges_spec)
        phase_names = list(ges_spec.phase_names)
        validator = validate_ges_lesson_json
    else:
        system_prompt = APPROVED_SYSTEM_PROMPT
        phase_names = ["PHASE 1: STARTER", "PHASE 2: NEW LEARNING", "PHASE 3: REFLECTION"]
        validator = validate_approved_lesson_json

    prompt = (
        f"{system_prompt}\n"
        f"Lesson context (reference only, do not repeat verbatim):\n"
        f"Subject: {lp.subject} | Class: {lp.class_level} | "
        f"Strand: {lp.strand} | Indicators: {', '.join((lp.indicators or [])[:3])}\n"
        f"Required phase names: {', '.join(phase_names)}\n"
        f"Current topic: {lp.lesson_topic or ''}\n"
    )
    raw = gen(prompt)
    ok, validated = validator(raw)
    if not ok:
        raw = gen(prompt)  # single bounded retry
        ok, validated = validator(raw)
    if not ok:
        logger.error("enrich_invalid_output", errors=str(validated)[:300])
        raise HTTPException(
            status_code=500,
            detail="AI returned invalid lesson data. Deterministic lesson preserved.",
        )

    written = []
    import json as _json

    def _load_list(col):
        return _existing_texts(col)

    # Phases → teacher/learner activities + resources (append, deduped)
    for ph in validated.get("phases", []):
        pname = (ph.get("name") or "").strip() or "PHASE"
        for act in ph.get("teacher_activities", []) or []:
            cur = _load_list(lp.teacher_activities)
            if act.strip() and act.strip() not in "\n".join(cur):
                cur_raw = _json.loads(lp.teacher_activities) if isinstance(lp.teacher_activities, str) else (lp.teacher_activities or [])
                cur_raw = cur_raw if isinstance(cur_raw, list) else []
                cur_raw.append({"phase": pname, "description": act.strip(), "source": "ai"})
                lp.teacher_activities = cur_raw
                written.append(f"teacher:{pname}")
        for act in ph.get("learner_activities", []) or []:
            cur = _load_list(lp.learner_activities)
            if act.strip() and act.strip() not in "\n".join(cur):
                cur_raw = _json.loads(lp.learner_activities) if isinstance(lp.learner_activities, str) else (lp.learner_activities or [])
                cur_raw = cur_raw if isinstance(cur_raw, list) else []
                cur_raw.append({"phase": pname, "description": act.strip(), "source": "ai"})
                lp.learner_activities = cur_raw
                written.append(f"learner:{pname}")
        res = _append_new(_load_list(lp.teaching_learning_resources), ph.get("resources", []) or [])
        if len(res) != len(_load_list(lp.teaching_learning_resources)):
            lp.teaching_learning_resources = res
            written.append("resources")

    # Assessment / reflection / vocabulary (append-only, never overwrite)
    if validated.get("assessment"):
        combo = ((lp.assessment or "") + "\n" + "\n".join(validated["assessment"])).strip()
        if combo != (lp.assessment or "").strip():
            # only append items not already present
            fresh = [a for a in validated["assessment"] if a and a.strip() not in (lp.assessment or "")]
            if fresh:
                lp.assessment = ((lp.assessment or "") + "\n" + "\n".join(fresh)).strip()
                written.append("assessment")
    if validated.get("reflection", "").strip() and validated["reflection"].strip() not in (lp.conclusion or ""):
        lp.conclusion = ((lp.conclusion or "") + "\n" + validated["reflection"].strip()).strip()
        written.append("reflection")
    for item in validated.get("new_words", []) or []:
        cur = _load_list(lp.keywords)
        if item.strip() and item.strip() not in cur:
            cur.append(item.strip())
            lp.keywords = cur
            written.append("new_words")
    for item in validated.get("references", []) or []:
        cur = _load_list(lp.references)
        if item.strip() and item.strip() not in cur:
            cur.append(item.strip())
            lp.references = cur
            written.append("references")
    for item in validated.get("core_competencies", []) or []:
        cur = _load_list(lp.core_competencies)
        if item.strip() and item.strip() not in cur:
            cur.append(item.strip())
            lp.core_competencies = cur
            written.append("core_competencies")

    lp.teacher_edited = True
    _save_enrichment_cache(db, lp.id, "enrich-lesson", _json.dumps(validated)[:2000],
                           provider.__class__.__name__, mode)
    # One successful generation consumes one lifetime AI generation.
    consume_ai_generation(user, db, request_id=req.request_id or None)
    log_event("lesson_enriched", user_id=user.id, lesson_plan_id=lp.id,
              written=written)
    db.commit()
    db.refresh(lp)
    return {"lesson_plan_id": lp.id, "written": written,
            "provider": provider.get_name(), "mode": mode}


def _save_enrichment_cache(db, lesson_plan_id: str, section: str, content: str, provider: str, mode: str):
    cache = AIEnrichmentCacheDB(
        id=generate_id(),
        lesson_plan_id=lesson_plan_id,
        section=section,
        content=content,
        provider=provider,
        created_at=datetime.utcnow(),
    )
    db.add(cache)
    db.commit()

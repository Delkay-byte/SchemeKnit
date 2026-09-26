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
from ..engines.ai_provider import get_provider, resolve_provider_mode, NAMED_PROVIDERS
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
    "essential_questions", "learning_objectives",
    "teaching_learning_resources", "previous_knowledge",
]

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
    "essential_questions": ("essential_questions", "learning_objectives"),
    "learning_objectives": ("learning_objectives",),
    "teaching_learning_resources": ("teaching_learning_resources", "resources"),
    "previous_knowledge": ("previous_knowledge", "teacher_notes"),
}

#: Minimum usable length for a REGENERATED SECTION (not the whole response).
#: Applied AFTER the provider payload is parsed and mapped; a valid structured
#: JSON response is never rejected because some OTHER field is short.
MIN_SECTION_CHARS = 10


class SectionRegenerateRequest(BaseModel):
    lesson_plan_id: str
    section: str
    ai_mode: str = "BASIC"
    additional_context: str = ""
    #: Client-generated id for THIS user action. Used to make the lifetime
    #: AI-generation consumption idempotent across duplicate submissions.
    request_id: str = ""


class SectionRegenerateResponse(BaseModel):
    section: str
    previous_content: str
    new_content: str
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
        raise HTTPException(
            status_code=503,
            detail=(
                f"AI provider '{resolved}' is not available (state: {state}). "
                "No real AI provider is configured on the server. Lessons and "
                "their deterministic content are unchanged — configure a "
                "provider (Gemini, Groq, OpenAI) or start local Ollama to use "
                "AI suggestions."
            ),
        )

    try:
        prompt = _build_section_prompt(lp, req.section, previous_content, req.additional_context)
        gen_kwargs = dict(
            indicator=lp.indicators[0] if lp.indicators else "",
            strand=lp.strand or "",
            sub_strand=lp.sub_strand or "",
            content_standard=lp.content_standard or "",
        )
        if provider.get_name() == "ollama":
            # Section-targeted prompt: smaller, faster, section-relevant output.
            gen_kwargs["section"] = req.section
        result = provider.generate_lesson_content(**gen_kwargs)
        new_content = _extract_section_text(result, req.section)

        # One bounded retry for empty/short results BEFORE surfacing a provider
        # diagnostic: local models occasionally return empty/truncated output,
        # and a transient failure should be retried, not reported.
        if (not new_content or len(new_content.strip()) < MIN_SECTION_CHARS) and provider.get_name() == "ollama":
            logger.warning("ai_empty_retry", section=req.section)
            result = provider.generate_lesson_content(**gen_kwargs)
            new_content = _extract_section_text(result, req.section)

        # A still-empty payload is a provider DIAGNOSTIC, not a generic "too
        # short" failure (PART W): surface the recorded error code (rate_limit /
        # malformed_json / empty_output …) through the normal error contract.
        if not result or not new_content or not new_content.strip():
            from ..engines.ai_provider import provider_status
            state = provider_status(provider)
            detail = {
                "rate_limit": (
                    f"AI provider '{provider.get_name()}' was rate-limited. "
                    "Please retry in a moment. Previous content preserved."
                ),
                "malformed_json": (
                    f"AI provider '{provider.get_name()}' returned an unparseable "
                    "response. Previous content preserved."
                ),
                "empty_output": (
                    f"AI provider '{provider.get_name()}' returned an empty "
                    "response. Previous content preserved."
                ),
            }.get(provider.last_error,
                  f"AI provider '{provider.get_name()}' returned no usable content "
                  f"(state: {state}). Previous content preserved.")
            raise HTTPException(status_code=502, detail=detail)

        # The length floor applies to the REGENERATED SECTION text only, after
        # the structured payload was mapped (PART W) — never to the raw model
        # output, and never to unrelated fields of a valid JSON response.
        if len(new_content.strip()) < MIN_SECTION_CHARS:
            raise ValueError(
                f"The provider did not return usable text for section "
                f"'{req.section}' (model output was a valid response, but no "
                f"content mapped to this section)."
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
            provider=provider.get_name(),
            model=getattr(provider, 'model', 'unknown'),
            mode=mode_label,
            timestamp=datetime.utcnow().isoformat(),
            source=ContentSource.AI.value,
        )

    except HTTPException:
        # Surfaced provider diagnostics (rate limit, empty output) keep the
        # lesson untouched and pass through unchanged.
        raise
    except Exception as e:
        logger.error("section_regeneration_failed",
                     section=req.section, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Regeneration failed: {str(e)}. Previous content preserved."
        )


@router.get("/sections")
async def list_regeneratable_sections():
    """List sections that can be regenerated."""
    return {"sections": REGENERATABLE_SECTIONS}


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


def _build_section_prompt(lp, section: str, current_content: str, additional_context: str) -> str:
    return f"""You are a Ghanaian educator. Regenerate the '{section}' section of this lesson plan.

Subject: {lp.subject}
Class: {lp.class_level}
Topic: {lp.strand} / {lp.sub_strand}
Content Standard: {lp.content_standard}

Current content:
{current_content or '(empty)'}

{f'Additional context: {additional_context}' if additional_context else ''}

Return ONLY the regenerated content for the '{section}' section.
Use local Ghanaian examples and materials.
No ICT/projector/smartboard references.
Appropriate for {lp.class_level} students.
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

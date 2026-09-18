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
from ..engines.ai_provider import get_provider
from ..entitlements import require_ai_entitlement
from ..logging_config import get_logger, log_event

router = APIRouter()
logger = get_logger()

REAL_AI_MODES = ("ollama", "gemini", "openai", "minimax")


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


class SectionRegenerateRequest(BaseModel):
    lesson_plan_id: str
    section: str
    ai_mode: str = "BASIC"
    additional_context: str = ""


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

    # Local-provider modes bypass the OFF/BASIC/ENHANCED enum (which resolve
    # to the deterministic Mock provider). Anything else falls back to BASIC.
    if (req.ai_mode or "").lower() == "ollama":
        mode_label = "ollama"
        provider = get_provider("ollama")
    else:
        ai_mode = AIMode(req.ai_mode) if req.ai_mode in [m.value for m in AIMode] else AIMode.BASIC
        mode_label = ai_mode.value
        provider = get_provider(ai_mode.value)

    if not provider or not provider.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI provider not available. Please try again later or use AI OFF mode."
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
        if (not new_content or len(new_content.strip()) < 10) and provider.get_name() == "ollama":
            # One retry: local models occasionally return empty/truncated output.
            # Bounded (single retry) so failures stay fast and controlled.
            logger.warning("ai_empty_retry", section=req.section)
            result = provider.generate_lesson_content(**gen_kwargs)
            new_content = _extract_section_text(result, req.section)

        if not new_content or len(new_content.strip()) < 10:
            raise ValueError("AI response too short or empty")

        _save_enrichment_cache(db, lp.id, req.section, new_content, provider.__class__.__name__, mode_label)

        log_event("section_regenerated",
                  user_id=user.id, lesson_plan_id=req.lesson_plan_id,
                  section=req.section, mode=mode_label)

        return SectionRegenerateResponse(
            section=req.section,
            previous_content=previous_content,
            new_content=new_content,
            provider=provider.__class__.__name__,
            model=getattr(provider, 'model', 'unknown'),
            mode=mode_label,
            timestamp=datetime.utcnow().isoformat(),
            source=ContentSource.AI.value,
        )

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
    (e.g. {"lesson_content": {"assessment": ...}}) and dict fragments."""
    if not isinstance(result, dict):
        return ""
    direct = _flatten_text(result.get(section, ""))
    if direct.strip():
        return direct
    nested = result.get("lesson_content")
    if isinstance(nested, dict):
        inner = _flatten_text(nested.get(section, ""))
        if inner.strip():
            return inner
    return _flatten_text(result.get("introduction", ""))


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

    mode = (req.ai_mode or "").lower()
    if mode not in REAL_AI_MODES:
        raise HTTPException(
            status_code=400,
            detail="Enrichment requires a real AI provider mode (e.g. ollama).",
        )
    provider = get_provider(mode)
    if not provider or not provider.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI provider not available. Deterministic lesson data is unchanged.",
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
    log_event("lesson_enriched", user_id=user.id, lesson_plan_id=lp.id,
              written=written)
    db.commit()
    db.refresh(lp)
    return {"lesson_plan_id": lp.id, "written": written,
            "provider": provider.__class__.__name__, "mode": mode}


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

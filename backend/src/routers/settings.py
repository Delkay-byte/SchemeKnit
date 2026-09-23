"""
SchemeKnit Settings Router

Teacher-facing settings with persistence.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..auth import get_current_user, get_optional_user
from ..database import User
from ..service import data_service
from ..models import (
    Subject, ClassLevel, Holiday, AIMode, TemplateType, EducationalLevel,
    CLASS_LEVEL_TO_EDUCATIONAL_LEVEL, CLASS_LEVEL_SUBJECTS,
    subjects_for_class_level,
)

router = APIRouter()


class HolidayRequest(BaseModel):
    name: str
    date: str
    is_recurring: bool = False
    description: str = ""


class PreferencesRequest(BaseModel):
    default_class_level: Optional[str] = None
    default_subject: Optional[str] = None
    default_lessons_per_week: Optional[int] = None
    default_lesson_duration: Optional[int] = None
    default_template: Optional[str] = None
    default_school_name: Optional[str] = None
    ai_mode: Optional[str] = None


@router.get("/holidays")
async def list_holidays(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    holidays = data_service.list_holidays(db, user.id)
    global_holidays = data_service.list_holidays(db, None)
    all_holidays = global_holidays + holidays
    return {
        "holidays": [
            {
                "id": h.id,
                "name": h.name,
                "date": h.date.isoformat() if hasattr(h.date, 'isoformat') else str(h.date),
                "is_recurring": h.is_recurring,
                "description": h.description,
            }
            for h in all_holidays
        ]
    }


@router.post("/holidays")
async def add_holiday(
    req: HolidayRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    from datetime import date as date_type
    try:
        parts = req.date.split("-")
        holiday_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    holiday = Holiday(
        name=req.name,
        date=holiday_date,
        is_recurring=req.is_recurring,
        description=req.description,
    )
    db_holiday = data_service.create_holiday(db, holiday, user.id)
    return {
        "id": db_holiday.id,
        "name": db_holiday.name,
        "date": db_holiday.date.isoformat(),
        "is_recurring": db_holiday.is_recurring,
    }


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    deleted = data_service.delete_holiday(db, holiday_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"message": "Holiday deleted"}


@router.get("/subjects")
async def list_subjects(level: Optional[str] = None):
    """Subjects available, optionally scoped to a class level.

    Without ``level`` the full catalogue is returned (backwards compatible).
    With ``level`` (e.g. ``?level=KG 1`` or ``?level=SHS 2``) only the subjects
    that belong to that level are returned — the level-aware availability the
    product requires, driven by the canonical taxonomy.
    """
    subjects = subjects_for_class_level(level) if level else list(Subject)
    return {"subjects": [s.value for s in subjects], "level": level or None}


@router.get("/subjects/by-level")
async def list_subjects_by_level():
    """Canonical LEVEL → AVAILABLE SUBJECTS map (single source of truth).

    The UI reads this instead of duplicating subject definitions per component.
    """
    return {
        "levels": [
            {
                "class_level": cl.value,
                "educational_level": CLASS_LEVEL_TO_EDUCATIONAL_LEVEL[cl].value,
                "subjects": [s.value for s in subjects],
            }
            for cl, subjects in CLASS_LEVEL_SUBJECTS.items()
        ]
    }


@router.get("/class-levels")
async def list_class_levels():
    return {"class_levels": [c.value for c in ClassLevel]}


@router.get("/educational-levels")
async def list_educational_levels():
    return {
        "educational_levels": [
            {"value": e.value, "label": e.value}
            for e in EducationalLevel
        ]
    }


@router.get("/template-types")
async def list_template_types():
    return {
        "template_types": [
            {"value": t.value, "label": t.value.replace("-", " ").title()}
            for t in TemplateType
        ]
    }


@router.get("/ai-modes")
async def list_ai_modes():
    """AI mode choices for the generate screen.

    OFF/BASIC/ENHANCED are the teacher-facing switches. Named providers are
    included so section regeneration / enrichment can target a specific
    backend without exposing secrets or model IDs.
    """
    named = [
        {"value": "gemini", "label": "Gemini"},
        {"value": "groq", "label": "Groq"},
        {"value": "ollama", "label": "Ollama (local)"},
        {"value": "openai", "label": "OpenAI"},
        {"value": "opencode-zen", "label": "OpenCode Zen"},
    ]
    return {
        "ai_modes": [
            {"value": m.value, "label": m.value.replace("_", " ").title()}
            for m in AIMode
        ] + named,
    }


@router.get("/ai-status")
async def ai_status(ai_mode: str = "OFF"):
    """Resolve and report the ACTUAL AI mode / provider for a requested mode.

    The UI must be able to show what will actually happen — never a label that
    disagrees with backend behaviour. This reports:
      mode        — the teacher-facing mode that was requested (OFF/BASIC/ENHANCED)
      active      — whether a real provider will be used
      provider    — the resolved provider name (or null)
      provider_key— the provider key (or null)
      state       — provider_status(): CONFIGURED / MISSING_KEY / …
      reason      — a short, secret-free explanation when AI is inactive
    Secrets, keys and model IDs are never returned.
    """
    from ..engines.ai_provider import (
        get_provider, resolve_provider_mode, provider_status, NAMED_PROVIDERS,
    )

    requested = (ai_mode or "OFF").strip()
    if requested.upper() == "OFF":
        return {
            "mode": "OFF", "active": False, "provider": None,
            "provider_key": None, "state": "OFF",
            "reason": "AI is off — lessons come from the deterministic engine.",
        }

    resolved = resolve_provider_mode(requested)
    if resolved == "OFF":
        return {
            "mode": requested, "active": False, "provider": None,
            "provider_key": None, "state": "OFF",
            "reason": "AI is off — lessons come from the deterministic engine.",
        }
    provider = get_provider(resolved)
    available = bool(provider and provider.is_available())
    state = provider_status(provider)
    reason = None
    if not available:
        reason = (
            f"No usable AI provider is configured for mode '{requested}'. "
            "Lessons will be generated deterministically. Configure a provider "
            "key (Gemini, Groq, OpenAI) or start a local Ollama server to enable AI."
        )
    return {
        "mode": requested,
        "active": available,
        "provider": provider.get_name() if provider else None,
        "provider_key": resolved if resolved in NAMED_PROVIDERS else None,
        "state": state,
        "reason": reason,
    }


@router.get("/teaching-days")
async def list_teaching_days():
    return {
        "teaching_days": [
            {"value": 0, "label": "Monday"},
            {"value": 1, "label": "Tuesday"},
            {"value": 2, "label": "Wednesday"},
            {"value": 3, "label": "Thursday"},
            {"value": 4, "label": "Friday"},
        ]
    }


@router.get("/preferences")
async def get_preferences(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    prefs = data_service.get_preferences(db, user.id)
    if not prefs:
        return {
            "default_class_level": "Basic 9",
            "default_subject": "Science",
            "default_lessons_per_week": 3,
            "default_lesson_duration": 60,
            "default_template": "GES-style",
            "default_school_name": user.school_name or "",
            "ai_mode": "OFF",
        }
    return {
        "default_class_level": prefs.default_class_level,
        "default_subject": prefs.default_subject,
        "default_lessons_per_week": prefs.default_lessons_per_week,
        "default_lesson_duration": prefs.default_lesson_duration,
        "default_template": prefs.default_template,
        "default_school_name": prefs.default_school_name,
        "ai_mode": prefs.ai_mode,
    }


@router.put("/preferences")
async def update_preferences(
    req: PreferencesRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    prefs = data_service.upsert_preferences(db, user.id, **updates)
    return {
        "default_class_level": prefs.default_class_level,
        "default_subject": prefs.default_subject,
        "default_lessons_per_week": prefs.default_lessons_per_week,
        "default_lesson_duration": prefs.default_lesson_duration,
        "default_template": prefs.default_template,
        "default_school_name": prefs.default_school_name,
        "ai_mode": prefs.ai_mode,
    }

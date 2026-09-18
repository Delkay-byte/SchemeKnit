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
from ..models import Subject, ClassLevel, Holiday, AIMode, TemplateType, EducationalLevel

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
async def list_subjects():
    return {"subjects": [s.value for s in Subject]}


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
    return {
        "ai_modes": [
            {"value": m.value, "label": m.value.replace("_", " ").title()}
            for m in AIMode
        ]
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

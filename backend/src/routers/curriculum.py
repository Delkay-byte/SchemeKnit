"""
SchemeKnit Curriculum Router

Production endpoints for curriculum validation and approval.
"""

from fastapi import APIRouter, HTTPException, Depends

from ..database import get_db
from ..auth import get_current_user, require_teacher_workflow
from ..database import User
from ..service import data_service
from ..models import WeekType, ValidationSeverity

router = APIRouter()


@router.get("/{scheme_id}/validate")
async def validate_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        if data_service.scheme_exists(db, scheme_id):
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this scheme",
            )
        raise HTTPException(status_code=404, detail="Scheme not found")

    issues = []
    if not scheme_db.subject:
        issues.append({"severity": "error", "field": "subject", "message": "Subject not detected"})
    if not scheme_db.class_level:
        issues.append({"severity": "error", "field": "class_level", "message": "Class level not detected"})

    instruction_weeks = [w for w in scheme_db.weeks if w.week_type == "instruction"]
    if not instruction_weeks:
        issues.append({"severity": "warning", "field": "weeks", "message": "No instructional weeks found"})

    total_indicators = sum(len(w.indicators or []) for w in instruction_weeks)
    if total_indicators == 0:
        issues.append({"severity": "warning", "field": "indicators", "message": "No curriculum indicators found"})

    is_valid = not any(i["severity"] == "error" for i in issues)

    return {
        "is_valid": is_valid,
        "issues": issues,
        "summary": {
            "total_weeks": len(scheme_db.weeks),
            "instruction_weeks": len(instruction_weeks),
            "total_indicators": total_indicators,
            "subject": scheme_db.subject,
            "class_level": scheme_db.class_level,
        }
    }


@router.post("/{scheme_id}/approve")
async def approve_scheme(
    scheme_id: str,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    scheme = data_service.update_scheme_status(db, scheme_id, user.id, "approved")
    if not scheme:
        if data_service.scheme_exists(db, scheme_id):
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this scheme",
            )
        raise HTTPException(status_code=404, detail="Scheme not found")
    return {"message": "Scheme approved for lesson plan generation"}


@router.get("/{scheme_id}/summary")
async def get_scheme_summary(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        if data_service.scheme_exists(db, scheme_id):
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this scheme",
            )
        raise HTTPException(status_code=404, detail="Scheme not found")

    instruction_weeks = [w for w in scheme_db.weeks if w.week_type == "instruction"]
    special_weeks = [w for w in scheme_db.weeks if w.week_type != "instruction"]
    strands = set(w.strand for w in scheme_db.weeks if w.strand)
    total_cs = sum(len(w.content_standards or []) for w in scheme_db.weeks)
    total_indicators = sum(len(w.indicators or []) for w in scheme_db.weeks)

    return {
        "subject": scheme_db.subject,
        "class_level": scheme_db.class_level,
        "term": scheme_db.term,
        "academic_year": scheme_db.academic_year,
        "total_weeks": len(scheme_db.weeks),
        "instruction_weeks": len(instruction_weeks),
        "special_weeks": len(special_weeks),
        "unique_strands": len(strands),
        "total_content_standards": total_cs,
        "total_indicators": total_indicators,
    }

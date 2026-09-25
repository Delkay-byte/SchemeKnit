"""
Weekly class-teacher plan API (Approved WAPEF Basic 1-3 Plan).

One weekly plan for Basic 1-3 holds one section per subject, each with its own
metadata and a DAYS | PHASE 1: STARTER | PHASE 2: MAIN | PHASE 3: REFLECTION
table. This router exposes the class-teacher workflow:

    POST   /weekly-plans/preview   build the plan (subjects + teaching days)
    POST   /weekly-plans           persist it
    GET    /weekly-plans           list the teacher's weekly plans
    GET    /weekly-plans/{id}      fetch one (review/reload)
    PUT    /weekly-plans/{id}      edit it (subject/day isolation enforced)
    POST   /weekly-plans/{id}/export/docx
    POST   /weekly-plans/{id}/export/pdf

Basic 4-JHS keeps the subject-teacher Approved WAPEF Plan and never lands here:
the class boundary is decided in one place (``wapef_template_for_class``) and
this router refuses a class outside the Basic 1-3 band.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import User, get_db
from ..engines.wapef_basic13_template import (
    TEMPLATE_ID,
    WEEK_DAYS,
    DAY_OPTIONS,
    wapef_routing,
)
from ..engines.weekly_plan_engine import (
    build_weekly_plan,
    plan_validation_issues,
    teaching_days_summary,
)
from ..logging_config import log_event
from ..models import (
    ClassLevel,
    WeeklyClassPlan,
    WeeklyPlanRequest,
)

router = APIRouter()

WEEKLY_PLANS_DIR = Path("exports/weekly-plans")


# ── Persistence ───────────────────────────────────────────────────────────────

_PLANS_FILE = Path("teachflow_data/weekly_plans.json")


def _load_store() -> Dict[str, Any]:
    """The weekly-plan store (created on first use).

    A lightweight, ownership-scoped JSON store: the weekly class plan is a
    single aggregate document, so a row-per-field relational split buys nothing
    here. Every record carries owner_id and every read/write filters on it.
    """
    if not _PLANS_FILE.is_file():
        return {"plans": []}
    try:
        return json.loads(_PLANS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"plans": []}


def _save_store(store: Dict[str, Any]) -> None:
    _PLANS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PLANS_FILE.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")


def _plan_record(plan: WeeklyClassPlan, owner_id: str) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "owner_id": owner_id,
        "class_level": plan.class_level.value if hasattr(plan.class_level, "value")
                       else str(plan.class_level),
        "week_number": plan.week_number,
        "term": plan.term,
        "academic_year": plan.academic_year,
        "template_id": plan.template_id,
        "school_name": plan.school_name,
        "teacher_name": plan.teacher_name,
        "created_date": plan.created_date.isoformat(),
        "updated_date": plan.updated_date.isoformat(),
        "plan": plan.model_dump(mode="json"),
    }


def _get_owned_record(db_plan: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if db_plan.get("owner_id") != user_id:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    return db_plan


# ── Class boundary ────────────────────────────────────────────────────────────

def _require_basic13(class_level: ClassLevel) -> None:
    """Only Basic 1-3 may build a class-teacher weekly plan here.

    The boundary is decided by the shared routing rule, never ad hoc: Basic 4
    through JHS stay on the subject-teacher Approved WAPEF Plan.
    """
    routing = wapef_routing(class_level)
    if routing["template_id"] != TEMPLATE_ID:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{routing['class_level'] or 'this class'} uses the "
                f"{routing['template_name']} (subject-teacher model). The weekly "
                "class-teacher plan is for Basic 1-3 only."
            ),
        )


def _scheme_ir(db, user_id: str, scheme_id: str) -> Dict[str, Any]:
    """One uploaded scheme as {weeks, subject, class_level} for the engine.

    Reuses the existing normalized curriculum IR — no separate parser.
    """
    from ..service import data_service

    scheme_db = data_service.get_scheme(db, scheme_id, user_id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    scheme = data_service.scheme_to_model(scheme_db)
    return {
        "weeks": list(scheme.weeks or []),
        "subject": scheme.subject,
        "class_level": scheme.class_level,
        "filename": scheme.filename,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/routing/{class_level}")
async def get_weekly_routing(
    class_level: str,
    user: User = Depends(get_current_user),
):
    """Which WAPEF planning model applies to this class (Basic 1-3 boundary)."""
    try:
        level = ClassLevel(class_level)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Unknown class level: {class_level}")
    return wapef_routing(level)


@router.get("/day-options")
async def get_day_options(user: User = Depends(get_current_user)):
    """The teaching-day options the teacher assigns per subject."""
    return {"days": DAY_OPTIONS, "week_days": list(WEEK_DAYS)}


@router.post("/preview")
async def preview_weekly_plan(
    request: WeeklyPlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Build a weekly class plan without persisting it.

    The teacher's teaching-day selections are authoritative; subjects with no
    selection fall back to the term's own teaching days (never a hard-coded
    Monday-Friday subject timetable).
    """
    _require_basic13(request.class_level)
    if not request.subjects:
        raise HTTPException(status_code=400, detail="Select at least one subject scheme.")

    schemes_by_id = {
        s.scheme_id: _scheme_ir(db, user.id, s.scheme_id)
        for s in request.subjects
    }
    prefs = data_service_get_preferences(db, user.id)
    context = {
        "owner_id": user.id,
        "school_name": (prefs.school_name if prefs else None),
        "teacher_name": user.full_name or None,
        "template_id": TEMPLATE_ID,
    }
    plan = build_weekly_plan(request, schemes_by_id, context)
    return {
        "plan": plan.model_dump(mode="json"),
        "teaching_days": teaching_days_summary(plan),
        "validation_issues": plan_validation_issues(plan),
    }


@router.post("")
async def create_weekly_plan(
    request: WeeklyPlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist one weekly class plan (review → save → reload → edit → export)."""
    _require_basic13(request.class_level)
    if not request.subjects:
        raise HTTPException(status_code=400, detail="Select at least one subject scheme.")

    schemes_by_id = {
        s.scheme_id: _scheme_ir(db, user.id, s.scheme_id)
        for s in request.subjects
    }
    prefs = data_service_get_preferences(db, user.id)
    context = {
        "owner_id": user.id,
        "school_name": (prefs.school_name if prefs else None),
        "teacher_name": user.full_name or None,
        "template_id": TEMPLATE_ID,
    }
    plan = build_weekly_plan(request, schemes_by_id, context)
    issues = plan_validation_issues(plan)
    if issues:
        raise HTTPException(status_code=400, detail="; ".join(issues))

    store = _load_store()
    store["plans"].append(_plan_record(plan, user.id))
    _save_store(store)
    log_event("weekly_plan_created", user_id=user.id, weekly_plan_id=plan.id)
    return {"plan": plan.model_dump(mode="json"), "id": plan.id}


@router.get("")
async def list_weekly_plans(
    user: User = Depends(get_current_user),
):
    """The teacher's weekly class plans (newest first)."""
    store = _load_store()
    plans = [
        {
            "id": p["id"],
            "class_level": p["class_level"],
            "week_number": p["week_number"],
            "term": p["term"],
            "academic_year": p["academic_year"],
            "template_id": p["template_id"],
            "school_name": p["school_name"],
            "subjects": [s.get("subject", "") for s in (p["plan"].get("subjects") or [])],
            "created_date": p["created_date"],
            "updated_date": p["updated_date"],
        }
        for p in store["plans"]
        if p.get("owner_id") == user.id
    ]
    plans.sort(key=lambda p: p["created_date"], reverse=True)
    return {"plans": plans}


@router.get("/{plan_id}")
async def get_weekly_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
):
    """Fetch one weekly plan (reload after save, with full day-plan content)."""
    store = _load_store()
    record = next((p for p in store["plans"] if p["id"] == plan_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    record = _get_owned_record(record, user.id)
    return {"plan": record["plan"]}


@router.put("/{plan_id}")
async def update_weekly_plan(
    plan_id: str,
    updates: Dict[str, Any],
    user: User = Depends(get_current_user),
):
    """Edit a saved weekly plan.

    Edits are applied at SUBJECT + DAY granularity and subjects are isolated:
    updating one subject's metadata or one day's starter/main/reflection never
    touches another subject or another day.
    """
    store = _load_store()
    record = next((p for p in store["plans"] if p["id"] == plan_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    record = _get_owned_record(record, user.id)

    plan = WeeklyClassPlan.model_validate(record["plan"])
    subject_updates = updates.get("subjects") or []
    for patch in subject_updates:
        index = patch.get("index")
        if index is None or not (0 <= index < len(plan.subjects)):
            continue
        subject = plan.subjects[index]
        metadata = patch.get("metadata")
        if metadata:
            new_meta = subject.metadata.model_copy(update={
                k: v for k, v in metadata.items()
                if k in subject.metadata.model_fields
            })
            subject.metadata = new_meta
        day_updates = patch.get("day_plans") or []
        for day_patch in day_updates:
            day_index = day_patch.get("index")
            if day_index is None or not (0 <= day_index < len(subject.day_plans)):
                continue
            current = subject.day_plans[day_index]
            fields = {
                k: v for k, v in day_patch.items()
                if k in ("days", "day_label", "starter", "reflection",
                         "main_activities", "focus_indicators", "resources",
                         "lesson_date", "period")
            }
            if "main_activities" in fields and isinstance(fields["main_activities"], list):
                fields["main_activities"] = [
                    {"description": a} if isinstance(a, str) else a
                    for a in fields["main_activities"]
                ]
            subject.day_plans[day_index] = current.model_copy(update=fields)
        if patch.get("teaching_day_groups"):
            from ..engines.wapef_basic13_template import normalize_day_groups
            subject.teaching_day_groups = normalize_day_groups(
                patch["teaching_day_groups"])
            subject.teaching_days = sorted(
                {d for g in subject.teaching_day_groups for d in g},
                key=lambda d: WEEK_DAYS.index(d) if d in WEEK_DAYS else 99,
            )

    record["plan"] = plan.model_dump(mode="json")
    record["updated_date"] = datetime.now().isoformat()
    _save_store(store)
    log_event("weekly_plan_updated", user_id=user.id, weekly_plan_id=plan_id)
    return {"plan": record["plan"]}


# ── Export ────────────────────────────────────────────────────────────────────

def _render_weekly_docx(plan: WeeklyClassPlan) -> Path:
    from ..engines.wapef_basic13_template import (
        render_weekly_document,
        validate_rendered_document,
    )

    WEEKLY_PLANS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEEKLY_PLANS_DIR / f"{plan.id}.docx"
    document = render_weekly_document(plan, {
        "school_name": plan.school_name,
    })
    leftovers = validate_rendered_document(document)
    if leftovers:
        raise HTTPException(
            status_code=500,
            detail=f"Weekly plan export left unfilled tokens: {_leftovers_text(leftovers)}",
        )
    document.save(str(out_path))
    return out_path


def _leftovers_text(leftovers: List[str]) -> str:
    return ", ".join(sorted(set(leftovers)))[:200]


@router.post("/{plan_id}/export/docx")
async def export_weekly_docx(
    plan_id: str,
    user: User = Depends(get_current_user),
):
    """One DOCX: one weekly class plan with every subject section in it."""
    store = _load_store()
    record = next((p for p in store["plans"] if p["id"] == plan_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    record = _get_owned_record(record, user.id)
    plan = WeeklyClassPlan.model_validate(record["plan"])

    out_path = _render_weekly_docx(plan)
    log_event("weekly_plan_exported", user_id=user.id, weekly_plan_id=plan_id,
              format="docx")
    label = _download_label(plan)
    return FileResponse(
        str(out_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"Weekly_Plan_{label}.docx",
    )


@router.post("/{plan_id}/export/pdf")
async def export_weekly_pdf(
    plan_id: str,
    user: User = Depends(get_current_user),
):
    """PDF from the same canonical weekly document (DOCX → PDF)."""
    store = _load_store()
    record = next((p for p in store["plans"] if p["id"] == plan_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    record = _get_owned_record(record, user.id)
    plan = WeeklyClassPlan.model_validate(record["plan"])

    docx_path = _render_weekly_docx(plan)
    pdf_path = docx_path.with_suffix(".pdf")
    _convert_docx_to_pdf(docx_path, pdf_path)
    log_event("weekly_plan_exported", user_id=user.id, weekly_plan_id=plan_id,
              format="pdf")
    label = _download_label(plan)
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"Weekly_Plan_{label}.pdf",
    )


def _download_label(plan: WeeklyClassPlan) -> str:
    class_label = (plan.class_level.value if hasattr(plan.class_level, "value")
                   else str(plan.class_level)) or "Class"
    parts = [class_label, f"Week_{plan.week_number}"]
    if plan.term:
        parts.append(plan.term.replace(" ", "_"))
    return "_".join(p for p in parts if p)


def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    """DOCX -> PDF via LibreOffice when available (the export engine's path)."""
    import shutil
    import subprocess

    converter = shutil.which("soffice") or shutil.which("libreoffice")
    if converter is None:
        raise HTTPException(
            status_code=500,
            detail="PDF conversion is unavailable in this environment (LibreOffice missing).",
        )
    subprocess.run(
        [converter, "--headless", "--convert-to", "pdf",
         "--outdir", str(pdf_path.parent), str(docx_path)],
        check=True, capture_output=True, timeout=180,
    )


def data_service_get_preferences(db: Session, user_id: str):
    from ..service import data_service

    return data_service.get_preferences(db, user_id)

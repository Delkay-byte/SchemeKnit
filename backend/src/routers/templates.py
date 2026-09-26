"""
SchemeKnit Templates Router

Production endpoints for lesson plan template management.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from typing import List, Optional
from sqlalchemy.orm import Session

from ..models import TemplateType, Template, EducationalLevel, TemplateFamily, ClassLevel
from ..engines.template_engine import (
    DEFAULT_TEMPLATES, get_template_by_type, get_visible_sections,
    get_template_by_id, get_templates_for_level,
    get_default_template_for_class_level,
    ALL_PROFILES, PROFILE_MAP
)
from ..engines.template_parser import parse_docx_template, parsed_to_template_sections
from ..engines.template_analyzer import analyze_docx_sample, TEACHFLOW_FIELDS
from ..engines.template_provenance import provenance_for_template, provenance_summary
from ..database import get_db, User
from ..auth import get_current_user
from ..service import data_service
from ..security import sanitize_filename, safe_join

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "templates")

ALLOWED_SAMPLE_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",  # some browsers/clients send generic type
}


#: The four teacher-facing approved groups (PART 10), keyed by educational
#: level. Pending/unverified forms are filtered out before grouping, so a
#: teacher's selection can only ever contain approved groups.
APPROVED_GROUPS = {
    "early_childhood": "Approved Nursery / KG",
    "primary": "Approved Lower Primary",
    "junior_high_school": "Approved JHS",
    "senior_high_school": "Approved SHS",
}


def _approved_group_for(template) -> str:
    """Teacher-facing group label for a verified built-in template."""
    level = getattr(template, "educational_level", None)
    key = level.value if hasattr(level, "value") else str(level or "")
    return APPROVED_GROUPS.get(key, "Approved Templates")


def _validated_sample_filename(file) -> str:
    """Extension + MIME + traversal-safe filename for sample uploads."""
    original = file.filename or ""
    if not original.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are accepted")
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_SAMPLE_MIMES:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    try:
        return sanitize_filename(original)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

# Staged sample analyses: analysis_id -> {file_path, original_filename, structure, owner_id}.
# Analysis creates NO database record; records are created only on explicit save.
STAGED_ANALYSES: dict = {}

MAX_SAMPLE_BYTES = 10 * 1024 * 1024


def _resolve_custom_or_raise(db, template_id: str, owner_id: str):
    """Owner-checked custom template lookup with diagnostic 404 vs 403."""
    from ..service import data_service as ds
    tpl = ds.get_custom_template(db, template_id, owner_id)
    if tpl:
        return tpl
    any_owner = ds.get_custom_template(db, template_id, None)
    if any_owner:
        raise HTTPException(status_code=403, detail="You do not have access to this template")
    raise HTTPException(status_code=404, detail="Template not found")


@router.get("/")
async def list_templates(
    educational_level: Optional[str] = None,
    class_level: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List templates eligible for the requesting user's selection.

    Visibility is enforced here, not only in the UI (PART 9/30):
      * Teachers see ONLY verified/approved built-in forms — never pending,
        draft, experimental or internal ones — plus their own custom templates.
      * Platform admins retain the full internal view (pending templates,
        provenance, lifecycle) for verification workflows.
    ``is_default`` is relative to what is being planned. Without ``class_level``
    it reports each template's own flag; with it, the one template that is the
    default for that class level is marked.
    """
    from ..engines.template_provenance import provenance_for_template

    is_platform_admin = getattr(current_user, "role", None) == "platform_admin"

    # Built-in templates — the FULL active catalog is always returned (PART A):
    # there is no fixed count and no extra server-side limit; the teacher sees
    # every active built-in template for their level plus their own custom
    # templates. Retired ids (e.g. the legacy Headteacher alias, PART C) are
    # never listed for selection.
    builtin = DEFAULT_TEMPLATES
    if educational_level:
        try:
            level = EducationalLevel(educational_level)
            builtin = get_templates_for_level(level)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid level: {educational_level}")

    # Teacher-facing production selection: keep only verified/approved built-in
    # forms. Platform admins see everything, including pending verification.
    if not is_platform_admin:
        builtin = [t for t in builtin
                   if provenance_for_template(t.id).verified]

    default_for_class = None
    if class_level:
        try:
            default_for_class = get_default_template_for_class_level(ClassLevel(class_level))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid class level: {class_level}")

    result = [
        {
            "id": t.id,
            "name": t.name,
            "family": t.family.value,
            "educational_level": t.educational_level.value,
            "description": t.description,
            "features": t.features,
            "is_default": (t.id == default_for_class.id) if default_for_class else t.is_default,
            "is_official": t.is_official,
            "provenance": provenance_for_template(t.id).as_dict(),
            # Teacher-facing grouping (PART 10): the four approved groups. This
            # is the label the UI groups by; internal template ids are not shown.
            "approved_group": _approved_group_for(t),
            "is_custom": False,
            "version": t.version,
        }
        for t in builtin
    ]

    # Custom templates (owner's own)
    custom = data_service.list_custom_templates(db, owner_id=current_user.id, educational_level=educational_level)
    for ct in custom:
        result.append({
            "id": ct.id,
            "name": ct.name,
            "family": ct.family,
            "educational_level": ct.educational_level,
            "description": ct.description or "",
            "features": ct.features or [],
            "is_default": ct.is_default,
            "is_official": False,
            "provenance": provenance_for_template(ct.id, is_custom=True).as_dict(),
            "is_custom": True,
            "version": ct.version,
            "source_type": ct.source_type,
            "section_count": len(ct.sections) if ct.sections else 0,
        })

    return {
        "templates": result,
        "total": len(result),
        "builtin_count": len(builtin),
        "custom_count": len(custom),
        "provenance_summary": provenance_summary(),
    }


@router.get("/profiles")
async def list_profiles():
    """List all curriculum profiles."""
    return {
        "profiles": [
            {
                "name": p.name,
                "educational_level": p.educational_level.value,
                "lessons_per_week": p.generation_rules.get("lessons_per_week", 3),
                "lesson_duration_minutes": p.generation_rules.get("duration_minutes", 60),
                "features": p.generation_rules.get("features", []),
            }
            for p in ALL_PROFILES
        ],
        "total": len(ALL_PROFILES),
    }


@router.get("/profiles/{educational_level}")
async def get_profile(educational_level: str):
    """Get curriculum profile for a specific level."""
    try:
        level = EducationalLevel(educational_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level: {educational_level}")

    profile = PROFILE_MAP.get(level)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "name": profile.name,
        "educational_level": profile.educational_level.value,
        "lessons_per_week": profile.generation_rules.get("lessons_per_week", 3),
        "lesson_duration_minutes": profile.generation_rules.get("duration_minutes", 60),
        "features": profile.generation_rules.get("features", []),
    }


@router.get("/{template_id}")
async def get_template(template_id: str):
    """Get a specific template by ID."""
    template = get_template_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    sections = get_visible_sections(template)

    return {
        "id": template.id,
        "name": template.name,
        "family": template.family.value,
        "educational_level": template.educational_level.value,
        "description": template.description,
        "features": template.features,
        "sections": [
            {
                "name": s.name,
                "label": s.label,
                "description": s.description,
                "required": s.required,
                "fields": [
                    {
                        "name": f.name,
                        "label": f.label,
                        "field_type": f.field_type.value,
                        "required": f.required,
                        "source": f.source.value,
                    }
                    for f in s.fields
                ],
            }
            for s in sections
        ],
        "layout": {
            "page_size": template.layout.page_size,
            "orientation": template.layout.orientation,
            "font_family": template.layout.font_family,
            "font_size": template.layout.font_size,
        },
        "is_default": template.is_default,
        "is_official": template.is_official,
        "provenance": provenance_for_template(template.id).as_dict(),
        "version": template.version,
    }


@router.get("/legacy/{template_type}")
async def get_template_legacy(template_type: str):
    """Legacy endpoint: get template by type string."""
    try:
        tt = TemplateType(template_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid template type: {template_type}")

    template = get_template_by_type(tt)
    sections = get_visible_sections(template)

    return {
        "id": template.id,
        "name": template.name,
        "type": tt.value,
        "family": template.family.value,
        "description": template.description,
        "features": template.features,
        "sections": [
            {
                "name": s.name,
                "label": s.label,
                "description": s.description,
                "required": s.required,
            }
            for s in sections
        ],
    }


# ── Custom Template Endpoints ────────────────────────────────────────────────


@router.post("/upload")
async def upload_template(
    file: UploadFile = File(...),
    name: Optional[str] = None,
    family: str = "jhs",
    educational_level: str = "junior_high_school",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a DOCX file as a custom template. Parses structure automatically."""
    safe_name = _validated_sample_filename(file)

    # Save uploaded file (server-generated id prefix + sanitized name, contained)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())[:12]
    file_path = safe_join(UPLOAD_DIR, f"{file_id}_{safe_name}")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    with open(file_path, "wb") as f:
        f.write(content)

    # Parse DOCX structure
    try:
        parsed = parse_docx_template(file_path)
    except Exception as e:
        os.unlink(file_path)
        raise HTTPException(status_code=400, detail=f"Failed to parse DOCX: {str(e)}")

    sections = parsed_to_template_sections(parsed)

    # Create template record
    tpl = data_service.create_custom_template(
        db,
        owner_id=current_user.id,
        name=name or file.filename.replace(".docx", ""),
        family=family if family in ["early_childhood", "primary", "jhs", "shs"] else parsed.get("detected_family", "jhs"),
        educational_level=educational_level,
        description=f"Custom template parsed from {file.filename}",
        sections=sections,
        layout=parsed.get("layout", {}),
        template_file_path=file_path,
        source_type="uploaded",
    )

    return {
        "id": tpl.id,
        "name": tpl.name,
        "family": tpl.family,
        "educational_level": tpl.educational_level,
        "sections": sections,
        "layout": parsed.get("layout", {}),
        "detected_level": parsed.get("detected_level"),
        "paragraph_count": parsed.get("paragraph_count", 0),
        "table_count": parsed.get("table_count", 0),
        "sample_content": parsed.get("sample_content", [])[:10],
        "message": "Template uploaded and parsed successfully",
    }


@router.post("/")
async def create_template(
    name: str,
    family: str = "jhs",
    educational_level: str = "junior_high_school",
    description: str = "",
    sections: list = [],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a custom template from scratch."""
    tpl = data_service.create_custom_template(
        db,
        owner_id=current_user.id,
        name=name,
        family=family,
        educational_level=educational_level,
        description=description,
        sections=sections,
        source_type="created",
    )
    return {
        "id": tpl.id,
        "name": tpl.name,
        "message": "Template created",
    }


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    sections: Optional[list] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a custom template."""
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    if sections is not None:
        kwargs["sections"] = sections

    tpl = data_service.update_custom_template(db, template_id, current_user.id, **kwargs)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template updated", "id": tpl.id}


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom template."""
    # Get file path before deleting
    tpl = data_service.get_custom_template(db, template_id, current_user.id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    file_path = tpl.template_file_path
    if file_path and os.path.exists(file_path):
        os.unlink(file_path)

    data_service.delete_custom_template(db, template_id, current_user.id)
    return {"message": "Template deleted"}


# ── Sample-Based Custom Template Flow (analyze → review → save) ──────────────


@router.post("/analyze")
async def analyze_sample(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a sample lesson-plan DOCX and analyze its structure.

    Returns the TemplateStructure IR plus an opaque analysis_id.
    Creates NO database record — the teacher must review mappings and save explicitly.
    """
    filename = file.filename or ""
    safe_name = _validated_sample_filename(file)

    content = await file.read()
    if len(content) > MAX_SAMPLE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="File is empty or too small to analyze")

    staged_dir = os.path.join(UPLOAD_DIR, "staged")
    os.makedirs(staged_dir, exist_ok=True)
    # Best-effort purge of abandoned staged samples (>24h, never saved).
    try:
        import time as _time
        cutoff = _time.time() - 24 * 3600
        for entry in os.listdir(staged_dir):
            p = os.path.join(staged_dir, entry)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.unlink(p)
            except OSError:
                pass
    except OSError:
        pass
    analysis_id = str(uuid.uuid4())
    try:
        staged_path = safe_join(staged_dir, f"{analysis_id}_{safe_name}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    with open(staged_path, "wb") as f:
        f.write(content)

    try:
        structure = analyze_docx_sample(staged_path)
    except ValueError as e:
        try:
            os.unlink(staged_path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=str(e))

    STAGED_ANALYSES[analysis_id] = {
        "file_path": staged_path,
        "original_filename": filename,
        "structure": structure,
        "owner_id": current_user.id,
    }

    unmapped = [m["label"] for m in structure["mappings"] if m["field"] is None]
    return {
        "analysis_id": analysis_id,
        "original_filename": filename,
        "structure": structure,
        "detected_family": structure["detected_family"],
        "detected_level": structure["detected_level"],
        "mapping_count": len(structure["mappings"]),
        "unmapped_labels": unmapped,
        "needs_review": len(unmapped) > 0,
    }


@router.post("/save")
async def save_custom_template(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist a reviewed sample template.

    Body: {analysis_id, name, educational_level, family?, description?,
           mappings: [{label, field|null, custom, teacher_confirmed}]}.
    """
    analysis_id = body.get("analysis_id", "")
    staged = STAGED_ANALYSES.get(analysis_id)
    if not staged or staged["owner_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Analysis not found or expired")

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")
    educational_level = body.get("educational_level") or staged["structure"]["detected_level"]

    confirmed = body.get("mappings") or []
    confirmed_by_label = {m.get("label"): m for m in confirmed if m.get("label")}
    for m in confirmed:
        field = m.get("field")
        if field is not None and field not in TEACHFLOW_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unknown SchemeKnit field: {field}")

    # Merge teacher confirmations into the analyzed structure
    structure = staged["structure"]
    for m in structure["mappings"]:
        ov = confirmed_by_label.get(m["label"])
        if ov is not None:
            if ov.get("field") is not None or ov.get("custom"):
                m["field"] = ov.get("field")
                m["custom"] = bool(ov.get("custom", m["custom"]))
            m["teacher_confirmed"] = True
            m["confidence"] = "confirmed"
    for t in structure["tables"]:
        for c in t["cells"]:
            if c.get("label") in confirmed_by_label:
                ov = confirmed_by_label[c["label"]]
                if ov.get("field") is not None or ov.get("custom"):
                    c["field"] = ov.get("field")
                    c["custom"] = bool(ov.get("custom", c["custom"]))
                c["confidence"] = "confirmed"

    # Promote staged file to permanent storage (sanitized + contained)
    permanent_dir = UPLOAD_DIR
    os.makedirs(permanent_dir, exist_ok=True)
    try:
        staged_name = sanitize_filename(staged["original_filename"])
    except ValueError:
        staged_name = "sample.docx"
    try:
        permanent_path = safe_join(permanent_dir, f"{uuid.uuid4().hex[:12]}_{staged_name}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    try:
        os.replace(staged["file_path"], permanent_path)
    except OSError:
        permanent_path = staged["file_path"]
    STAGED_ANALYSES.pop(analysis_id, None)

    tpl = data_service.create_custom_template(
        db,
        owner_id=current_user.id,
        name=name,
        family=body.get("family") or structure["detected_family"],
        educational_level=educational_level,
        description=body.get("description") or f"Custom template from {staged['original_filename']}",
        sections=[{
            "name": "custom_structure",
            "label": name,
            "visible": True,
            "required": True,
            "order": 0,
            "fields": [
                {"name": mm["field"] or mm["label"], "label": mm["label"],
                 "field_type": "textarea", "required": False}
                for mm in structure["mappings"] if mm["field"]
            ],
        }],
        layout=structure["layout"],
        template_file_path=permanent_path,
        source_type="sample",
    )
    # Attach lifecycle columns + full structure IR
    data_service.update_custom_template(
        db, tpl.id, current_user.id,
        original_filename=staged["original_filename"],
        structure=structure,
        version=body.get("version") or "1.0",
    )
    db.refresh(tpl)

    return {
        "id": tpl.id,
        "name": tpl.name,
        "educational_level": tpl.educational_level,
        "family": tpl.family,
        "version": tpl.version,
        "status": getattr(tpl, "status", "active"),
        "mapping_count": len(structure["mappings"]),
        "message": "Custom template saved",
    }


def _serialize_custom(tpl) -> dict:
    return {
        "id": tpl.id,
        "name": tpl.name,
        "family": tpl.family,
        "educational_level": tpl.educational_level,
        "description": tpl.description or "",
        "version": tpl.version,
        "status": getattr(tpl, "status", "active"),
        "original_filename": getattr(tpl, "original_filename", None),
        "source_type": tpl.source_type,
        "owner_id": tpl.owner_id,
        "is_custom": True,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
        "structure": getattr(tpl, "structure", None) or {},
        "layout": tpl.layout or {},
    }


@router.get("/custom/{template_id}")
async def get_custom_template_detail(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-checked full custom template including structure IR and mappings."""
    tpl = _resolve_custom_or_raise(db, template_id, current_user.id)
    return _serialize_custom(tpl)


@router.get("/custom/{template_id}/preview")
async def preview_custom_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview payload: tables with labels, sample values, and mapping states."""
    tpl = _resolve_custom_or_raise(db, template_id, current_user.id)
    structure = getattr(tpl, "structure", None) or {}
    tables = []
    for t in structure.get("tables", []):
        tables.append({
            "index": t.get("index"),
            "rows": t.get("rows"),
            "cols": t.get("cols"),
            "cells": [
                {"r": c.get("r"), "c": c.get("c"), "colspan": c.get("colspan", 1),
                 "label": c.get("label"), "sample_value": c.get("sample_value"),
                 "field": c.get("field"), "confidence": c.get("confidence"),
                 "custom": c.get("custom", False), "is_phase_marker": c.get("is_phase_marker", False),
                 "text": c.get("text")}
                for c in t.get("cells", [])
            ],
        })
    return {
        "id": tpl.id,
        "name": tpl.name,
        "version": tpl.version,
        "original_filename": getattr(tpl, "original_filename", None),
        "layout": tpl.layout or {},
        "mappings": structure.get("mappings", []),
        "tables": tables,
    }


@router.post("/{template_id}/version")
async def version_custom_template(
    template_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bump a custom template version (format X.Y, e.g. 1.1, 2.0)."""
    import re as _re
    version = (body.get("version") or "").strip()
    if not _re.fullmatch(r"\d+\.\d+", version):
        raise HTTPException(status_code=400, detail="Version must look like 1.1 or 2.0")
    _resolve_custom_or_raise(db, template_id, current_user.id)
    tpl = data_service.version_custom_template(db, template_id, current_user.id, version)
    return {"id": tpl.id, "version": tpl.version, "message": "Template version updated"}


@router.post("/{template_id}/archive")
async def archive_custom_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-archive a custom template (hidden from lists; history preserved)."""
    _resolve_custom_or_raise(db, template_id, current_user.id)
    tpl = data_service.archive_custom_template(db, template_id, current_user.id)
    return {"id": tpl.id, "status": tpl.status, "message": "Template archived"}

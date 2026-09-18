"""
SchemeKnit Documents Router

Upload, parse, review, and manage schemes of work.
All endpoints enforce user ownership.
"""

import asyncio
import os
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime

from ..database import get_db
from ..auth import get_current_user, require_teacher_workflow
from ..database import User
from ..service import data_service
from ..parsers.docx_parser import DOCXParser
from ..models import SchemeOfWork
from ..logging_config import get_logger, log_event

router = APIRouter()
parser = DOCXParser()
logger = get_logger()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def _get_upload_dir() -> Path:
    """Get upload directory using absolute path from environment or default."""
    base = os.environ.get("TEACHFLOW_DATA_DIR", os.path.expanduser("~/teachflow_data"))
    upload_dir = Path(base) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _write_file_sync(path: Path, data: bytes):
    """Synchronous file write for use in run_in_executor."""
    path.write_bytes(data)


def _read_file_sync(path: Path) -> bytes:
    """Synchronous file read for use in run_in_executor."""
    return path.read_bytes()


def _resolve_scheme_or_raise(db, scheme_id: str, user_id: str):
    """Fetch an owned scheme with diagnostic 404 vs 403 errors.

    404 = no scheme with this ID exists. 403 = it exists but the
    requester is not its owner. Never collapse authz into 'not found'.
    """
    scheme = data_service.get_scheme(db, scheme_id, user_id)
    if scheme:
        return scheme
    if data_service.scheme_exists(db, scheme_id):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this scheme",
        )
    raise HTTPException(status_code=404, detail="Scheme not found")


@router.post("/upload")
async def upload_scheme(
    file: UploadFile = File(...),
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext != ".docx":
        raise HTTPException(status_code=400, detail="Only .docx files are supported")
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Stream-read to check size before loading full content
    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")
        chunks.append(chunk)
    content = b"".join(chunks)

    upload_dir = _get_upload_dir()
    safe_filename = f"{user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}{ext}"
    file_path = upload_dir / safe_filename

    try:
        # Write file using executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_file_sync, file_path, content)

        # Parse using executor to avoid blocking event loop.
        # Preserve the teacher's original filename for display; the file on
        # disk keeps a UUID-based storage name.
        scheme = await parser.parse(file_path, original_filename=file.filename)

        db_scheme = data_service.create_scheme(db, user.id, scheme, school_id=user.school_id)
        # Track storage location for safe orphan cleanup on delete (server-side only).
        db_scheme.storage_filename = str(file_path)
        db.commit()
        log_event("scheme_uploaded", user_id=user.id, scheme_id=scheme.id, filename=file.filename)

        return {
            "scheme_id": scheme.id,
            "filename": file.filename,
            "subject": scheme.subject.value if hasattr(scheme.subject, 'value') else str(scheme.subject),
            "class_level": scheme.class_level.value if hasattr(scheme.class_level, 'value') else str(scheme.class_level),
            "weeks_count": len(scheme.weeks),
            "status": "uploaded",
        }
    except HTTPException:
        raise
    except Exception as e:
        # Clean up file on failure
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            pass
        # Roll back database session on error
        try:
            db.rollback()
        except Exception:
            pass
        log_event("scheme_upload_failed", user_id=user.id, error=str(e))
        raise HTTPException(status_code=422, detail=f"Failed to parse document: {str(e)}")


@router.get("/")
async def list_schemes(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    schemes = data_service.list_schemes(db, user.id)
    return {
        "schemes": [
            {
                "id": s.id,
                "filename": s.filename,
                "subject": s.subject,
                "class_level": s.class_level,
                "term": s.term,
                "academic_year": s.academic_year,
                "weeks_count": len(s.weeks),
                "status": s.status,
                "upload_date": s.upload_date.isoformat() if s.upload_date else None,
            }
            for s in schemes
        ]
    }


@router.get("/{scheme_id}")
async def get_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    scheme = _resolve_scheme_or_raise(db, scheme_id, user.id)

    return {
        "id": scheme.id,
        "filename": scheme.filename,
        "subject": scheme.subject,
        "class_level": scheme.class_level,
        "term": scheme.term,
        "academic_year": scheme.academic_year,
        "weeks_count": len(scheme.weeks),
        "status": scheme.status,
        "upload_date": scheme.upload_date.isoformat() if scheme.upload_date else None,
    }


@router.get("/{scheme_id}/weeks")
async def get_scheme_weeks(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    scheme_db = _resolve_scheme_or_raise(db, scheme_id, user.id)

    weeks = []
    for w in scheme_db.weeks:
        weeks.append({
            "id": w.id,
            "week_number": w.week_number,
            "week_type": w.week_type,
            "start_date": w.start_date.isoformat() if w.start_date else None,
            "end_date": w.end_date.isoformat() if w.end_date else None,
            "strand": w.strand,
            "sub_strand": w.sub_strand,
            "content_standards": w.content_standards or [],
            "indicators": w.indicators or [],
            "resources": w.resources or [],
        })

    return {"weeks": weeks}


@router.get("/{scheme_id}/workflow")
async def get_workflow_state(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Server-persisted workflow progress for one scheme.

    Stages derive ONLY from stored rows (scheme status, generation jobs,
    lesson plans, export events) — never from page visitation.
    """
    from ..service import compute_workflow_state
    scheme = _resolve_scheme_or_raise(db, scheme_id, user.id)

    jobs = [j for j in data_service.list_jobs(db, user.id) if j.scheme_id == scheme_id]
    completed_job = next(
        (j for j in jobs if j.status == "completed" and (j.completed_lessons or 0) > 0),
        None,
    )
    lessons = data_service.count_lessons_for_scheme(db, scheme_id, user.id)
    exported = data_service.has_export_for_scheme(db, scheme_id, user.id)

    return {
        "scheme_id": scheme.id,
        "scheme_status": scheme.status,
        "stages": compute_workflow_state(
            scheme.status,
            has_job=len(jobs) > 0,
            job_completed=completed_job is not None,
            lessons_count=lessons,
            has_export=exported,
        ),
        "lesson_count": lessons,
        "exported": exported,
    }


@router.put("/{scheme_id}/status")
async def update_scheme_status(
    scheme_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    status = body.get("status", "")
    scheme = data_service.update_scheme_status(db, scheme_id, user.id, status)
    if not scheme:
        _resolve_scheme_or_raise(db, scheme_id, user.id)
    return {"message": "Status updated", "status": scheme.status}


@router.delete("/{scheme_id}")
async def delete_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    scheme = _resolve_scheme_or_raise(db, scheme_id, user.id)
    if data_service.scheme_has_children(db, scheme_id, user.id):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a scheme with generated lesson plans. "
                   "Its lessons and history are preserved.",
        )
    deleted = data_service.delete_scheme(db, scheme_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scheme not found")
    log_event("scheme_deleted", user_id=user.id, scheme_id=scheme_id)
    return {"message": "Scheme deleted"}

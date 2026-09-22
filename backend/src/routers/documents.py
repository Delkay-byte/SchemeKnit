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
from ..parsers.pdf_parser import get_document_parser
from ..database import WeekDB
from ..models import SchemeOfWork, Subject
from ..logging_config import get_logger, log_event

router = APIRouter()
logger = get_logger()

SUPPORTED_EXTENSIONS = (".docx", ".pdf")

#: Detection statuses that require the teacher to review/confirm something
#: before generation. "multiple" needs a subject choice; "needs_confirmation"
#: means the class/subject could not be detected; "extraction_failed" means no
#: usable curriculum was extracted.
NEEDS_SUBJECT_CONFIRMATION = ("multiple",)
NEEDS_REVIEW_STATUSES = (
    "multiple", "needs_confirmation", "low_confidence", "extraction_failed",
)

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


def _analyze_document(document_parser, file_path: Path,
                      original_filename: str = None) -> dict:
    """Run section detection, degrading safely when it fails.

    Detection failure must never fail the upload: the teacher keeps the scheme
    and can still review it manually (low_confidence). The teacher's ORIGINAL
    filename is passed for metadata reconciliation — the on-disk storage name is
    a UUID and carries no signal.
    """
    try:
        info = document_parser.analyze(file_path, original_filename=original_filename)
        if not isinstance(info, dict):
            raise ValueError("unexpected analyze() result")
        return info
    except Exception:
        logger.warning("document_analysis_failed", path=str(file_path))
        return {
            "title": "",
            "detected_subjects": [],
            "sections": [],
            "detection_status": "low_confidence",
        }


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
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only .docx and .pdf files are supported",
        )
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    allowed_content_types = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "application/octet-stream",
        "",
    }
    if content_type not in allowed_content_types:
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

        # Parse using the parser for this format (DOCX or PDF). Preserve the
        # teacher's original filename for display; the file on disk keeps a
        # UUID-based storage name.
        document_parser = get_document_parser(file_path)
        if document_parser is None:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        scheme = await document_parser.parse(file_path, original_filename=file.filename)

        db_scheme = data_service.create_scheme(db, user.id, scheme, school_id=user.school_id)
        # Track storage location for safe orphan cleanup on delete (server-side only).
        db_scheme.storage_filename = str(file_path)

        # ── Multi-subject document detection (§4) ───────────────────────
        # Inspect the document for subject sections. When more than one subject
        # is present the teacher MUST confirm which one to use before
        # generation — the system never silently picks a subject.
        detection = _analyze_document(document_parser, file_path, file.filename)
        db_scheme.document_title = detection.get("title") or ""
        db_scheme.detected_subjects = [
            s["subject"] for s in detection.get("sections", [])
        ]
        db_scheme.detection_status = detection.get("detection_status", "")
        db_scheme.subject_sections = detection.get("sections", [])
        # A document that yielded no weeks is an extraction FAILURE, never a
        # usable empty curriculum (PART J).
        if not scheme.weeks:
            db_scheme.detection_status = "extraction_failed"
            db_scheme.status = "extraction_failed"
        db.commit()
        log_event("scheme_uploaded", user_id=user.id, scheme_id=scheme.id,
                  filename=file.filename,
                  detection_status=db_scheme.detection_status)

        metadata = detection.get("metadata", {}) or {}
        return {
            "scheme_id": scheme.id,
            "filename": file.filename,
            "subject": scheme.subject.value if hasattr(scheme.subject, 'value') else str(scheme.subject),
            "class_level": scheme.class_level.value if hasattr(scheme.class_level, 'value') else str(scheme.class_level),
            "weeks_count": len(scheme.weeks),
            "status": db_scheme.status,
            "detection": {
                "status": db_scheme.detection_status,
                "title": db_scheme.document_title,
                "subjects": db_scheme.detected_subjects or [],
                "sections": db_scheme.subject_sections or [],
                "needs_confirmation": db_scheme.detection_status in NEEDS_REVIEW_STATUSES,
                "subject_confidence": "none" if not metadata.get("subject") else "high",
                "class_confidence": "none" if not metadata.get("class_level") else "high",
                "subject_signals": metadata.get("subject_signals", {}),
                "class_signals": metadata.get("class_signals", {}),
            },
            "extraction": {
                "weeks_count": len(scheme.weeks),
                "status": db_scheme.detection_status,
            },
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
        "document_title": scheme.document_title or "",
        "detected_subjects": scheme.detected_subjects or [],
        "detection_status": scheme.detection_status or "",
        "needs_subject_confirmation": (
            scheme.detection_status in NEEDS_SUBJECT_CONFIRMATION
        ),
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


@router.get("/{scheme_id}/detection")
async def get_document_detection(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Detected document structure for the subject-confirmation screen (§4).

    Returns the detected subjects, the detection confidence, and whether the
    teacher must confirm a subject section before generating.
    """
    scheme = _resolve_scheme_or_raise(db, scheme_id, user.id)
    return {
        "scheme_id": scheme.id,
        "filename": scheme.filename,
        "document_title": scheme.document_title or "",
        "detected_subjects": scheme.detected_subjects or [],
        "sections": scheme.subject_sections or [],
        "detection_status": scheme.detection_status or "",
        "confirmed_subject": (
            scheme.subject if (scheme.detection_status == "confirmed") else None
        ),
        "needs_confirmation": (
            scheme.detection_status in NEEDS_SUBJECT_CONFIRMATION
        ),
    }


@router.post("/{scheme_id}/confirm-subject")
async def confirm_subject_section(
    scheme_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Confirm which subject section of a multi-subject document to use (§4).

    The chosen section is re-extracted from the stored document and becomes the
    scheme's curriculum. Other subject sections are ignored — never silently
    mixed in. The teacher must confirm before generation proceeds.
    """
    scheme = _resolve_scheme_or_raise(db, scheme_id, user.id)

    requested = (body or {}).get("subject", "")
    if not requested:
        raise HTTPException(status_code=400, detail="A subject is required")

    try:
        subject = Subject(requested)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown subject")

    detected = scheme.detected_subjects or []
    if detected and subject.value not in detected:
        # Mismatch handling (§4): warn rather than silently accept.
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{subject.value}' is not one of the subjects detected in this "
                f"document ({', '.join(detected)}). Choose a detected subject or "
                f"re-upload the correct file."
            ),
        )

    storage = scheme.storage_filename
    if not storage:
        raise HTTPException(status_code=409, detail="The uploaded file is no longer available")
    file_path = Path(storage)
    if not file_path.exists():
        raise HTTPException(status_code=409, detail="The uploaded file is no longer available")

    document_parser = get_document_parser(file_path)
    if document_parser is None:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    try:
        extracted = await document_parser.parse(
            file_path,
            original_filename=scheme.filename,
            target_subject=subject.value,
        )
    except Exception as e:
        log_event("subject_confirm_failed", user_id=user.id, scheme_id=scheme_id, error=str(e))
        raise HTTPException(status_code=422, detail="Could not re-read the subject section")

    if not extracted.weeks:
        raise HTTPException(
            status_code=422,
            detail="No curriculum content found in that subject section",
        )

    # Replace the scheme's extracted curriculum with the confirmed section.
    db.query(WeekDB).filter(WeekDB.scheme_id == scheme_id).delete()
    for w in extracted.weeks:
        db.add(WeekDB(
            id=w.id,
            scheme_id=scheme_id,
            week_number=w.week_number,
            week_type=w.week_type.value if hasattr(w.week_type, "value") else str(w.week_type),
            start_date=w.start_date,
            end_date=w.end_date,
            strand=w.strand or "",
            sub_strand=w.sub_strand or "",
            content_standards=w.content_standards,
            indicators=w.indicators,
            resources=w.resources,
        ))

    scheme.subject = extracted.subject.value if hasattr(extracted.subject, "value") else str(extracted.subject)
    scheme.class_level = (
        extracted.class_level.value if hasattr(extracted.class_level, "value") else str(extracted.class_level)
    )
    scheme.detection_status = "confirmed"
    db.commit()
    log_event("subject_confirmed", user_id=user.id, scheme_id=scheme_id,
              subject=scheme.subject)

    return {
        "scheme_id": scheme.id,
        "confirmed_subject": scheme.subject,
        "class_level": scheme.class_level,
        "weeks_count": len(extracted.weeks),
        "detection_status": scheme.detection_status,
    }


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

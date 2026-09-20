"""
SchemeKnit Generation Router

Production endpoints for lesson plan generation with persistence.
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote
import re
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user, require_teacher_workflow
from ..database import User
from ..service import data_service
from ..entitlements import require_ai_entitlement
from ..models import TermConfig, LessonPlan, Subject, ClassLevel, TemplateType, AIMode
from ..engines.generation_pipeline import GenerationPipeline
from ..logging_config import get_logger, log_event, log_error

router = APIRouter()
pipeline = GenerationPipeline()
logger = get_logger()


#: Response header carrying the download filename for export endpoints.
#: Exposed to the browser via CORS `expose_headers` (see main.py).
X_FILENAME_HEADER = "X-TeachFlow-Filename"


def _download_response(path, media_type: str, filename: str) -> FileResponse:
    """Binary download response shared by every export endpoint.

    Filename transport is a custom header rather than
    `Content-Disposition: attachment`, because the browser classifies an
    attachment-dispositioned `application/zip` response as a *download* and
    refuses to deliver it to `fetch()`. The request then dies the instant the
    response arrives (HttpError / "Failed to fetch") and no file is ever saved
    — even though the server answered 200 with a perfectly valid archive.

    A `Content-Disposition: inline` header is kept so direct/scripted consumers
    still see the intended name.
    """
    name = Path(filename).name
    response = FileResponse(
        str(path),
        media_type=media_type,
        headers={
            X_FILENAME_HEADER: quote(name, safe=""),
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(name, safe='')}",
        },
    )
    return response


def _custom_structure_for(db, user_id: str, template_id) -> Optional[dict]:
    """Resolve a teacher-owned custom template id to its saved structure IR.

    Returns None for blank ids, unknown ids, or other owners' templates
    (which then fall back to built-in rendering — never leak across owners).

    The approved organizational template is deliberately NOT resolved here: it
    names the same approved source document as the verified JHS form, so
    ``is_ges_form_template`` routes it to the in-place renderer and the output
    is topologically identical to the source by construction. Returning a
    structure here would rebuild the document from an IR and reintroduce a
    second layout that can drift from the golden master.
    """
    if not template_id:
        return None
    tpl = data_service.get_custom_template(db, template_id, user_id)
    if not tpl:
        return None
    struct = getattr(tpl, "structure", None) or {}
    if not struct.get("tables"):
        return None
    return struct


async def _run_pipeline(fn, *args, **kwargs):
    """Run synchronous export builders off the event loop (same pattern as upload)."""
    loop = asyncio.get_running_loop()
    from functools import partial
    return await loop.run_in_executor(None, partial(fn, *args, **kwargs))


@router.post("/{scheme_id}/allocation-preview")
async def preview_allocation(
    scheme_id: str,
    config: TermConfig,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Preview the indicator→period allocation WITHOUT generating lessons.

    Returns a per-week table showing which indicator lands in which teaching
    period, plus any allocation conflicts (e.g. more indicators than
    configured teaching periods). The teacher reviews this before confirming
    generation.
    """
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")

    config.school_name = _resolve_school_name(db, user)
    config.teacher_name = _resolve_teacher_name(db, user)

    scheme = data_service.scheme_to_model(scheme_db)

    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme.weeks, config.holidays
    )
    coverage = pipeline.allocation_engine.allocate(
        scheme.weeks, calendar, config, config.include_special_weeks
    )
    report = pipeline.coverage_validator.generate_report(scheme.weeks, coverage)

    return report


@router.post("/{scheme_id}/generate")
async def generate_lesson_plans(
    scheme_id: str,
    config: TermConfig,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")

    # ── Subject-section confirmation gate (§4) ──────────────────────────
    # A document that contains several subject sections must be confirmed before
    # anything is generated. The system never silently picks a subject.
    if getattr(scheme_db, "detection_status", "") == "multiple":
        raise HTTPException(
            status_code=409,
            detail=(
                "This document contains more than one subject. Confirm which "
                "subject section to use before generating lesson plans."
            ),
        )

    # Server-authoritative identity (PART 14/15/32). School and teacher names are
    # derived from the authenticated user's real school relationship and profile —
    # never from the request body — so a client cannot generate another school's
    # plan or impersonate a teacher. The config is corrected in place, and the
    # same values are what the export header renders.
    config.school_name = _resolve_school_name(db, user)
    config.teacher_name = _resolve_teacher_name(db, user)

    # ── Entitlement gate: generation quota (individual free teachers) ──────
    from ..entitlements import resolve_entitlement, increment_generation_count
    resolved = resolve_entitlement(db, user)
    gen_limit = resolved.get("generation_limit", 0)
    gen_used = resolved.get("generations_used", 0)
    if gen_limit > 0 and gen_used >= gen_limit:
        raise HTTPException(
            status_code=403,
            detail=f"You have reached the generation limit ({gen_limit}) for your current plan. "
                   "Upgrade to Teacher Pro for unlimited generations.",
        )

    # ── Pre-generation lesson estimate ──────────────────────────────────
    # In the indicator→period model, each indicator becomes one lesson.
    # Estimate the count BEFORE generation so a free teacher cannot exceed
    # their quota mid-generation.
    scheme = data_service.scheme_to_model(scheme_db)
    if gen_limit > 0:
        from ..models import WeekType
        estimated_lessons = sum(
            len(w.indicators)
            for w in scheme.weeks
            if w.week_type == WeekType.INSTRUCTION
        )
        remaining = gen_limit - gen_used
        if estimated_lessons > remaining:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This scheme will generate {estimated_lessons} individual lesson plans "
                    f"(one per indicator), but your current plan has only {remaining} "
                    f"generation{'' if remaining == 1 else 's'} remaining. "
                    "Upgrade to Teacher Pro for unlimited generations."
                ),
            )

    if config.ai_mode != AIMode.OFF:
        # Commercial entitlement is enforced before any provider is constructed:
        # an installed local provider (e.g. Ollama) never grants access by
        # itself. AI OFF still generates a full deterministic lesson plan.
        require_ai_entitlement(user, db)

    existing_job = data_service.get_term_config(db, scheme_id, user.id)
    if existing_job:
        # Previous generation for this scheme exists: replace its lessons (regeneration must not duplicate)
        data_service.delete_lesson_plans_for_scheme(db, scheme_id, user.id)

    job_db = data_service.create_job(db, user.id, scheme_id, config)
    config.scheme_of_work_id = scheme_id

    try:
        job = pipeline.generate_all(
            scheme, config,
            template_id=config.template_id,
        )

        data_service.update_job(db, job_db.id,
            status=job.status.value,
            total_lessons=job.total_lessons,
            completed_lessons=job.completed_lessons,
            progress=100,
        )

        if hasattr(job, '_lesson_plans'):
            for lp in job._lesson_plans:
                data_service.create_lesson_plan(db, user.id, job_db.id, scheme_id, lp)

        # Increment generation count for entitlement tracking.
        # Usage counts INDIVIDUAL LESSONS (one per indicator), not one per
        # generation request. A week with 3 indicators = 3 lessons = 3 credits.
        actual_lesson_count = (
            len(job._lesson_plans) if hasattr(job, '_lesson_plans') else job.completed_lessons
        )
        increment_generation_count(user, db, count=max(actual_lesson_count, 1))

        log_event("generation_completed", user_id=user.id, scheme_id=scheme_id, job_id=job_db.id,
                   total_lessons=job.total_lessons, lessons_billed=actual_lesson_count)

        return {
            "job_id": job_db.id,
            "status": job.status.value,
            "total_lessons": job.total_lessons,
            "completed_lessons": job.completed_lessons,
        }

    except Exception as e:
        data_service.update_job(db, job_db.id, status="failed", error_message=str(e))
        log_error("generation_failed", user_id=user.id, scheme_id=scheme_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/{job_id}/status")
async def get_generation_status(
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "total_lessons": job.total_lessons,
        "completed_lessons": job.completed_lessons,
        "failed_lessons": job.failed_lessons,
        "error_message": job.error_message,
        "coverage": {
            "total_generated_lessons": job.completed_lessons,
        }
    }


@router.get("/{job_id}/lessons")
async def get_generated_lessons(
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    return {
        "lesson_plans": [_serialize_lesson(lp) for lp in lessons],
        "total": len(lessons),
    }


@router.get("/lessons/{lesson_id}")
async def get_lesson_plan(
    lesson_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    lp = data_service.get_lesson_plan(db, lesson_id, user.id)
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return _serialize_lesson(lp)


@router.put("/lessons/{lesson_id}")
async def update_lesson_plan(
    lesson_id: str,
    updates: dict,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    lp = data_service.update_lesson_plan(db, lesson_id, user.id, updates)
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson not found")
    log_event("lesson_edited", user_id=user.id, lesson_id=lesson_id)
    return _serialize_lesson(lp)


@router.get("/scheme/{scheme_id}/status")
async def get_latest_job_for_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return the most recent generation job for a scheme (so the UI can restore state)."""
    jobs = data_service.list_jobs(db, user.id)
    for job in jobs:
        if job.scheme_id == scheme_id:
            return {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "total_lessons": job.total_lessons,
                "completed_lessons": job.completed_lessons,
                "failed_lessons": job.failed_lessons,
                "error_message": job.error_message,
                "coverage": {
                    "total_generated_lessons": job.completed_lessons,
                },
            }
    return None


@router.get("/{job_id}/coverage")
async def get_curriculum_coverage(
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)

    # In the indicator→period model each lesson carries exactly one primary
    # indicator, so total_indicators == total lessons with an indicator.
    total_lessons = len(lessons)
    total_indicators = sum(1 for lp in lessons if lp.indicator_codes)
    indicators_duplicated = 0
    from collections import Counter
    code_counter = Counter()
    for lp in lessons:
        for c in (lp.indicator_codes or []):
            code_counter[c] += 1
    indicators_duplicated = sum(n - 1 for n in code_counter.values() if n > 1)

    coverage_pct = (
        (total_indicators / total_indicators * 100)
        if total_indicators > 0 else 0.0
    )

    # Per-week summary for the review UI
    from collections import defaultdict
    week_map = defaultdict(list)
    for lp in lessons:
        week_map[lp.week_number].append(lp)
    week_summaries = []
    for wn in sorted(week_map.keys()):
        wls = sorted(week_map[wn], key=lambda x: x.lesson_number)
        week_summaries.append({
            "week_number": wn,
            "indicator_count": sum(1 for w in wls if w.indicator_codes),
            "lesson_count": len(wls),
            "periods": [
                {
                    "period_index": w.lesson_number,
                    "indicator_code": (w.indicator_codes or [""])[0] if w.indicator_codes else "",
                    "indicator_description": (w.indicators or [""])[0] if w.indicators else "",
                    "lesson_date": w.lesson_date.isoformat() if w.lesson_date else None,
                }
                for w in wls
            ],
        })

    return {
        "total_lessons": total_lessons,
        "total_indicators": total_indicators,
        "indicators_duplicated": indicators_duplicated,
        "coverage_percentage": coverage_pct,
        # Field the UI expects (CurriculumCoverage TS type)
        "total_generated_lessons": total_lessons,
        "total_periods_allocated": total_lessons,
        "warnings": [],
        "allocation_conflicts": [],
        "weeks": week_summaries,
    }


@router.post("/{job_id}/export/docx")
async def export_docx(
    job_id: str,
    template_type: str = "GES-style",
    template_id: str = None,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'

    custom_structure = _custom_structure_for(db, user.id, template_id)
    # Context the renderer resolves non-stored header fields from: the term the
    # teacher configured and the timetable period. Both are server-side; the
    # school/teacher names come from the lesson rows themselves.
    prefs = data_service.get_preferences(db, user.id)
    snapshot = job.config_snapshot or {}
    render_context = {
        "term": scheme_db.term if scheme_db and scheme_db.term else None,
        "academic_term": snapshot.get("term") if snapshot else None,
        "period": (prefs.default_period if prefs else "")
                  or snapshot.get("period", "")
                  or (lp_models[0].period if lp_models else ""),
    }
    if custom_structure is not None:
        log_event("custom_template_export", user_id=user.id, job_id=job_id)
        out = await _run_pipeline(
            pipeline.export_docx_combined_custom,
            lp_models, custom_structure,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
            render_context,
        )
        download_name = f"Lesson_Plans_{scheme_label}.docx"
    elif len(lp_models) == 1 and not template_id:
        # Single lesson with no template chosen: serve that lesson as its own
        # descriptively named file. When a template IS selected (including the
        # approved organizational form) the combined path below is used so the
        # download is always named after the scheme.
        output_dir = Path(f"exports/{user.id}/{job_id}/docx")
        files = await _run_pipeline(pipeline.export_docx_batch, lp_models, tt, output_dir, template_id=template_id)
        out = files[0]
        download_name = out.name
    else:
        # One combined document: all lessons, each starting on a new page
        out = await _run_pipeline(
            pipeline.export_docx_combined,
            "",
            lp_models, tt,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
            template_id=template_id,
        )
        download_name = f"Lesson_Plans_{scheme_label}.docx"

    data_service.log_export_event(db, job.id, job.scheme_id, user.id, "docx")
    return _download_response(
        out,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        download_name,
    )


def _convert_only(pipeline, docx_path: Path, pdf_path: Path) -> Path:
    """Convert an existing DOCX to PDF (no re-rendering) — runs in the executor."""
    return pipeline.pdf_engine._convert_docx_to_pdf(docx_path, pdf_path)


@router.post("/{job_id}/export/pdf")
async def export_pdf(
    job_id: str,
    template_type: str = "GES-style",
    template_id: str = None,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    from ..engines.pdf_export import (
        PDFExportEngine, PDFConversionError, _is_real_pdf,
        PDF_CONVERTER_REQUIREMENT, PDF_CONVERSION_FAILED,
    )
    # Layer 1 — toolchain missing on this server. DOCX/XLSX/ZIP unaffected.
    if not PDFExportEngine.is_available():
        log_event("pdf_export_unavailable", user_id=user.id, job_id=job_id)
        raise HTTPException(status_code=503, detail=PDF_CONVERTER_REQUIREMENT)

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'

    # Build ONE combined DOCX (the same document the Word download serves) and
    # convert it once. The previous per-lesson batch held the request open for
    # the whole multi-minute conversion — long enough for the browser to abort
    # the fetch — and then returned only the first lesson's PDF.
    combined_docx = Path(f"exports/{user.id}/{job_id}/pdf/lesson_plans.docx")
    try:
        await _run_pipeline(
            pipeline.export_docx_combined, scheme_label, lp_models, tt,
            combined_docx, template_id=template_id)
    except Exception as e:
        logger.error("pdf_source_docx_failed", user_id=user.id, job_id=job_id, detail=str(e))
        raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)

    # Layer 2 — converter present but produced nothing usable. Reported as a
    # controlled 500: never a raw traceback, never a mislabeled .docx body.
    target = combined_docx.with_suffix(".pdf")
    try:
        await _run_pipeline(
            pipeline.pdf_engine.export_single.__wrapped__ if False else _convert_only,
            pipeline, combined_docx, target)
    except PDFConversionError as e:
        logger.error("pdf_conversion_failed", user_id=user.id, job_id=job_id, detail=str(e))
        raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)

    # Final guard: never hand the browser a body labelled application/pdf that
    # isn't actually a PDF (that is what made PDF "downloads" fail silently).
    if not target.exists() or not _is_real_pdf(target):
        logger.error("pdf_conversion_failed", user_id=user.id, job_id=job_id,
                     detail="output failed PDF signature check")
        raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)

    data_service.log_export_event(db, job.id, job.scheme_id, user.id, "pdf")
    return _download_response(target, "application/pdf", f"Lesson_Plans_{scheme_label}.pdf")


# ── One-time authenticated download URLs (PART 27/28) ─────────────────────────
#
# A download manager (IDM) intercepts the browser's own navigation, not a
# fetch() body read. When the app builds a blob in JS and clicks an anchor,
# IDM can truncate the stream the page is still reading, so response.blob()
# throws "Failed to fetch" even though the file was handed off successfully.
#
# The fix keeps the successful-handoff case silent without hiding real errors:
# the POST still validates and renders (so a genuine 503/500 reaches the user),
# then issues a single-use token. The browser navigates to the token URL, which
# is a normal download the browser/IDM owns end to end — no JS body read to
# race against, so no false failure. The token is bound to the user and job,
# expires quickly, and works exactly once.

import time as _time
import secrets as _secrets

#: token -> {user_id, job_id, path, media_type, filename, expires_at}
_DOWNLOAD_TOKENS: Dict[str, dict] = {}
DOWNLOAD_TOKEN_TTL_SECONDS = 120


def _issue_download_token(user_id: str, job_id: str, path, media_type: str,
                          filename: str) -> str:
    """Create a single-use, short-lived download token bound to (user, job)."""
    token = _secrets.token_urlsafe(32)
    _DOWNLOAD_TOKENS[token] = {
        "user_id": user_id,
        "job_id": job_id,
        "path": str(path),
        "media_type": media_type,
        "filename": filename,
        "expires_at": _time.time() + DOWNLOAD_TOKEN_TTL_SECONDS,
    }
    return token


def _consume_download_token(token: Optional[str], user_id: str) -> Optional[dict]:
    """Pop a valid, unexpired, user-matched token; else None."""
    if not token:
        return None
    entry = _DOWNLOAD_TOKENS.pop(token, None)
    if not entry:
        return None
    if entry["user_id"] != user_id:
        return None
    if _time.time() > entry["expires_at"]:
        return None
    return entry


@router.post("/{job_id}/download-url")
async def issue_download_url(
    job_id: str,
    format: str,
    template_type: str = "GES-style",
    template_id: str = None,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Pre-validate an export and hand back a one-time download URL.

    The expensive work (render/conversion) runs here, so any genuine failure —
    no converter, a failed conversion, a missing job — is reported as a real
    error on this request. When it succeeds the browser navigates to the
    returned URL, which delivers the bytes as a native download: download
    managers intercept that navigation cleanly and the page never reads the
    body, so a successful handoff cannot be misreported as "Failed to fetch".
    """
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    fmt = (format or "").lower()
    if fmt not in ("docx", "pdf", "zip"):
        raise HTTPException(status_code=400, detail="Unsupported format")

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'
    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    if fmt == "docx":
        out = await _run_pipeline(
            pipeline.export_docx_combined, "", lp_models, tt,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
            template_id=template_id)
        media_type = ("application/vnd.openxmlformats-officedocument"
                      ".wordprocessingml.document")
        filename = f"Lesson_Plans_{scheme_label}.docx"
    elif fmt == "zip":
        out = await _run_pipeline(
            pipeline.export_zip, lp_models, tt,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.zip"),
            template_id=template_id)
        media_type = "application/zip"
        filename = f"Lesson_Plans_{scheme_label}.zip"
    else:  # pdf
        from ..engines.pdf_export import (
            PDFExportEngine, PDFConversionError, _is_real_pdf,
            PDF_CONVERTER_REQUIREMENT, PDF_CONVERSION_FAILED,
        )
        if not PDFExportEngine.is_available():
            log_event("pdf_export_unavailable", user_id=user.id, job_id=job_id)
            raise HTTPException(status_code=503, detail=PDF_CONVERTER_REQUIREMENT)
        combined_docx = Path(f"exports/{user.id}/{job_id}/pdf/lesson_plans.docx")
        try:
            await _run_pipeline(
                pipeline.export_docx_combined, scheme_label, lp_models, tt,
                combined_docx, template_id=template_id)
        except Exception as e:
            logger.error("pdf_source_docx_failed", user_id=user.id, job_id=job_id,
                         detail=str(e))
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)
        target = combined_docx.with_suffix(".pdf")
        try:
            await _run_pipeline(_convert_only, pipeline, combined_docx, target)
        except PDFConversionError as e:
            logger.error("pdf_conversion_failed", user_id=user.id, job_id=job_id,
                         detail=str(e))
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)
        if not target.exists() or not _is_real_pdf(target):
            logger.error("pdf_conversion_failed", user_id=user.id, job_id=job_id,
                         detail="output failed PDF signature check")
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)
        out = target
        media_type = "application/pdf"
        filename = f"Lesson_Plans_{scheme_label}.pdf"

    data_service.log_export_event(db, job.id, job.scheme_id, user.id, fmt)
    token = _issue_download_token(user.id, job.id, out, media_type, filename)
    return {
        "download_url": f"/api/generation/downloads/{token}",
        "filename": filename,
        "media_type": media_type,
    }


@router.get("/downloads/{token}")
async def download_by_token(
    token: str,
    user: User = Depends(get_current_user),
):
    """Deliver a pre-validated export as a native browser download.

    This is the URL the browser navigates to. It answers
    ``Content-Disposition: attachment`` with the correct media type so the
    browser (or a download manager) owns the transfer — there is no JS body
    read on the page, so a successful handoff cannot surface as a false
    "Failed to fetch". Auth still applies: the token is user-bound and
    single-use, so it cannot be shared or replayed.
    """
    entry = _consume_download_token(token, user.id)
    if not entry:
        raise HTTPException(status_code=404, detail="Download link expired or invalid")
    path = Path(entry["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File no longer available")
    name = Path(entry["filename"]).name
    return FileResponse(
        str(path),
        media_type=entry["media_type"],
        filename=name,
        headers={
            X_FILENAME_HEADER: quote(name, safe=""),
            # attachment (not inline): this endpoint is a direct navigation,
            # never a fetch() body read, so the disposition is the browser's
            # cue to save rather than render.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
        },
    )


@router.post("/{job_id}/export/xlsx")
async def export_xlsx(
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    output_path = Path(f"exports/{user.id}/{job_id}/register.xlsx")
    await _run_pipeline(pipeline.export_xlsx, lp_models, output_path)
    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'
    data_service.log_export_event(db, job.id, job.scheme_id, user.id, "xlsx")
    return _download_response(
        output_path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"Lesson_Register_{scheme_label}.xlsx",
    )


@router.post("/{job_id}/export/zip")
async def export_zip(
    job_id: str,
    template_type: str = "GES-style",
    template_id: str = None,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    # ── Entitlement gate: ZIP export requires Pro or school license ────────
    from ..entitlements import can_export_zip
    allowed, reason = can_export_zip(user, db)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    zip_path = Path(f"exports/{user.id}/{job_id}/lesson_plans.zip")
    custom_structure = _custom_structure_for(db, user.id, template_id)
    scheme_for_ctx = data_service.get_scheme(db, job.scheme_id, user.id)
    render_context = {"term": scheme_for_ctx.term} if scheme_for_ctx and scheme_for_ctx.term else {}
    if custom_structure is not None:
        log_event("custom_template_export", user_id=user.id, job_id=job_id)
    await _run_pipeline(pipeline.export_zip, lp_models, tt, zip_path,
                        template_id=template_id, structure=custom_structure,
                        context=render_context)

    scheme_db = scheme_for_ctx
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'
    data_service.log_export_event(db, job.id, job.scheme_id, user.id, "zip")
    # application/zip is the content type Chrome/Edge treat as a download, so this
    # endpoint is the one that relied on the disposition fix above.
    return _download_response(
        zip_path, "application/zip", f"Lesson_Plans_{scheme_label}.zip")


@router.get("/lessons")
async def list_all_lessons(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """List all lesson plans for the current user across all schemes."""
    from ..database import LessonPlanDB, SchemeDB
    lessons = db.query(LessonPlanDB).filter(
        LessonPlanDB.owner_id == user.id
    ).order_by(LessonPlanDB.lesson_date, LessonPlanDB.lesson_sequence).all()

    schemes_map = {}
    for s in db.query(SchemeDB).filter(SchemeDB.owner_id == user.id).all():
        schemes_map[s.id] = s

    result = []
    for lp in lessons:
        serialized = _serialize_lesson(lp)
        scheme = schemes_map.get(lp.scheme_id)
        serialized["scheme_filename"] = scheme.filename if scheme else "Unknown"
        serialized["scheme_subject"] = scheme.subject if scheme else "Unknown"
        result.append(serialized)

    return {
        "lesson_plans": result,
        "total": len(result),
    }


@router.get("/schemes/{scheme_id}/lessons")
async def get_lessons_for_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    lessons = data_service.get_lesson_plans_for_scheme(db, scheme_id, user.id)
    return {
        "lesson_plans": [_serialize_lesson(lp) for lp in lessons],
        "total": len(lessons),
    }


def _resolve_school_name(db: Session, user: User) -> Optional[str]:
    """The authenticated user's real school name.

    Identity is server-authoritative (PART 15): the teacher's school membership
    is looked up from the authenticated user, never accepted from the client.
    A teacher with no school relationship gets None, which renders blank rather
    than a generic placeholder.
    """
    from ..database import SchoolDB
    if not getattr(user, "school_id", None):
        return None
    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    return school.name if school else None


def _resolve_teacher_name(db: Session, user: User) -> Optional[str]:
    """The authenticated user's real display name (PART 14/18).

    Comes from the account profile; the client cannot supply it. Falls back to
    the user's email local-part only when the profile has no name yet, and the
    UI prompts for a full name on first use (PART 18).
    """
    full = (getattr(user, "full_name", None) or "").strip()
    if full:
        return full
    email = getattr(user, "email", None) or ""
    local = email.split("@", 1)[0]
    return local.strip().title() or None


def _serialize_lesson(lp) -> dict:
    from ..database import LessonPlanDB
    return {
        "id": lp.id,
        "scheme_id": lp.scheme_id,
        "job_id": lp.job_id,
        "week_number": lp.week_number,
        "source_week": lp.week_number,
        "teaching_week": getattr(lp, "teaching_week", None) or lp.week_number,
        "carry_forward": bool(getattr(lp, "carry_forward", False)),
        "lesson_sequence": lp.lesson_sequence,
        "lesson_date": lp.lesson_date.isoformat() if lp.lesson_date else None,
        "lesson_number": lp.lesson_number,
        "period": getattr(lp, "period", "") or "",
        "class_level": lp.class_level,
        "subject": lp.subject,
        "class_size": lp.class_size,
        "duration_minutes": lp.duration_minutes,
        "school_name": lp.school_name,
        "teacher_name": lp.teacher_name,
        "strand": lp.strand,
        "sub_strand": lp.sub_strand,
        "content_standard": lp.content_standard,
        "content_standard_code": lp.content_standard_code,
        "indicators": lp.indicators or [],
        "indicator_codes": lp.indicator_codes or [],
        "lesson_topic": lp.lesson_topic,
        "previous_knowledge": lp.previous_knowledge,
        "learning_objectives": lp.learning_objectives or [],
        "core_competencies": lp.core_competencies or [],
        "teaching_learning_resources": lp.teaching_learning_resources or [],
        "introduction": lp.introduction,
        "main_activities": lp.main_activities or [],
        "learner_activities": lp.learner_activities or [],
        "teacher_activities": lp.teacher_activities or [],
        "assessment": lp.assessment,
        "conclusion": lp.conclusion,
        "references": lp.references or [],
        "status": lp.status,
        "ai_generated": lp.ai_generated,
        "teacher_edited": lp.teacher_edited,
    }


def _parse_activity_list(raw, model_cls):
    """Parse DB JSON activity/objective lists into pydantic models.

    Previously these were dropped (hardcoded to []), so exports rendered
    generic fallback text instead of the generated activities.
    """
    if not raw:
        return []
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    out = []
    for it in items or []:
        try:
            out.append(model_cls(**it) if isinstance(it, dict) else it)
        except Exception:
            continue
    return out


def _db_to_lesson_model(lp) -> LessonPlan:
    from ..database import LessonPlanDB
    from ..models import TeachingActivity, LearningObjective
    return LessonPlan(
        id=lp.id,
        scheme_of_work_id=lp.scheme_id,
        term_config_id=lp.job_id,
        week_number=lp.week_number,
        teaching_week=getattr(lp, "teaching_week", None) or lp.week_number,
        carry_forward=bool(getattr(lp, "carry_forward", False)),
        lesson_sequence=lp.lesson_sequence,
        lesson_date=lp.lesson_date,
        lesson_number=lp.lesson_number,
        period=getattr(lp, "period", "") or "",
        class_level=ClassLevel(lp.class_level) if lp.class_level in [c.value for c in ClassLevel] else ClassLevel.BASIC_9,
        subject=Subject(lp.subject) if lp.subject in [s.value for s in Subject] else Subject.SCIENCE,
        class_size=lp.class_size,
        duration_minutes=lp.duration_minutes,
        school_name=lp.school_name,
        teacher_name=lp.teacher_name,
        strand=lp.strand,
        sub_strand=lp.sub_strand,
        content_standard=lp.content_standard,
        content_standard_code=lp.content_standard_code,
        indicators=lp.indicators or [],
        indicator_codes=lp.indicator_codes or [],
        lesson_topic=lp.lesson_topic,
        previous_knowledge=lp.previous_knowledge,
        learning_objectives=_parse_activity_list(lp.learning_objectives, LearningObjective),
        core_competencies=lp.core_competencies or [],
        teaching_learning_resources=lp.teaching_learning_resources or [],
        introduction=lp.introduction,
        main_activities=_parse_activity_list(lp.main_activities, TeachingActivity),
        learner_activities=_parse_activity_list(lp.learner_activities, TeachingActivity),
        teacher_activities=_parse_activity_list(lp.teacher_activities, TeachingActivity),
        assessment=lp.assessment,
        conclusion=lp.conclusion,
        references=lp.references or [],
    )

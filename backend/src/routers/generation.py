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
from ..auth import get_current_user, get_optional_user, require_teacher_workflow
from ..database import User
from ..service import data_service
from ..entitlements import require_ai_entitlement, consume_ai_generation
from ..models import (
    TermConfig, LessonPlan, Subject, ClassLevel, TemplateType, AIMode,
    ReferenceEntry,
)
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

    # Free Tier context for the allocation screen (PART C): how many lesson-plan
    # units remain this calendar month and how many indicators this scheme has.
    from ..entitlements import resolve_entitlement, lesson_quota_status
    quota = lesson_quota_status(db, user, resolve_entitlement(db, user))
    report["lesson_quota"] = quota
    # Only genuine indicator allocations are teacher-SELECTABLE under the
    # quota. Nursery-style week-unit allocations carry an empty indicator code
    # (the source has none — never fabricated); advertising them as selectable
    # would dead-end the generate button, because a selection can never be
    # made. The generate endpoint already exempts indicatorless schemes from
    # the selection requirement.
    report["selectable_indicators"] = [
        {
            "indicator_code": a.indicator_code,
            "indicator_description": a.indicator_description,
            "source_week": a.week_number,
            "teaching_week": a.teaching_week or a.week_number,
        }
        for a in sorted(coverage.allocations, key=lambda x: x.lesson_sequence)
        if a.indicator_code
    ] if quota.get("enforced") else []

    # Per-lesson review seeds + any drafts the teacher already saved (Section H).
    # Source fields are read-only; editable fields start from the draft when one
    # exists, otherwise empty for the teacher to fill before generation.
    drafts = data_service.get_lesson_review_drafts(db, scheme_id, user.id) or {}
    report["lesson_review_drafts"] = drafts
    report["lesson_review"] = [
        {
            "lesson_sequence": a.lesson_sequence,
            "indicator_code": a.indicator_code,
            "indicator_description": a.indicator_description,
            "content_standard_code": a.content_standard_code,
            "content_standard": a.content_standard_description,
            "strand": a.strand,
            "sub_strand": a.sub_strand,
            "source_week": a.week_number,
            "week_ending": a.week_ending.isoformat() if a.week_ending else None,
            "week_ending_derived": bool(a.week_ending_derived),
            "teaching_week": a.teaching_week or a.week_number,
            "source_tlrs": list(a.source_resources or []),
            # Special-period rows (PART R): the review UI shows the period
            # banner and NO editable lesson fields for these.
            "is_special_period": bool(getattr(a, "is_special_period", False)),
            "special_period_label": getattr(a, "special_period_label", ""),
            "special_period_type": getattr(a, "special_period_type", ""),
            "keywords": list((drafts.get(str(a.lesson_sequence)) or {}).get("keywords") or []),
            "other_tlrs": list((drafts.get(str(a.lesson_sequence)) or {}).get("other_tlrs") or []),
            "core_competencies": list((drafts.get(str(a.lesson_sequence)) or {}).get("core_competencies") or []),
            "structured_references": list((drafts.get(str(a.lesson_sequence)) or {}).get("structured_references") or []),
            "wapef_deep_hope": (drafts.get(str(a.lesson_sequence)) or {}).get("wapef_deep_hope", ""),
            "wapef_storyline": (drafts.get(str(a.lesson_sequence)) or {}).get("wapef_storyline", ""),
            "wapef_through_lines": list((drafts.get(str(a.lesson_sequence)) or {}).get("wapef_through_lines") or []),
            "wapef_gods_story": (drafts.get(str(a.lesson_sequence)) or {}).get("wapef_gods_story", ""),
            "remarks": (drafts.get(str(a.lesson_sequence)) or {}).get("remarks", ""),
        }
        # Special-period rows stay in the list so the review UI can show the
        # period banner; normal lessons keep their curriculum order.
        for a in sorted(
            coverage.allocations,
            key=lambda x: (0 if getattr(x, "is_special_period", False) else 1,
                           x.lesson_sequence),
        )
    ]
    return report


@router.get("/wapef/options")
async def get_wapef_options(
    user: User = Depends(get_current_user),
):
    """Approved WAPEF option lists for the review UI dropdowns.

    The four WAPEF fields are teacher-selected structured values; these are
    the only values a teacher may select, served from the canonical registry.
    """
    from ..engines.wapef_fields import wapef_options
    return wapef_options()


@router.get("/{scheme_id}/lesson-review")
async def get_lesson_review_drafts(
    scheme_id: str,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Saved pre-generation review drafts for this scheme."""
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return {"drafts": data_service.get_lesson_review_drafts(db, scheme_id, user.id)}


@router.put("/{scheme_id}/lesson-review")
async def put_lesson_review_drafts(
    scheme_id: str,
    payload: dict,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Save per-lesson review drafts before generation.

    Body: {"drafts": {"<lesson_sequence>": {keywords, other_tlrs, ...}}}
    or a single {"lesson_sequence": "3", "keywords": [...], ...} merged in.
    Source fields (source_tlrs, week_ending, indicator, content standard)
    are rejected — they stay authoritative from the document.
    """
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")

    blocked = {"source_tlrs", "week_ending", "week_ending_derived", "indicator_code",
               "content_standard", "strand", "sub_strand", "source_week"}
    raw = payload.get("drafts") if isinstance(payload.get("drafts"), dict) else payload
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Invalid lesson review payload")

    # Reject attempts to overwrite source-authoritative fields.
    for key, draft in raw.items():
        if isinstance(draft, dict):
            hit = blocked & set(draft.keys())
            if hit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source fields cannot be edited: {', '.join(sorted(hit))}",
                )

    if isinstance(payload.get("drafts"), dict):
        store = data_service.save_lesson_review_drafts(db, scheme_id, user.id, raw)
    else:
        lesson_key = str(payload.get("lesson_sequence", payload.get("key", "")))
        if not lesson_key:
            raise HTTPException(status_code=400, detail="lesson_sequence is required")
        store = data_service.save_lesson_review_draft(db, scheme_id, user.id, lesson_key, payload)
    log_event("lesson_review_saved", user_id=user.id, scheme_id=scheme_id,
              lessons=len(store))
    return {"drafts": store}


@router.get("/quota")
async def get_lesson_quota(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Server-authoritative lesson-plan quota for the current calendar month.

    The month is always derived from the server clock; the browser never
    supplies it. Used by the dashboard/generation screens to show the Free Tier
    allowance in user-facing language ("N of M used this month").
    """
    from ..entitlements import resolve_entitlement, lesson_quota_status
    return lesson_quota_status(db, user, resolve_entitlement(db, user))


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

    # ── Extraction / classification safety gate (PART E/J) ────────────────
    # A document whose subject/class could not be detected, or whose content
    # could not be reliably extracted, must NOT be presented as a usable
    # curriculum. Require explicit teacher confirmation first.
    if getattr(scheme_db, "detection_status", "") == "extraction_failed":
        raise HTTPException(
            status_code=409,
            detail=(
                "This scheme could not be reliably extracted. Review the "
                "detected structure or upload a clearer copy."
            ),
        )
    if (scheme_db.subject in ("Unknown", "", None)
            or scheme_db.class_level in ("Unknown", "", None)):
        raise HTTPException(
            status_code=409,
            detail=(
                "The subject or class could not be determined from this scheme "
                "and needs confirmation before lesson plans can be generated."
            ),
        )

    # Server-authoritative identity (PART 14/15/32). School and teacher names are
    # derived from the authenticated user's real school relationship and profile —
    # never from the request body — so a client cannot generate another school's
    # plan or impersonate a teacher. The config is corrected in place, and the
    # same values are what the export header renders.
    config.school_name = _resolve_school_name(db, user)
    config.teacher_name = _resolve_teacher_name(db, user)

    # ── AI commercial gate (checked BEFORE any generation work) ──────────
    # Commercial entitlement is enforced before any provider is constructed: an
    # installed local provider (e.g. Ollama) never grants access by itself. AI
    # OFF still generates a full deterministic lesson plan.
    if config.ai_mode != AIMode.OFF:
        require_ai_entitlement(user, db)

    # ── Server-side calendar-month lesson-plan quota (Free Tier) ─────────
    # Enforcement lives entirely on the server. The browser never supplies the
    # month. Reservation is atomic and idempotent per indicator.
    from ..entitlements import (
        resolve_entitlement, lesson_quota_status, free_tier_lesson_quota_message,
    )
    from ..usage_quota import reserve_lesson_units, release_lesson_units
    from ..models import WeekType

    resolved = resolve_entitlement(db, user)
    quota_before = lesson_quota_status(db, user, resolved)
    gen_limit = quota_before["limit"] if quota_before["enforced"] else 0

    scheme = data_service.scheme_to_model(scheme_db)

    # The full curriculum indicator list, in curriculum order (never reordered).
    ae = pipeline.allocation_engine
    include_special = bool(config.include_special_weeks)

    # ── Nursery-style schemes (no indicator source) ───────────────────────
    # WAPEF Nursery schemes legitimately have no indicator column: the weekly
    # row is the curriculum unit. Bypassing the indicator catalogue here is
    # NOT a bypass of the allocation engine — allocate() itself detects the
    # same condition and allocates one lesson per weekly row without ever
    # inventing indicator codes or content standards.
    from ..engines.allocation_engine import scheme_has_indicators
    indicatorless = not scheme_has_indicators(
        [w for w in scheme.weeks
         if include_special or w.week_type == WeekType.INSTRUCTION])

    available_codes: list = []
    if not indicatorless:
        for w in sorted(scheme.weeks, key=lambda x: x.week_number):
            if not include_special and w.week_type != WeekType.INSTRUCTION:
                continue
            for text in ae._split_indicators(w.indicators):
                code = ae._extract_indicator_code(text)
                if code not in available_codes:
                    available_codes.append(code)

    supplied_selection = list(config.selected_indicator_codes or [])
    selected_set = set(supplied_selection)
    if supplied_selection and not indicatorless and not (selected_set & set(available_codes)):
        raise HTTPException(
            status_code=400,
            detail="None of the selected indicators could be found in this scheme.",
        )

    # Preserve curriculum order regardless of the teacher's click order.
    if selected_set and not indicatorless:
        requested_codes = [c for c in available_codes if c in selected_set]
    else:
        requested_codes = list(available_codes)

    if not requested_codes and not indicatorless:
        raise HTTPException(
            status_code=422,
            detail="This scheme contains no instructional indicators to generate.",
        )

    reservation = None
    if gen_limit > 0:
        remaining = quota_before["remaining"] or 0
        if len(requested_codes) > remaining:
            # Never silently select or drop indicators — ask the teacher to
            # choose a subset no larger than the remaining allowance.
            raise HTTPException(
                status_code=403,
                detail=(
                    "This scheme contains "
                    f"{len(available_codes)} instructional indicator"
                    f"{'s' if len(available_codes) != 1 else ''}. "
                    f"You have {remaining} Free Tier lesson plan"
                    f"{'s' if remaining != 1 else ''} remaining this month. "
                    f"Select up to {remaining} indicator"
                    f"{'s' if remaining != 1 else ''} to generate now, or "
                    "upgrade to Teacher Pro for unlimited generation."
                ),
            )
        reservation = reserve_lesson_units(
            db, user.id, scheme_id, requested_codes, gen_limit
        )
        if not reservation.allowed:
            raise HTTPException(
                status_code=403,
                detail=free_tier_lesson_quota_message(0),
            )

    existing_job = data_service.get_term_config(db, scheme_id, user.id)
    if existing_job:
        # Previous generation for this scheme exists: replace its lessons
        # (regeneration must not duplicate). Regenerating already-counted
        # indicators consumes zero additional units (idempotent reservation).
        data_service.delete_lesson_plans_for_scheme(db, scheme_id, user.id)

    job_db = data_service.create_job(db, user.id, scheme_id, config)
    config.scheme_of_work_id = scheme_id
    # Generate exactly the requested indicators (all of them when no explicit
    # selection was made). The allocation engine keeps every original field.
    config.selected_indicator_codes = requested_codes

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
            drafts = data_service.get_lesson_review_drafts(db, scheme_id, user.id) or {}
            for lp in job._lesson_plans:
                _apply_lesson_review_draft(lp, drafts)
                data_service.create_lesson_plan(db, user.id, job_db.id, scheme_id, lp)

        actual_lesson_count = (
            len(job._lesson_plans) if hasattr(job, '_lesson_plans') else job.completed_lessons
        )

        # Release any reserved unit that did not become a lesson (defensive: a
        # selected indicator that had no allocation must not consume quota).
        if reservation and reservation.consumed:
            produced = set()
            for lp in (getattr(job, '_lesson_plans', None) or []):
                for c in (lp.indicator_codes or []):
                    produced.add(f"{scheme_id}:{c}")
            unused = [k for k in reservation.reserved_keys if k not in produced]
            if unused:
                release_lesson_units(db, user.id, unused, reservation.period_key)

        quota_after = lesson_quota_status(db, user)
        log_event("generation_completed", user_id=user.id, scheme_id=scheme_id, job_id=job_db.id,
                   total_lessons=job.total_lessons, lessons_billed=actual_lesson_count,
                   quota_used=quota_after.get("used"))

        # ── AI lifetime credits (separate from the lesson-plan quota) ────
        # Batch AI enrichment that actually produced AI content consumes ONE
        # lifetime AI generation per successful request (idempotent on the
        # job id). Failed generation, AI OFF, or a fully deterministic
        # fallback never consumes AI credits. Local Ollama cannot bypass this.
        ai_credit_remaining = None
        if config.ai_mode != AIMode.OFF and getattr(job, "ai_enrichment_succeeded", 0) > 0:
            ai_credit_remaining = consume_ai_generation(
                user, db, request_id=job_db.id,
            )
            log_event("ai_generation_consumed", user_id=user.id, job_id=job_db.id,
                      provider_batch=True, remaining=ai_credit_remaining)

        # Report the ACTUAL AI mode/provider that was used for this job, so the
        # UI can never claim "AI" while the backend generated deterministically.
        from ..engines.ai_provider import (
            resolve_provider_mode, get_provider, provider_status, NAMED_PROVIDERS,
        )
        ai_lessons = int(getattr(job, "ai_enrichment_succeeded", 0) or 0)
        ai_info = {
            "mode": config.ai_mode.value,
            "active": False,
            "provider": None,
            "state": "OFF" if config.ai_mode == AIMode.OFF else "NOT_CONFIGURED",
            "lessons_ai": ai_lessons,
            "lessons_deterministic": max(job.completed_lessons - ai_lessons, 0),
            "reason": None,
        }
        if config.ai_mode != AIMode.OFF:
            resolved = resolve_provider_mode(config.ai_mode)
            if resolved != "OFF":
                prov = get_provider(resolved)
                ai_info["provider"] = prov.get_name() if prov else None
                ai_info["provider_key"] = resolved if resolved in NAMED_PROVIDERS else None
                ai_info["state"] = provider_status(prov)
                ai_info["active"] = bool(prov and prov.is_available())
            if not ai_info["active"]:
                ai_info["reason"] = (
                    "No usable AI provider was available; every lesson was "
                    "generated by the deterministic engine."
                )
        else:
            ai_info["reason"] = "AI is off — lessons come from the deterministic engine."

        return {
            "job_id": job_db.id,
            "status": job.status.value,
            "total_lessons": job.total_lessons,
            "completed_lessons": job.completed_lessons,
            "generated_indicator_codes": requested_codes,
            "quota": quota_after,
            "ai_credits_remaining": ai_credit_remaining,
            "ai": ai_info,
        }

    except HTTPException:
        if reservation and reservation.consumed:
            release_lesson_units(db, user.id, reservation.reserved_keys, reservation.period_key)
        raise
    except Exception as e:
        # A failed generation must not consume quota.
        if reservation and reservation.consumed:
            release_lesson_units(db, user.id, reservation.reserved_keys, reservation.period_key)
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
            snapshot = job.config_snapshot or {}
            return {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "total_lessons": job.total_lessons,
                "completed_lessons": job.completed_lessons,
                "failed_lessons": job.failed_lessons,
                "error_message": job.error_message,
                # The template the lessons were actually generated with, so a
                # reloaded generate page exports with the same form instead of
                # silently falling back to the level default (a WAPEF lesson
                # would otherwise export onto a GES sheet).
                "template_id": snapshot.get("template_id"),
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


def _consume_download_token(token: Optional[str], user_id: Optional[str] = None) -> Optional[dict]:
    """Pop a valid, unexpired token; else None.

    ``user_id`` is optional: the browser reaches this URL by *navigation* and
    cannot attach a Bearer header, so the single-use token itself is the
    credential (a presigned URL). When an authenticated identity IS present it
    must still match the issuing user, so an authenticated caller can never
    consume another user's token.
    """
    if not token:
        return None
    entry = _DOWNLOAD_TOKENS.pop(token, None)
    if not entry:
        return None
    if user_id is not None and entry["user_id"] != user_id:
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
    if fmt not in ("docx", "pdf", "zip", "xlsx"):
        raise HTTPException(status_code=400, detail="Unsupported format")

    # ── Entitlement gate: ZIP export requires Pro or school license ────────
    # The UI's export buttons all go through this one-time URL path, so the
    # gate has to live here too — on the legacy /export/zip route alone a
    # Free Tier teacher received a real zip through the active UI path.
    if fmt == "zip":
        from ..entitlements import can_export_zip
        allowed, reason = can_export_zip(user, db)
        if not allowed:
            raise HTTPException(status_code=403, detail=reason)

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'
    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    if fmt == "docx":
        custom_structure = _custom_structure_for(db, user.id, template_id)
        if custom_structure is not None:
            log_event("custom_template_export", user_id=user.id, job_id=job_id)
            prefs = data_service.get_preferences(db, user.id)
            snapshot = job.config_snapshot or {}
            render_context = {
                "term": scheme_db.term if scheme_db and scheme_db.term else None,
                "academic_term": snapshot.get("term") if snapshot else None,
                "period": (prefs.default_period if prefs else "")
                          or snapshot.get("period", "")
                          or (lp_models[0].period if lp_models else ""),
            }
            out = await _run_pipeline(
                pipeline.export_docx_combined_custom, lp_models, custom_structure,
                Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
                render_context,
            )
        else:
            out = await _run_pipeline(
                pipeline.export_docx_combined, "", lp_models, tt,
                Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
                template_id=template_id)
        media_type = ("application/vnd.openxmlformats-officedocument"
                      ".wordprocessingml.document")
        filename = f"Lesson_Plans_{scheme_label}.docx"
    elif fmt == "zip":
        custom_structure = _custom_structure_for(db, user.id, template_id)
        if custom_structure is not None:
            log_event("custom_template_export", user_id=user.id, job_id=job_id)
        render_context = {"term": scheme_db.term} if scheme_db and scheme_db.term else {}
        out = await _run_pipeline(
            pipeline.export_zip, lp_models, tt,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.zip"),
            template_id=template_id, structure=custom_structure,
            context=render_context)
        media_type = "application/zip"
        filename = f"Lesson_Plans_{scheme_label}.zip"
    elif fmt == "xlsx":
        out = await _run_pipeline(
            pipeline.export_xlsx, lp_models,
            Path(f"exports/{user.id}/{job_id}/register.xlsx"))
        media_type = ("application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet")
        filename = f"Lesson_Register_{scheme_label}.xlsx"
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
    user: Optional[User] = Depends(get_optional_user),
):
    """Deliver a pre-validated export as a native browser download.

    This is the URL the browser navigates to. It answers
    ``Content-Disposition: attachment`` with the correct media type so the
    browser (or a download manager) owns the transfer — there is no JS body
    read on the page, so a successful handoff cannot surface as a false
    "Failed to fetch". Auth still applies: the token is user-bound and
    single-use, so it cannot be shared or replayed. A plain navigation carries
    no Bearer header, so the token itself is the credential; when an
    authenticated identity is supplied it must match the issuing user.
    """
    entry = _consume_download_token(token, user.id if user else None)
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


def _apply_lesson_review_draft(lp, drafts: dict) -> None:
    """Apply teacher-saved pre-generation review fields onto a built lesson.

    The four editable review fields plus the four WAPEF teacher-selected
    structured fields are written. source_tlrs, indicator, content standard,
    strand and week_ending remain whatever the deterministic builder produced
    from the source document (Section P authority). WAPEF selections are
    normalized through the approved option lists — only approved values persist.
    """
    if not drafts:
        return
    draft = drafts.get(str(getattr(lp, "lesson_sequence", "")))
    if not draft:
        codes = list(getattr(lp, "indicator_codes", None) or [])
        draft = drafts.get(codes[0]) if codes else None
    if not isinstance(draft, dict):
        return
    if any(k in draft for k in (
            "wapef_deep_hope", "wapef_storyline", "wapef_through_lines",
            "wapef_gods_story")):
        from ..engines.wapef_fields import normalize_wapef_payload
        canonical = normalize_wapef_payload(draft)
        lp.wapef_deep_hope = canonical["deep_hope"]
        lp.wapef_storyline = canonical["storyline"]
        lp.wapef_through_lines = canonical["through_lines"]
        lp.wapef_gods_story = canonical["gods_story"]
    if "remarks" in draft:
        lp.remarks = str(draft.get("remarks") or "")
    if "keywords" in draft:
        lp.keywords = list(draft.get("keywords") or [])
    if "other_tlrs" in draft:
        lp.other_tlrs = list(draft.get("other_tlrs") or [])
        # Keep the display union in sync without touching source_tlrs.
        union = list(getattr(lp, "source_tlrs", None) or [])
        for r in lp.other_tlrs:
            if r and r.lower() not in [x.lower() for x in union]:
                union.append(r)
        for r in (getattr(lp, "teaching_learning_resources", None) or []):
            if r.lower() in [x.lower() for x in union]:
                continue
            # Activity extras stay; only rewrite when source+other already cover.
        lp.teaching_learning_resources = union
    if "core_competencies" in draft:
        lp.core_competencies = list(draft.get("core_competencies") or [])
    if "structured_references" in draft:
        refs = [
            ReferenceEntry(**r) if isinstance(r, dict) else r
            for r in (draft.get("structured_references") or [])
        ]
        # PART L/M: only NON-EMPTY references persist. The UI shows 3 empty
        # slots by default; untouched/blank slots must never be stored as
        # empty objects on the lesson.
        refs = [r for r in refs if (getattr(r, "title", "") or "").strip()]
        lp.structured_references = refs
        labels = []
        for entry in refs:
            label = entry.title or entry.type
            if label and label.lower() not in [x.lower() for x in labels]:
                labels.append(label)
        if labels:
            lp.references = labels


def _serialize_lesson(lp) -> dict:
    from ..database import LessonPlanDB
    return {
        "id": lp.id,
        "scheme_id": lp.scheme_id,
        "job_id": lp.job_id,
        "week_number": lp.week_number,
        "source_week": lp.week_number,
        "week_ending": (
            lp.week_ending.isoformat()
            if getattr(lp, "week_ending", None)
            else None
        ),
        "week_ending_derived": bool(getattr(lp, "week_ending_derived", False)),
        "teaching_week": getattr(lp, "teaching_week", None) or lp.week_number,
        "carry_forward": bool(getattr(lp, "carry_forward", False)),
        "lesson_sequence": lp.lesson_sequence,
        "lesson_date": lp.lesson_date.isoformat() if lp.lesson_date else None,
        "lesson_number": lp.lesson_number,
        "period": getattr(lp, "period", "") or "",
        # Special-period metadata (PART R): the review page uses this to render
        # the period banner instead of fake curriculum fields.
        "special_period_label": getattr(lp, "special_period_label", "") or "",
        "special_period_type": getattr(lp, "special_period_type", "") or "",
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
        "wapef_deep_hope": getattr(lp, "wapef_deep_hope", "") or "",
        "wapef_storyline": getattr(lp, "wapef_storyline", "") or "",
        "wapef_through_lines": list(getattr(lp, "wapef_through_lines", None) or []),
        "wapef_gods_story": getattr(lp, "wapef_gods_story", "") or "",
        "remarks": getattr(lp, "remarks", "") or "",
        "learning_objectives": lp.learning_objectives or [],
        "core_competencies": lp.core_competencies or [],
        "source_tlrs": list(getattr(lp, "source_tlrs", None) or []),
        "other_tlrs": list(getattr(lp, "other_tlrs", None) or []),
        "teaching_learning_resources": lp.teaching_learning_resources or [],
        "introduction": lp.introduction,
        "main_activities": lp.main_activities or [],
        "learner_activities": lp.learner_activities or [],
        "teacher_activities": lp.teacher_activities or [],
        "assessment": lp.assessment,
        "conclusion": lp.conclusion,
        "references": lp.references or [],
        "structured_references": list(getattr(lp, "structured_references", None) or []),
        "keywords": lp.keywords or [],
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
        week_ending=getattr(lp, "week_ending", None),
        week_ending_derived=bool(getattr(lp, "week_ending_derived", False)),
        teaching_week=getattr(lp, "teaching_week", None) or lp.week_number,
        carry_forward=bool(getattr(lp, "carry_forward", False)),
        lesson_sequence=lp.lesson_sequence,
        lesson_date=lp.lesson_date,
        lesson_number=lp.lesson_number,
        period=getattr(lp, "period", "") or "",
        # Honest fallbacks only: an unknown stored class/subject must not be
        # silently relabelled as Basic 9 / Science (PART E/Y).
        class_level=ClassLevel(lp.class_level) if lp.class_level in [c.value for c in ClassLevel] else ClassLevel.UNKNOWN,
        subject=Subject(lp.subject) if lp.subject in [s.value for s in Subject] else Subject.UNKNOWN,
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
        wapef_deep_hope=getattr(lp, "wapef_deep_hope", "") or "",
        wapef_storyline=getattr(lp, "wapef_storyline", "") or "",
        wapef_through_lines=list(getattr(lp, "wapef_through_lines", None) or []),
        wapef_gods_story=getattr(lp, "wapef_gods_story", "") or "",
        remarks=getattr(lp, "remarks", "") or "",
        learning_objectives=_parse_activity_list(lp.learning_objectives, LearningObjective),
        core_competencies=lp.core_competencies or [],
        source_tlrs=list(getattr(lp, "source_tlrs", None) or []),
        other_tlrs=list(getattr(lp, "other_tlrs", None) or []),
        teaching_learning_resources=lp.teaching_learning_resources or [],
        introduction=lp.introduction,
        main_activities=_parse_activity_list(lp.main_activities, TeachingActivity),
        learner_activities=_parse_activity_list(lp.learner_activities, TeachingActivity),
        teacher_activities=_parse_activity_list(lp.teacher_activities, TeachingActivity),
        assessment=lp.assessment,
        conclusion=lp.conclusion,
        references=lp.references or [],
        structured_references=[
            ReferenceEntry(**r) if isinstance(r, dict) else r
            for r in (getattr(lp, "structured_references", None) or [])
        ],
        keywords=lp.keywords or [],
    )

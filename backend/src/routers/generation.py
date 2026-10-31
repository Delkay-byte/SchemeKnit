"""
SchemeKnit Generation Router

Production endpoints for lesson plan generation with persistence.
"""

import asyncio
import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import re
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db, SessionLocal
from ..auth import get_current_user, get_optional_user, require_teacher_workflow
from ..database import GenerationJobDB, User
from ..security import enforce_authenticated_budget
from ..service import data_service, UnsupportedLessonFieldError
from ..entitlements import require_ai_entitlement, consume_ai_generation
from ..models import (
    TermConfig, LessonPlan, Subject, ClassLevel, TemplateType, AIMode,
    ReferenceEntry, GenerationMethod,
)
from ..engines.generation_pipeline import GenerationPipeline
from ..engines.zeli_generation import ZeliGenerationError, zeli_availability
from ..ai_resource_text import (
    normalize_exact_items, normalize_resource_items, normalize_text_items,
    normalize_structured_references,
)
from ..logging_config import get_logger, log_event, log_error

router = APIRouter()
pipeline = GenerationPipeline()
logger = get_logger()


def _is_free_only(quota: dict) -> bool:
    """True when the account has no paid/referral/package credit balance."""
    state = (quota or {}).get("credits") or {}
    return not (
        int(state.get("purchased") or 0)
        + int(state.get("package") or 0)
        + int(state.get("referral") or 0)
    )

# ── Generation coordination ───────────────────────────────────────────────
# Two truly concurrent POST /generate requests for the same (owner, scheme)
# used to pass the in-flight job read before either created its job, then both
# ran and wrote duplicate lessons. The endpoint is synchronous (FastAPI
# threadpool), so the bodies really can overlap.
#
# The process-wide non-blocking lock is the cheap local gate. It cannot protect
# a multi-worker or multi-machine deployment, so PostgreSQL additionally takes
# a session-level advisory lock on a dedicated connection held for the whole
# request. The database lock is released by PostgreSQL if the process dies.
# The registry is bounded by the number of schemes a process has generated for.
_generation_locks: Dict[tuple, threading.Lock] = {}
_generation_locks_guard = threading.Lock()


def generation_lock_key(user_id: str, scheme_id: str) -> int:
    """Stable 64-bit PostgreSQL advisory-lock key for one owner + scheme.

    Keep this derivation stable: rolling-deploy workers and crash-recovery
    processes must contend on the same key. Tests pin the same contract.
    """
    digest = hashlib.sha256(
        f"schemeknit:generation:{user_id or ''}:{scheme_id or ''}".encode("utf-8")
    ).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


def _scheme_generation_lock(user_id: str, scheme_id: str) -> threading.Lock:
    key = (user_id or "", scheme_id or "")
    with _generation_locks_guard:
        lock = _generation_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _generation_locks[key] = lock
        return lock


@contextmanager
def _generation_guard(db: Session, user_id: str, scheme_id: str):
    """Hold the local + PostgreSQL generation guard for one request.

    PostgreSQL uses ``pg_try_advisory_lock`` on a dedicated connection. That
    connection is held (and the lock is session-scoped) for the entire run;
    commits in the request's own session therefore cannot release it early.
    SQLite and other local drivers keep the process lock only, which is
    sufficient for the supported single-process local/desktop path.
    """
    local_lock = _scheme_generation_lock(user_id, scheme_id)
    if not local_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=(
                "A generation for this scheme is already running. "
                "Wait for it to finish before starting another."
            ),
        )

    lock_conn = None
    lock_held = False
    key = generation_lock_key(user_id, scheme_id)
    try:
        bind = db.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect == "postgresql":
            try:
                lock_conn = bind.connect()
                lock_held = bool(lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
                ).scalar())
            except Exception as exc:
                if lock_conn is not None:
                    lock_conn.close()
                    lock_conn = None
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Generation coordination is temporarily unavailable. "
                        "Please try again."
                    ),
                ) from exc
            if not lock_held:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A generation for this scheme is already running in "
                        "another process. Wait for it to finish before "
                        "starting another."
                    ),
                )
        yield
    finally:
        if lock_conn is not None:
            try:
                if lock_held:
                    lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                    lock_conn.commit()
            except Exception as exc:  # pragma: no cover - broken connection
                # Invalidate so the pool cannot hand a connection that still
                # holds the session-level lock to a later request. Never let
                # cleanup mask the request's outcome or strand the local lock.
                log_error(
                    "generation_lock_release_failed",
                    user_id=user_id, scheme_id=scheme_id, error=str(exc),
                )
                try:
                    lock_conn.invalidate()
                except Exception:
                    pass
            finally:
                lock_conn.close()
        local_lock.release()


@contextmanager
def _job_heartbeat(job_id: str):
    """Refresh a running job's last-activity timestamp in the background.

    The generation call is synchronous and can legitimately outlive the stale
    window, so a single timestamp at start is not enough. A daemon thread uses
    its OWN SessionLocal session: it never shares the request's transaction,
    never delays the response, and cannot roll back durable work. It starts by
    waiting one interval because the caller has already written the initial
    heartbeat; short runs therefore do not touch the database from this thread.

    Heartbeat failures are logged and swallowed: a transient database hiccup
    must not fail an otherwise healthy generation. If the database is down for
    longer than the stale window, the job is genuinely unrecoverable and
    reconciliation will surface it later.
    """
    try:
        interval = max(int(get_settings().GENERATION_HEARTBEAT_SECONDS), 1)
    except Exception:
        interval = 30
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(interval):
            session = SessionLocal()
            try:
                data_service.heartbeat_job(session, job_id)
            except Exception as exc:  # pragma: no cover - broken DB
                session.rollback()
                log_error(
                    "generation_heartbeat_failed", job_id=job_id,
                    error=str(exc),
                )
            finally:
                session.close()

    thread = threading.Thread(
        target=_beat, name=f"generation-heartbeat-{job_id[:8]}", daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)


def _persist_finalization_warning(db: Session, job_db: GenerationJobDB,
                                  warning: str) -> None:
    """Record a post-commit warning on the durable job (best effort).

    The warning is additive to the existing snapshot, so planned occurrence
    ids, resume state and the config the job was generated with are preserved.
    A failure here is logged and never masks the committed result.
    """
    try:
        snapshot = dict(job_db.config_snapshot or {})
        snapshot["finalization_warning"] = warning
        data_service.update_job(
            db, job_db.id, config_snapshot=snapshot,
        )
    except Exception as exc:
        db.rollback()
        log_error(
            "generation_finalization_warning_persist_failed",
            job_id=job_db.id, error=str(exc),
        )


def _recovered_committed_response(db: Session, user: User,
                                  job_db: GenerationJobDB, scheme_id: str,
                                  error: Exception) -> Dict[str, Any]:
    """Last-resort truthful response after a committed run's finalization.

    This runs only when something outside the explicitly guarded post-commit
    steps raised. The transaction is already durable, so this must never be
    presented as a rollback or a 500. It re-reads lessons, occurrence ids and
    job state from the database and returns a recovered success with a
    warning. Any read that itself fails falls back to honest nulls.
    """
    db.rollback()
    warning = (
        "Generation completed and its lessons and lesson-plan quota are "
        "saved, but the final response could not be fully assembled. Reload "
        "the saved job to see the durable result."
    )
    log_error(
        "generation_post_commit_finalization_failed",
        user_id=user.id, scheme_id=scheme_id, job_id=job_db.id,
        error=str(error),
    )

    lessons = []
    job = None
    quota = None
    try:
        lessons = data_service.get_lesson_plans_for_scheme(
            db, scheme_id, user.id)
        job = data_service.get_job(db, job_db.id, user.id)
    except Exception:
        db.rollback()
    try:
        from ..entitlements import lesson_quota_status
        quota = lesson_quota_status(db, user)
    except Exception:
        db.rollback()
        quota = None

    try:
        total = len(lessons) if lessons else int(
            getattr(job_db, "completed_lessons", 0) or 0)
    except Exception:
        db.rollback()
        total = 0
    occurrences = sorted({
        lp.source_occurrence_id for lp in lessons
        if getattr(lp, "source_occurrence_id", "")
    })
    codes = sorted({
        code for lp in lessons for code in (lp.indicator_codes or [])
    })
    status = job.status if job is not None else "completed"
    resume_view = {
        "planned_occurrence_ids": [],
        "blocked_for_review_occurrence_ids": [],
        "resumable_occurrence_ids": [],
        "pending_occurrence_ids": [],
        "can_resume": False,
    }
    if job is not None:
        try:
            resume_view = _job_resume_view(db, job, user.id)
        except Exception:
            db.rollback()

    _persist_finalization_warning(db, job_db, warning)
    return {
        "job_id": job_db.id,
        "status": status,
        "total_lessons": total,
        "completed_lessons": total,
        "generated_indicator_codes": codes,
        "generated_occurrence_ids": occurrences,
        "rejected_occurrence_ids": [],
        "pending_occurrence_ids": resume_view["pending_occurrence_ids"],
        "planned_occurrence_ids": resume_view["planned_occurrence_ids"],
        "resumable_occurrence_ids": resume_view["resumable_occurrence_ids"],
        "preserved_occurrence_ids": [],
        "blocked_for_review_occurrence_ids":
            resume_view["blocked_for_review_occurrence_ids"],
        "already_generated_occurrence_ids": occurrences,
        "resumed": False,
        "resumed_from_job_id": None,
        "quota": quota,
        "ai_credits_remaining": None,
        "ai": {
            "mode": "UNKNOWN", "active": False, "provider": None,
            "state": "UNKNOWN",
            "reason": "Finalization was incomplete; reload the saved job.",
        },
        "quality": None,
        "recovered": True,
        "warning": warning,
        "finalization": {
            "state": "completed_with_warning",
            "warnings": ["response finalization failed"],
        },
    }


class ResumeGenerationRequest(BaseModel):
    """The durable job whose eligible pending occurrences should be resumed."""

    job_id: str


def _config_from_snapshot(snapshot: Dict[str, Any]) -> TermConfig:
    """Rebuild a TermConfig from a stored job snapshot without inventing fields."""
    fields = {
        key: value
        for key, value in (snapshot or {}).items()
        if key in TermConfig.model_fields
    }
    return TermConfig.model_validate(fields)


def _allocations_for_config(scheme, config: TermConfig):
    """The same deterministic allocation the original run used."""
    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme.weeks, config.holidays)
    coverage = pipeline.allocation_engine.allocate(
        scheme.weeks, calendar, config,
        bool(config.include_special_weeks),
    )
    return list(coverage.allocations)


def _planned_scope(
    *,
    allocations: List[Any],
    selected_occurrence_ids: List[str],
    requested_codes: List[str],
    indicatorless: bool,
) -> tuple[List[str], List[str]]:
    """Return (planned, blocked-for-review) occurrence ids for this run.

    Planned excludes special periods and rows the allocation engine marked
    needs_review; blocked names the latter so the API never silently drops
    them. Explicit occurrence selections are already gated upstream, so their
    blocked list is empty in practice.
    """
    if selected_occurrence_ids:
        scope = [
            a for a in allocations
            if a.source_occurrence_id in set(selected_occurrence_ids)
        ]
    elif indicatorless:
        scope = list(allocations)
    else:
        codes = set(requested_codes)
        scope = [a for a in allocations if a.indicator_code in codes]

    planned = sorted({
        a.source_occurrence_id for a in scope
        if a.source_occurrence_id
        and not getattr(a, "is_special_period", False)
        and not getattr(a, "needs_review", False)
    })
    blocked = sorted({
        a.source_occurrence_id for a in scope
        if a.source_occurrence_id and getattr(a, "needs_review", False)
    })
    return planned, blocked


def _job_resume_view(db: Session, job: GenerationJobDB, user_id: str) -> Dict[str, Any]:
    """Occurrence-level recovery state for a job, without re-planning it."""
    snapshot = job.config_snapshot or {}
    planned = sorted(set(
        (snapshot.get("planned_occurrence_ids") or [])
        or (snapshot.get("selected_occurrence_ids") or [])
    ))
    blocked = sorted(set(snapshot.get("blocked_for_review_occurrence_ids") or []))
    existing = {
        (getattr(lp, "source_occurrence_id", "") or "")
        for lp in data_service.get_lesson_plans_for_scheme(
            db, job.scheme_id, user_id)
    }
    existing.discard("")
    resumable = sorted(set(planned) - existing - set(blocked))
    return {
        "planned_occurrence_ids": planned,
        "blocked_for_review_occurrence_ids": blocked,
        "resumable_occurrence_ids": resumable,
        "pending_occurrence_ids": resumable,
        "can_resume": bool(resumable) and job.status in ("failed", "completed"),
    }


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


def _render_context(db, user_id: str, job, scheme_db, lp_models) -> Dict:
    """Context every export renderer resolves non-stored header fields from.

    The term the teacher configured and the timetable period are server-side;
    the school/teacher names come from the lesson rows themselves.
    """
    prefs = data_service.get_preferences(db, user_id)
    snapshot = job.config_snapshot or {}
    # Phase 5: the DATE / DAY: row must show the teacher's selected teaching
    # DAYS (never calendar dates), in weekday order. The configured snapshot
    # is the authority; an empty selection renders nothing rather than a guess.
    day_names = _teaching_day_names(snapshot.get("teaching_days") or [])
    return {
        "term": scheme_db.term if scheme_db and scheme_db.term else None,
        "academic_term": snapshot.get("term") if snapshot else None,
        "period": (prefs.default_period if prefs else "")
                  or snapshot.get("period", "")
                  or (lp_models[0].period if lp_models else ""),
        "teaching_days": day_names,
    }


_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday")


def _teaching_day_names(days) -> list:
    """Normalize configured teaching days to ordered weekday names.

    Accepts weekday ints (0=Monday, the TermConfig convention) or name
    strings; the output is always in Monday-first order and de-duplicated.
    """
    names = set()
    for d in days or []:
        if isinstance(d, bool):
            continue
        if isinstance(d, int) and 0 <= d < len(_WEEKDAY_NAMES):
            names.add(_WEEKDAY_NAMES[d])
        elif isinstance(d, str):
            probe = d.strip().lower()
            for i, name in enumerate(_WEEKDAY_NAMES):
                if probe == name.lower() or probe == name.lower()[:3]:
                    names.add(name)
    return [n for n in _WEEKDAY_NAMES if n in names]


def _resolve_export_template_id(job, lp_models, template_id) -> Optional[str]:
    """Template id an export must render with, following the teacher's choice.

    The query parameter is an explicit selection and always wins. Otherwise the
    lessons' own stored template is used: a single-lesson export must not
    silently downgrade the WAPEF form the teacher generated with to the GES
    default just because no query param was sent (``default_template_for_lessons``
    only looks at class level, so it could never see the lesson's template).

    Only ids that resolve in the built-in registry are picked up. A custom
    (teacher-built) template is therefore only ever applied when explicitly
    requested — an unknown stored id falls through rather than guessing.

    Returns None when nothing resolvable is stored, so the caller keeps its
    ``template_type`` / class-level default.
    """
    if template_id:
        return template_id

    from ..engines.template_engine import get_template_by_id
    from ..engines.wapef_template import is_wapef_template

    stored = [t for t in (getattr(lp, "template_id", None) for lp in lp_models) if t]
    unique = list(dict.fromkeys(stored))
    if len(unique) == 1 and len(stored) == len(lp_models) and get_template_by_id(unique[0]):
        return unique[0]

    snapshot = job.config_snapshot or {}
    chosen = snapshot.get("template_id")
    if chosen and get_template_by_id(chosen):
        return chosen

    # Mixed templates: the WAPEF form wins over the GES form so an export is
    # never rendered in a lower-fidelity layout than the lessons were built in.
    ordered = ([t for t in unique if is_wapef_template(t) or t.startswith("tpl-wapef")]
               + [t for t in unique if not (is_wapef_template(t) or t.startswith("tpl-wapef"))])
    for candidate in ordered:
        if get_template_by_id(candidate):
            return candidate
    return None


def resolve_term_window(config: TermConfig, weeks) -> TermConfig:
    """Fill an unset term window from the scheme's own curriculum dates.

    Real-use remediation (Defect 6/7): the teacher clearing the Term Start /
    Term End inputs used to make the whole allocation payload invalid, so BOTH
    "Quick Generate" and "Build with me" stopped at "Validation failed" even
    though the curriculum was perfectly usable. The term window is derived from
    the scheme's extracted week dates — the source stays authoritative and
    nothing is invented. A scheme without dates either is the only case that
    falls back to the server date, exactly as the model default did before.
    """
    starts = [w.start_date for w in (weeks or []) if getattr(w, "start_date", None)]
    ends = [w.end_date for w in (weeks or []) if getattr(w, "end_date", None)]
    if config.term_start_date is None:
        config.term_start_date = min(starts) if starts else date.today()
    if config.term_end_date is None:
        config.term_end_date = max(ends) if ends else config.term_start_date
    if config.term_end_date < config.term_start_date:
        config.term_end_date = config.term_start_date
    return config


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
    # Guided configuration (Phase 2): the preview reflects the plan's SAVED
    # configuration, so what the teacher reviews is what generation will use.
    # No hard gate here — the preview is how the teacher SEES the plan before
    # the configuration step; generation enforces the required fields.
    _apply_saved_lesson_config(db, scheme_db, config, user)
    # PART 3: record a teacher-confirmed class at PREVIEW time too, so the
    # preview the teacher approves is generated from the same class.
    _persist_confirmed_class(db, user, scheme_db, config)

    scheme = data_service.scheme_to_model(scheme_db)
    resolve_term_window(config, scheme.weeks)

    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme.weeks, config.holidays
    )
    coverage = pipeline.allocation_engine.allocate(
        scheme.weeks, calendar, config, config.include_special_weeks
    )
    report = pipeline.coverage_validator.generate_report(scheme.weeks, coverage)

    # ── Weekly coverage semantics (Priority 1) ───────────────────────────
    # The week table tells the teacher the truth about coverage: how many
    # curriculum occurrences the source week holds, how many periods the
    # timetable defines (context only), and how many lesson plans that means.
    # The timetable count NEVER changes the lesson count.
    from collections import defaultdict
    timetable_periods: Dict[int, int] = defaultdict(int)
    for _day in calendar.days:
        if _day.is_teaching_day and _day.week_number:
            timetable_periods[_day.week_number] += 1
    for _ws in report.get("weeks", []):
        _wn = _ws.get("week_number")
        _ws["teaching_period_count"] = timetable_periods.get(_wn, 0)
        _ws["lesson_plans_required"] = _ws.get("lesson_count", 0)

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
    # Spine-derived review state per curriculum week (Patterns 2/6): a week whose
    # extraction was uncertain is shown as "Needs review" on the allocation
    # screen. Nothing is re-parsed and nothing is invented.
    from ..curriculum.spine import classify_week_review, scheme_provides_indicators
    _scheme_weeks = list(scheme_db.weeks or [])
    week_review = {
        w.week_number: classify_week_review(w, _scheme_weeks)[0]
        for w in _scheme_weeks
    }
    week_review_reasons = {
        w.week_number: classify_week_review(w, _scheme_weeks)[1]
        for w in _scheme_weeks
    }
    # Defect 2/7: a scheme whose source has NO indicator column anywhere (the
    # WAPEF Nursery/KG shape) must not have its weeks flagged as review
    # failures on the allocation screen — the honest state is "not provided in
    # source". The indicatorless allocation path already handles these schemes.
    provides_indicators = scheme_provides_indicators(scheme_db.weeks)
    # The review row's ``lesson_sequence`` is the number the BUILT lesson will
    # carry — the ordinal among the real lessons — not the allocation index.
    # The allocation engine numbers allocations from 0 while the built lessons
    # are numbered from 1, so keying the teacher's pre-generation drafts by the
    # raw allocation index applied every row's WAPEF/keyword/reference choices
    # to the WRONG lesson (row 2's selections landed on lesson 1) and dropped
    # the first row's entirely. Special-period rows are not lessons and keep -1.
    _ordered_allocations = sorted(coverage.allocations,
                                 key=lambda x: x.lesson_sequence)
    _lesson_number: Dict[int, int] = {}
    _lesson_counter = 0
    for _a in _ordered_allocations:
        if getattr(_a, "is_special_period", False):
            _lesson_number[id(_a)] = -1
        else:
            _lesson_counter += 1
            _lesson_number[id(_a)] = _lesson_counter

    def _draft_for(alloc) -> dict:
        """The teacher's saved pre-generation draft for THIS lesson."""
        draft = drafts.get(str(_lesson_number[id(alloc)]))
        return draft if isinstance(draft, dict) else {}

    report["lesson_review"] = [
        {
            "lesson_sequence": _lesson_number[id(a)],
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
            "source_occurrence_id": (
                getattr(a, "source_occurrence_id", "") or ""),
            "source_tlrs": list(a.source_resources or []),
            # Special-period rows (PART R): the review UI shows the period
            # banner and NO editable lesson fields for these.
            "is_special_period": bool(getattr(a, "is_special_period", False)),
            "special_period_label": getattr(a, "special_period_label", ""),
            "special_period_type": getattr(a, "special_period_type", ""),
            # Teacher-editable timetable slot for THIS lesson (Pattern 1).
            # Starts from any saved draft, else blank — never invented.
            "period": _draft_for(a).get("period", ""),
            # Allocation review state: the engine flags an allocation whose
            # placement could not be confirmed (e.g. no teaching date). Special
            # periods are a real curriculum state, not a review failure.
            "needs_review": bool(getattr(a, "needs_review", False))
                            and not bool(getattr(a, "is_special_period", False)),
            # Why the row needs attention (teacher-facing, from the spine).
            "review_reasons": (
                week_review_reasons.get(a.week_number, [])
                if bool(getattr(a, "needs_review", False)) else []
            ),
            # "Why this lesson?" provenance (Patterns 3/6). Compact, teacher-facing;
            # every value comes from the stored curriculum, nothing is fabricated.
            "source_provenance": {
                "scheme": getattr(scheme_db, "filename", "") or "",
                "curriculum_source": "Teacher scheme",
                "source_week": a.week_number,
                "source_occurrence_id": (
                    getattr(a, "source_occurrence_id", "") or ""),
                "teaching_week": a.teaching_week or a.week_number,
                "strand": a.strand or "",
                "sub_strand": a.sub_strand or "",
                "content_standard": a.content_standard_description or "",
                "content_standard_code": a.content_standard_code or "",
                "indicator": a.indicator_code or "",
                "indicator_text": a.indicator_description or "",
                "carry_forward": bool(getattr(a, "carry_forward", False)),
                "source_review_status": week_review.get(a.week_number),
                "source_review_reasons": week_review_reasons.get(a.week_number, []),
                "source_provides_indicators": provides_indicators,
                "allocation": f"Week {a.teaching_week or a.week_number} \u00b7 Period "
                              f"{getattr(a, 'period_index', '')}".strip(),
            },
            # Draft fields normalize at the API boundary too: a serialized
            # string draft must never reach the UI as split characters.
            "keywords": normalize_text_items(_draft_for(a).get("keywords")),
            "other_tlrs": normalize_text_items(_draft_for(a).get("other_tlrs")),
            "core_competencies": normalize_text_items(_draft_for(a).get("core_competencies")),
            "structured_references": normalize_structured_references(_draft_for(a).get("structured_references")),
            "wapef_deep_hope": _draft_for(a).get("wapef_deep_hope", ""),
            "wapef_storyline": _draft_for(a).get("wapef_storyline", ""),
            "wapef_through_lines": normalize_text_items(_draft_for(a).get("wapef_through_lines")),
            "wapef_gods_story": _draft_for(a).get("wapef_gods_story", ""),
            "remarks": _draft_for(a).get("remarks", ""),
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


# ── Guided lesson configuration (Phase 2) ────────────────────────────────────

#: Fields the GES template requires before a plan can be generated. A field
# that is genuinely optional on the form (Reference, the timetable PERIOD
# slot) may legitimately stay blank; everything here must be either already
# saved or entered by the teacher — never invented.
LESSON_CONFIG_REQUIRED = (
    "school_name", "teacher_name", "class_size",
    "lesson_duration_minutes", "teaching_days",
)

_ALLOWED_TEACHING_DAYS = {0, 1, 2, 3, 4}  # Monday..Friday (TermConfig ints)


class LessonConfigRequest(BaseModel):
    """The teacher's per-plan lesson configuration (Configure lesson rubrics)."""
    school_name: Optional[str] = None
    teacher_name: Optional[str] = None
    class_size: Optional[int] = None
    reference: Optional[str] = None
    lesson_duration_minutes: Optional[int] = None
    periods_per_week: Optional[int] = None
    period: Optional[str] = None
    teaching_days: Optional[List[int]] = None


def _normalize_lesson_config(payload: LessonConfigRequest) -> dict:
    """Validate and normalize the configuration the teacher submitted.

    Raises 422 with a field-specific message on nonsense values; blanks stay
    blank (an optional field may legitimately be empty) and nothing is ever
    invented to make the form look complete.
    """
    errors = []
    out: dict = {}

    def _clean_str(name, value, max_len=200):
        if value is None:
            return None
        v = str(value).strip()
        if not v:
            return None
        if len(v) > max_len:
            errors.append(f"{name} is too long (max {max_len} characters).")
            return None
        return v

    out["school_name"] = _clean_str("School name", payload.school_name)
    out["teacher_name"] = _clean_str("Teacher's name", payload.teacher_name)
    out["reference"] = _clean_str("Reference", payload.reference, max_len=400)
    out["period"] = _clean_str("Period", payload.period, max_len=60)

    cs = payload.class_size
    if cs is not None:
        if not isinstance(cs, int) or isinstance(cs, bool) or cs < 1 or cs > 500:
            errors.append("Class size must be a whole number between 1 and 500.")
        else:
            out["class_size"] = cs

    dur = payload.lesson_duration_minutes
    if dur is not None:
        if not isinstance(dur, int) or isinstance(dur, bool) or dur < 20 or dur > 240:
            errors.append("Lesson duration must be a whole number between 20 and 240 minutes.")
        else:
            out["lesson_duration_minutes"] = dur

    ppw = payload.periods_per_week
    if ppw is not None:
        if not isinstance(ppw, int) or isinstance(ppw, bool) or ppw < 1 or ppw > 15:
            errors.append("Periods per week must be a whole number between 1 and 15.")
        else:
            out["periods_per_week"] = ppw

    if payload.teaching_days is not None:
        days = payload.teaching_days
        bad = [d for d in days
               if not isinstance(d, int) or isinstance(d, bool)
               or d not in _ALLOWED_TEACHING_DAYS]
        if bad:
            errors.append("Teaching days must be weekdays (Monday-Friday).")
        else:
            out["teaching_days"] = sorted(set(days))

    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    return {k: v for k, v in out.items() if v is not None}


def _saved_lesson_config(scheme_db) -> dict:
    saved = getattr(scheme_db, "lesson_config", None)
    return dict(saved) if isinstance(saved, dict) else {}


def _lesson_config_readiness(config: dict) -> dict:
    """Which REQUIRED fields the plan is still missing (never invented)."""
    missing = [name for name in LESSON_CONFIG_REQUIRED
               if not config.get(name) and config.get(name) != 0]
    return {"ready": not missing, "missing": missing}


@router.get("/{scheme_id}/lesson-config")
async def get_lesson_config(
    scheme_id: str,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """The plan's saved lesson configuration, prepopulated from what exists.

    Merge order (most specific wins): the plan's saved configuration, then
    the teacher's profile defaults (school name, duration, period,
    references), then the server-resolved identity for the authenticated
    user. A field with no applicable value anywhere is returned as null —
    the UI asks the teacher for it instead of inventing one.
    """
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    prefs = data_service.get_preferences(db, user.id)
    merged: dict = {}
    if prefs:
        if getattr(prefs, "default_school_name", None):
            merged["school_name"] = prefs.default_school_name
        if getattr(prefs, "default_lesson_duration", None):
            merged["lesson_duration_minutes"] = prefs.default_lesson_duration
        if getattr(prefs, "default_period", None):
            merged["period"] = prefs.default_period
        refs = getattr(prefs, "default_references", None) or []
        if refs:
            merged["reference"] = refs[0] if isinstance(refs[0], str) else ""
    resolved_school = _resolve_school_name(db, user)
    resolved_teacher = _resolve_teacher_name(db, user)
    if resolved_school:
        merged.setdefault("school_name", resolved_school)
    if resolved_teacher:
        merged.setdefault("teacher_name", resolved_teacher)
    merged.update(_saved_lesson_config(scheme_db))
    readiness = _lesson_config_readiness(merged)
    return {
        "config": merged,
        "ready": readiness["ready"],
        "missing": readiness["missing"],
        "required_fields": list(LESSON_CONFIG_REQUIRED),
    }


@router.put("/{scheme_id}/lesson-config")
async def put_lesson_config(
    scheme_id: str,
    payload: LessonConfigRequest,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Validate and persist the plan's lesson configuration.

    The values are saved on THIS scheme only — a per-plan override that never
    silently mutates global school settings or other plans. Configuration
    must be persisted before generation; the generate endpoint merges it.
    """
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    config = _normalize_lesson_config(payload)
    scheme_db.lesson_config = config
    db.commit()
    readiness = _lesson_config_readiness(config)
    log_event("lesson_config_saved", user_id=user.id, scheme_id=scheme_id,
              ready=readiness["ready"])
    return {
        "config": config,
        "ready": readiness["ready"],
        "missing": readiness["missing"],
    }


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


@router.post("/{scheme_id}/autopilot-selection")
async def autopilot_selection(
    scheme_id: str,
    config: TermConfig,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """What ONE "Generate my lesson plans" click would generate (Priority 3.1).

    Server-authoritative Autopilot plan: the instructional occurrences that
    are pending, safe (never needs_review), special-week-free and within the
    teacher's real monthly allowance — in source order — plus the smallest
    genuine interruptions (subject ambiguity, an unstated class, one-time
    WAPEF values, an exhausted allowance). The browser never counts, never
    ranks, and never invents the remaining allowance.
    """
    from ..engines.allocation_engine import scheme_has_indicators
    from ..engines.autopilot import (
        selection_blockers, select_autopilot_rows, wapef_autopilot_state,
    )
    from ..entitlements import (
        free_tier_lesson_quota_message, lesson_quota_status, resolve_entitlement,
    )
    from ..models import WeekType

    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")

    detection_status = getattr(scheme_db, "detection_status", "") or ""
    confirmed_class = getattr(config, "class_level", None)
    is_known = _is_known_class_level

    resolved = resolve_entitlement(db, user)
    quota = lesson_quota_status(db, user, resolved)

    scheme = data_service.scheme_to_model(scheme_db)
    resolve_term_window(config, scheme.weeks)
    # A teacher-confirmed class on a scheme that never stated one is persisted
    # exactly as the preview does it; a scheme that states its class is never
    # overridden.
    _persist_confirmed_class(db, user, scheme_db, config)

    include_special = bool(config.include_special_weeks)
    indicatorless = not scheme_has_indicators(
        [w for w in scheme.weeks
         if include_special or w.week_type in (WeekType.INSTRUCTION, WeekType.MIXED)]
    )

    # Allocation rows in source order — the same deterministic machinery the
    # week surface and the generate endpoint use; Autopilot never re-derives
    # coverage on the client.
    ae = pipeline.allocation_engine
    calendar = pipeline.calendar_engine.build_calendar(
        config, scheme.weeks, config.holidays
    )
    coverage = ae.allocate(scheme.weeks, calendar, config, include_special)

    rows = []
    for _order, a in enumerate(coverage.allocations):
        rows.append({
            "source_occurrence_id": getattr(a, "source_occurrence_id", "") or "",
            "indicator_code": getattr(a, "indicator_code", "") or "",
            "indicator_description": getattr(a, "indicator_description", "") or "",
            "strand": getattr(a, "strand", "") or "",
            "sub_strand": getattr(a, "sub_strand", "") or "",
            "week_number": int(getattr(a, "week_number", 0) or 0),
            "needs_review": bool(getattr(a, "needs_review", False)),
            "is_special_period": bool(getattr(a, "is_special_period", False)),
            "_order": _order,
        })
    # Earliest source week first, source occurrence order within the week.
    rows.sort(key=lambda r: (r["week_number"], r["_order"]))

    generated_ids = {
        (getattr(lp, "source_occurrence_id", "") or "")
        for lp in data_service.get_lesson_plans_for_scheme(db, scheme_id, user.id)
    }

    selection = select_autopilot_rows(
        rows,
        generated_ids=generated_ids,
        quota_remaining=quota.get("remaining"),
        quota_unlimited=bool(quota.get("unlimited")),
        quota_enforced=bool(quota.get("enforced")),
        indicatorless=indicatorless,
    )

    wapef = wapef_autopilot_state(config.template_id, scheme_db.lesson_review_drafts or {})
    blockers = selection_blockers(
        detection_status=detection_status,
        subject=scheme_db.subject,
        class_level=scheme_db.class_level,
        confirmed_class=confirmed_class,
        is_known_class_level=is_known,
        quota_selected_count=selection["selected_count"],
        safe_pending_count=selection["safe_pending_count"],
        pending_count=selection["pending_count"],
        needs_review_count=selection["needs_review_count"],
        wapef=wapef,
        quota_remaining=quota.get("remaining"),
        quota_message_for_empty=lambda: (
            free_tier_lesson_quota_message(0)
            if (quota.get("enforced") and not quota.get("unlimited"))
            else "No lesson plans can be generated right now."
        ),
    )

    needs_review_items = [
        {
            "source_occurrence_id": r["source_occurrence_id"],
            "indicator_code": r["indicator_code"],
            "week_number": r["week_number"],
            "indicator": r["indicator_description"],
            "review_reasons": [],
        }
        for r in selection["needs_review_items"]
    ]
    review_message = None
    if selection["needs_review_count"] > 0 and selection["safe_pending_count"] > 0:
        _s = selection["safe_pending_count"]
        _n = selection["needs_review_count"]
        review_message = (
            f"{_s} lesson plan{'s' if _s != 1 else ''} "
            f"{'is' if _s == 1 else 'are'} ready to generate. "
            f"{_n} source item{'s' if _n != 1 else ''} "
            f"{'needs' if _n == 1 else 'need'} review."
        )

    ready = bool(not blockers and selection["selected_count"] > 0)
    return {
        "ready": ready,
        "blockers": blockers,
        "review_message": review_message,
        "needs_review_items": needs_review_items[:25],
        "counts": {
            "pending_count": selection["pending_count"],
            "safe_pending_count": selection["safe_pending_count"],
            "needs_review_count": selection["needs_review_count"],
            "selected_count": selection["selected_count"],
            "generated_count": len(generated_ids - {""}),
            "quota_skipped_count": len(selection["quota_skipped"]),
        },
        "selected_occurrence_ids": selection["selected_occurrence_ids"],
        "selected_indicator_codes": selection["selected_indicator_codes"],
        "selected_rows": [
            {
                "source_occurrence_id": r["source_occurrence_id"],
                "indicator_code": r["indicator_code"],
                "week_number": r["week_number"],
                "topic": (r["sub_strand"] or r["strand"] or r["indicator_description"])[:120],
                "indicator": r["indicator_description"],
            }
            for r in selection["selected"]
        ],
        "quota": quota,
        "wapef": wapef,
        "template_id": config.template_id or None,
        "scheme_id": scheme_id,
    }


@router.post("/{scheme_id}/generate")
def generate_lesson_plans(
    scheme_id: str,
    config: TermConfig,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Synchronous endpoint so FastAPI runs the blocking pipeline off-loop.

    The body performs synchronous DB and CPU work; declaring it ``async def``
    blocked the event loop for the whole run. It now runs in the threadpool,
    which makes the process lock below necessary and correct.
    """
    with _generation_guard(db, user.id, scheme_id):
        return _generate_lesson_plans(scheme_id, config, user, db)


def _generate_lesson_plans(
    scheme_id: str,
    config: TermConfig,
    user: User,
    db: Session,
    existing_job: Optional[GenerationJobDB] = None,
    resume: bool = False,
):
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    if not resume:
        enforce_authenticated_budget(user.id, "generate")

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
    # PART 3: a teacher-confirmed value satisfies a detection gap. When the
    # scheme never stated the class, the ONLY acceptable source is the value the
    # teacher explicitly chose on this request (validated against the canonical
    # class-level catalogue). A client-supplied value can never OVERRIDE a class
    # the scheme actually states, and "Unknown" is never accepted as a class.
    _UNDETERMINED = ("Unknown", "", None)
    if scheme_db.subject in _UNDETERMINED:
        raise HTTPException(
            status_code=409,
            detail=(
                "The subject could not be determined from this scheme and needs "
                "confirmation before lesson plans can be generated."
            ),
        )
    if scheme_db.class_level in _UNDETERMINED:
        _confirmed = (getattr(config, "class_level", "") or "").strip()
        if not _confirmed or _confirmed == "Unknown" or not _is_known_class_level(_confirmed):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The class could not be determined from this scheme. "
                    "Select the class this scheme is for, then try again."
                ),
            )
        scheme_db.class_level = _confirmed
        log_event("class_level_confirmed", user_id=user.id, scheme_id=scheme_id,
                  class_level=_confirmed)
        db.commit()

    # Server-authoritative identity (PART 14/15/32). School and teacher names are
    # derived from the authenticated user's real school relationship and profile —
    # never from the request body — so a client cannot generate another school's
    # plan or impersonate a teacher. The config is corrected in place, and the
    # same values are what the export header renders.
    config.school_name = _resolve_school_name(db, user)
    config.teacher_name = _resolve_teacher_name(db, user)

    # Guided lesson configuration (Phase 2): the plan's SAVED configuration —
    # confirmed by the teacher through "Configure lesson rubrics" — is the
    # authority for class size, duration, period allocation, teaching days,
    # reference and the per-plan name overrides. A materially different
    # configuration must never reuse a lesson generated with old settings, so
    # the merged values below feed both the builder and the job snapshot.
    _apply_saved_lesson_config(db, scheme_db, config, user)
    _require_lesson_config(config)

    # ── AI commercial gate (checked BEFORE any generation work) ──────────
    # Commercial entitlement is enforced before any provider is constructed: an
    # installed local provider (e.g. Ollama) never grants access by itself. AI
    # OFF still generates a full deterministic lesson plan.
    if config.ai_mode != AIMode.OFF:
        require_ai_entitlement(user, db)

    # ── Generate with Zeli: configuration gate BEFORE any quota reservation ─
    # A missing key/disabled method must produce a clear unconfigured state and
    # charge nothing. Standard generation is untouched and stays usable.
    if config.generation_method == GenerationMethod.ZELI:
        require_ai_entitlement(user, db)
        zeli_state = zeli_availability()
        if not zeli_state.get("available"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Generate with Zeli is not available right now. No lesson "
                    "plans were saved and no lesson-plan quota was used. "
                    "Choose Standard generation, or try again later."
                ),
            )

    # ── Server-side calendar-month lesson-plan quota (Free Tier) ─────────
    # Enforcement lives entirely on the server. The browser never supplies the
    # month. Reservation is atomic and idempotent per indicator.
    from ..entitlements import (
        resolve_entitlement, lesson_quota_status, free_tier_lesson_quota_message,
    )
    from ..usage_quota import charged_indicator_codes
    from .. import credits as credit_service
    from ..models import WeekType

    resolved = resolve_entitlement(db, user)
    quota_before = lesson_quota_status(db, user, resolved)

    scheme = data_service.scheme_to_model(scheme_db)
    resolve_term_window(config, scheme.weeks)

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
         if include_special or w.week_type in (WeekType.INSTRUCTION, WeekType.MIXED)])

    available_codes: list = []
    if not indicatorless:
        for w in sorted(scheme.weeks, key=lambda x: x.week_number):
            if not include_special and w.week_type not in (WeekType.INSTRUCTION, WeekType.MIXED):
                continue
            for text in ae._split_indicators(w.indicators):
                code = ae._extract_indicator_code(text)
                if code not in available_codes:
                    available_codes.append(code)

    supplied_selection = list(config.selected_indicator_codes or [])
    selected_set = set(supplied_selection)
    selected_occ = [str(o) for o in (getattr(config, "selected_occurrence_ids", None) or []) if o]
    selected_occ = list(dict.fromkeys(selected_occ))

    # ── Occurrence-level selection (Priority 3) ─────────────────────────────
    # "[Generate lesson]" targets EXACTLY one source occurrence — one row of
    # one source week. Indicator codes alone cannot express that when the same
    # code repeats across weeks, so when occurrence ids are supplied they are
    # the AUTHORITY: each is resolved to its allocation with the same
    # deterministic machinery the preview uses, and quota is reserved for
    # exactly the codes those occurrences carry.
    resolved_by_occ: dict = {}
    # Every allocation in the scheme, used after the run to report which
    # occurrences remain pending (never silently implying a full success).
    _all_allocations: list = []
    if selected_occ:
        _cal = pipeline.calendar_engine.build_calendar(
            config, scheme.weeks, config.holidays
        )
        _cov = ae.allocate(scheme.weeks, _cal, config, include_special)
        _all_allocations = list(_cov.allocations)
        resolved_by_occ = {
            a.source_occurrence_id: a
            for a in _cov.allocations
            if a.source_occurrence_id
        }
        missing = [o for o in selected_occ if o not in resolved_by_occ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "None of the selected lessons could be found in this scheme."
                    if len(missing) == len(selected_occ)
                    else "Some of the selected lessons could not be found in this scheme."
                ),
            )
        # Server-side needs_review gate (backlog item 5). The Autopilot plan
        # already excludes uncertain occurrences, but /generate is a public
        # surface and must never silently generate a placement the allocation
        # engine could not confirm — a client-supplied id cannot bypass it.
        unsafe = [
            o for o in selected_occ
            if bool(getattr(resolved_by_occ[o], "needs_review", False))
        ]
        if unsafe:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Some selected lessons are flagged for review and cannot "
                    "be generated automatically. Review them first, then "
                    "generate the confirmed lessons."
                ),
            )

    if (supplied_selection and not selected_occ and not indicatorless
            and not (selected_set & set(available_codes))):
        raise HTTPException(
            status_code=400,
            detail="None of the selected indicators could be found in this scheme.",
        )

    # Preserve curriculum order regardless of the teacher's click order.
    if selected_occ:
        chosen_allocs = [resolved_by_occ[o] for o in selected_occ]
        _chosen_codes = {
            a.indicator_code for a in chosen_allocs
            if (a.indicator_code or "").strip()
        }
        requested_codes = [c for c in available_codes if c in _chosen_codes]
    elif selected_set and not indicatorless:
        requested_codes = [c for c in available_codes if c in selected_set]
        chosen_allocs = []
    else:
        requested_codes = list(available_codes)
        chosen_allocs = []

    if not requested_codes and not indicatorless and not selected_occ:
        raise HTTPException(
            status_code=422,
            detail="This scheme contains no instructional indicators to generate.",
        )

    # ── needs_review gate for code/full selections (backlog item 5) ───────
    # The occurrence path above already rejects an explicitly selected
    # uncertain row. The code path (and the no-selection full run) is a
    # separate public surface: without this check a client could omit
    # occurrence ids and still generate a placement the allocation engine
    # could not confirm. Nothing is reserved or written when the gate fires.
    if not selected_occ:
        _gate_cal = pipeline.calendar_engine.build_calendar(
            config, scheme.weeks, config.holidays
        )
        _gate_cov = ae.allocate(scheme.weeks, _gate_cal, config, include_special)
        _all_allocations = list(_gate_cov.allocations)
        if indicatorless:
            _gate_allocs = list(_gate_cov.allocations)
        else:
            _gate_codes = set(requested_codes)
            _gate_allocs = [
                a for a in _gate_cov.allocations
                if a.indicator_code in _gate_codes
            ]
        _gate_unsafe = [
            a for a in _gate_allocs if bool(getattr(a, "needs_review", False))
        ]
        if _gate_unsafe:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{len(_gate_unsafe)} lesson placement"
                    f"{'s' if len(_gate_unsafe) != 1 else ''} in this "
                    "selection are flagged for review and cannot be "
                    "generated automatically. Review them first, then "
                    "generate the confirmed lessons."
                ),
            )

    # ── Double-submit guard (backlog item 4) ─────────────────────────────
    # A second click while this scheme is still generating must not start a
    # competing run (which would race the lesson replacement and reserve a
    # second quota). The in-flight job is returned as a 409 with its id so
    # the UI can keep polling it instead of resubmitting.
    #
    # Reclaim jobs orphaned by a hard process death first: otherwise a stale
    # "pending" row blocks this scheme until the next server restart. Only
    # jobs older than the conservative threshold are touched, so a live run
    # is never failed by this call.
    data_service.reconcile_stale_generation_jobs(db)
    for _j in data_service.list_jobs(db, user.id):
        if existing_job is not None and _j.id == existing_job.id:
            # A resume is the owner of this exact job; its failed/completed
            # state is the resume precondition, not a competing run.
            continue
        if _j.scheme_id == scheme_id and _j.status in ("pending", "processing"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A generation for this scheme is already running. "
                    f"Waiting for job {_j.id} to finish."
                ),
            )

    # ── Already-generated info (backlog item 4) ──────────────────────────
    # Which requested occurrences already have a persisted lesson, so the
    # response (and the status endpoint) can tell the UI what a re-run
    # would replace rather than silently duplicating state in the browser.
    already_generated_occurrence_ids: list = []
    _existing_by_scheme = data_service.get_lesson_plans_for_scheme(
        db, scheme_id, user.id)
    _existing_occ = {
        (getattr(lp, "source_occurrence_id", "") or "")
        for lp in _existing_by_scheme
    }
    _existing_occ.discard("")
    if selected_occ:
        already_generated_occurrence_ids = [
            o for o in selected_occ if o in _existing_occ
        ]
    elif requested_codes:
        _existing_codes = {
            c for lp in _existing_by_scheme for c in (lp.indicator_codes or [])
        }
        if set(requested_codes) <= _existing_codes:
            already_generated_occurrence_ids = sorted(_existing_occ)

    reservation = None
    # ── Credit reservation (free monthly first, then paid buckets) ───────
    # Affordability is decided on the server from the approved catalogue and
    # the user's auditable balances. A partial batch is never silently run.
    charged_codes = charged_indicator_codes(
        db, user.id, scheme_id, quota_before.get("period_key"))
    unpaid_codes = [c for c in requested_codes if c not in charged_codes]
    requested_units = len(unpaid_codes)
    available_units = int(quota_before.get("remaining") or 0)
    quota_unlimited = bool(
        quota_before.get("unlimited") or not quota_before.get("enforced"))
    if not quota_unlimited and requested_units > available_units:
        shortfall = requested_units - available_units
        raise HTTPException(
            status_code=403,
            detail=(
                f"This selection needs {requested_units} credit"
                f"{'s' if requested_units != 1 else ''} for "
                f"{requested_units} indicator-level lesson plan"
                f"{'s' if requested_units != 1 else ''}. "
                f"You have {available_units} credit"
                f"{'s' if available_units != 1 else ''} available "
                f"(shortfall: {shortfall}). Select up to {available_units} "
                "indicator(s) to generate now, or buy a package for more credits."
                + (" Adesua — Free allowance resets on the 1st of each month."
                   if _is_free_only(quota_before) else "")
                + (" This resume can be limited to the indicators you can afford."
                   if resume else "")
            ),
            headers={
                "X-Credits-Requested": str(requested_units),
                "X-Credits-Available": str(available_units),
                "X-Credits-Shortfall": str(shortfall),
            },
        )

    if not quota_unlimited and requested_units > 0:
        import hashlib as _hashlib
        _request_id = (getattr(config, "request_id", "") or "").strip()
        if _request_id:
            _idem = f"gen:{user.id}:{_request_id}"
        else:
            _fingerprint = _hashlib.sha256(
                ("|".join(sorted(unpaid_codes)) + f"|{scheme_id}|"
                 + (existing_job.id if (resume and existing_job) else "")).encode()
            ).hexdigest()[:32]
            _idem = f"gen:{user.id}:{scheme_id}:{quota_before.get('period_key')}:{_fingerprint}"
        reservation = credit_service.reserve(
            db, user.id, requested_units, _idem, scheme_id, unpaid_codes,
            period_key=quota_before.get("period_key"),
        )
        if not reservation.allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"You need {requested_units} credits but only "
                    f"{reservation.available} are available. No lesson plans "
                    "were generated and no credit was charged. Reduce the "
                    "batch or buy a package."
                ),
            )

    # ── What this run replaces (Priority 3) ────────────────────────────────
    # No selection at all = full regeneration: the run's output becomes the
    # scheme's lesson set. Any selection replaces exactly the lessons the run
    # regenerates (its occurrences, or every occurrence of its codes); every
    # other week — including teacher edits — survives. The old code asked a
    # term-config row for "existing job" before deleting, but nothing ever
    # created that row: the branch was dead, so a second generation silently
    # DUPLICATED every lesson while the UI (job-scoped) showed only the latest
    # run. Replacement now happens AFTER a successful run (below), keyed by
    # what the run actually generated.
    replace_mode = (
        "occurrence" if selected_occ
        else "codes" if (supplied_selection and not indicatorless)
        else "all"
    )

    # Generate exactly the requested indicators (all of them when no explicit
    # selection was made). The allocation engine keeps every original field.
    # The occurrence ids stay on the config as the pipeline's subset authority.
    config.scheme_of_work_id = scheme_id
    config.selected_indicator_codes = requested_codes
    config.selected_occurrence_ids = list(selected_occ)

    # Persist the occurrence identity of this run BEFORE generation. A hard
    # process death skips the endpoint's exception handlers; without this
    # snapshot a later request could not tell which occurrences the job still
    # owed. The snapshot is additive to the existing config (exports and
    # template restoration keep reading the same fields).
    _planned_ids, _blocked_ids = _planned_scope(
        allocations=_all_allocations,
        selected_occurrence_ids=selected_occ,
        requested_codes=requested_codes,
        indicatorless=indicatorless,
    )

    if existing_job is None:
        job_db = data_service.create_job(db, user.id, scheme_id, config)
    else:
        job_db = existing_job
        if job_db.owner_id != user.id or job_db.scheme_id != scheme_id:
            raise HTTPException(status_code=404, detail="Job not found")

    _snapshot = dict(config.model_dump(mode="json"))
    _snapshot["planned_occurrence_ids"] = _planned_ids
    _snapshot["blocked_for_review_occurrence_ids"] = _blocked_ids
    if existing_job is not None:
        _prior = dict(existing_job.config_snapshot or {})
        _snapshot["planned_occurrence_ids"] = sorted(
            set(_prior.get("planned_occurrence_ids") or []) | set(_planned_ids))
        _snapshot["blocked_for_review_occurrence_ids"] = sorted(
            set(_prior.get("blocked_for_review_occurrence_ids") or [])
            | set(_blocked_ids))
        _snapshot["resumed_at"] = datetime.utcnow().isoformat()
        _snapshot["resume_count"] = int(_prior.get("resume_count") or 0) + 1
    data_service.update_job(
        db, job_db.id, status="processing", error_message="",
        config_snapshot=_snapshot,
        heartbeat_at=datetime.utcnow(),
        # A resumed job may have been marked failed/completed by stale
        # reconciliation; starting it again clears the old terminal stamp.
        completed_at=None,
    )

    # Set only after the accepted lessons, replacement, rehome and unused-unit
    # release have committed as ONE transaction. From that point on the run
    # owns durable lesson rows and its quota units, so an exception handler
    # must never return the reservation (audit defect #2: a late failure used
    # to leave persisted lessons charged zero quota).
    persistence_committed = False

    try:
        # Keep this job demonstrably alive while the (synchronous) engine
        # works. Without it, a legitimate run longer than the stale window
        # could be reclaimed by a peer. The thread never shares this session.
        with _job_heartbeat(job_db.id):
            job = pipeline.generate_all(
                scheme, config,
                template_id=config.template_id,
                db=db,
                owner_id=user.id,
            )

        # generate_all() records engine errors on the job instead of raising
        # (its historical contract). A swallowed failure must NEVER reach the
        # teacher as a 200 with zero lessons: fail the request through the
        # handlers below, which return the reservation and mark the job.
        if job.status.value != "completed":
            zeli_error = getattr(job, "_zeli_error", None)
            if zeli_error is not None:
                # Classified, teacher-safe Zeli failure (429/503/504/502).
                # Nothing was persisted, so the handler below releases quota.
                raise HTTPException(
                    status_code=zeli_error.status_code,
                    detail=zeli_error.message,
                )
            raise HTTPException(
                status_code=500,
                detail="Generation failed: "
                f"{getattr(job, 'error_message', None) or 'the lesson engine could not complete this run.'}",
            )

        actual_lesson_count = (
            len(job._lesson_plans) if hasattr(job, '_lesson_plans') else job.completed_lessons
        )

        # Priority 4: the lessons the quality gate ACCEPTED (set by the gate
        # below; until then, every built lesson is a candidate). Only accepted
        # lessons are persisted, counted and quota-charged.
        accepted: List[Any] = list(getattr(job, '_lesson_plans', None) or [])
        gate_metrics: Optional[Dict[str, Any]] = None

        if hasattr(job, '_lesson_plans'):
            # ── Occurrence-scoped replacement + job merge (Priority 3) ─────
            # The run succeeded — NOW it is safe to touch the teacher's
            # existing lessons (a failure above leaves them intact). Every run
            # creates a NEW job (the AI credit is keyed by job id, so re-using
            # one would lose per-run idempotency) while the lesson set is
            # scheme-scoped: the lessons this run regenerated are removed, the
            # SURVIVORS are re-homed onto this job, and the new lessons are
            # inserted — so workspace, status, coverage and exports all read
            # the scheme's complete, deduplicated set. This replaces the dead
            # whole-scheme delete that never fired (and would have destroyed
            # teacher edits even if it had).
            #
            # Order matters: the replaced ids are snapshotted from the
            # EXISTING rows, the new lessons are inserted FIRST, and only then
            # are the old ids deleted. A failure at any point therefore leaves
            # the teacher with lessons (never zero), and a rerun of the same
            # selection heals any partial state by replacing the same ids
            # again — never by duplicating them.
            existing = data_service.get_lesson_plans_for_scheme(
                db, scheme_id, user.id
            )

            # READ-AFTER-WRITE (WAPEF save boundary): the browser issues PUT
            # /lesson-review and POST /generate as two separate requests, and
            # on production they can land on different workers. get_lesson_review_drafts
            # below re-reads the committed store (session-refresh inside), so
            # the lessons are always built from the teacher's last saved
            # review state — never a stale in-memory copy.
            drafts = data_service.get_lesson_review_drafts(db, scheme_id, user.id) or {}
            for lp in job._lesson_plans:
                _apply_lesson_review_draft(lp, drafts)

            # ── Priority 4: the deterministic quality gate ────────────────
            # Every lesson is validated in memory BEFORE any row is written.
            # A hard failure is mechanically repaired, then the lesson is
            # rebuilt with a different teaching pattern (bounded, deterministic)
            # and only the best PASSING candidate is persisted. A lesson the
            # gate cannot fix is dropped: it is never written, its reserved
            # quota unit is released below, and its existing row survives. If
            # the gate rejects the whole run the request fails, the job is
            # marked failed and the reservation is returned in full — a failed
            # generation consumes no quota and leaves no corrupted row.
            gate_report = _run_quality_gate(
                job, config, scheme_id, drafts,
                allow_rebuild=config.generation_method != GenerationMethod.ZELI,
            )
            accepted = gate_report["accepted"]
            gate_metrics = gate_report["metrics"]
            # Quality-gate rejection is an eligible provider-content failure:
            # make ONE bounded fallback attempt on the rejected lessons, then
            # re-run the same gate. Nothing is persisted before it passes.
            _rejected_ids = [
                r.lesson_id for r in gate_report["reports"]
                if not r.accepted
            ]
            if (_rejected_ids
                    and config.generation_method == GenerationMethod.ZELI
                    and pipeline.regenerate_zeli_with_fallback(
                        job, config, db, lesson_ids=_rejected_ids)):
                log_event(
                    "zeli_quality_fallback_attempted", user_id=user.id,
                    scheme_id=scheme_id, job_id=job_db.id,
                    rejected=len(_rejected_ids),
                )
                gate_report = _run_quality_gate(
                    job, config, scheme_id, drafts, allow_rebuild=False,
                )
                accepted = gate_report["accepted"]
                gate_metrics = gate_report["metrics"]
            if not accepted:
                log_event(
                    "quality_gate_run_rejected", user_id=user.id,
                    scheme_id=scheme_id, job_id=job_db.id,
                    lessons=len(job._lesson_plans),
                    hard_rejections=gate_metrics["hard_rejections"],
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Generation failed: the lesson quality gate rejected "
                        "every lesson in this run, so nothing was saved and no "
                        "lesson-plan quota was consumed. Re-run generation or "
                        "adjust the source scheme. Rejections: "
                        f"{gate_metrics['hard_rejections'] or gate_metrics['soft_rejections']}."
                    ),
                )
            log_event(
                "quality_gate_run", user_id=user.id, scheme_id=scheme_id,
                job_id=job_db.id, **gate_metrics,
            )

            # Replacement is keyed to what the run actually ACCEPTED: a lesson
            # the gate refused keeps its existing row (never zero lessons,
            # never a weak replacement displacing a good one). In the normal
            # case — every lesson accepted — this is exactly the previous
            # behaviour; it only diverges when the gate drops a lesson.
            accepted_occs = {
                lp.source_occurrence_id for lp in accepted
                if lp.source_occurrence_id
            }
            accepted_codes = {
                code for lp in accepted for code in (lp.indicator_codes or [])
            }
            accepted_weeks = {lp.week_number for lp in accepted}
            if replace_mode == "all":
                # Full regeneration: the run's accepted output is the new set.
                # Legacy rows without an occurrence id fall back to the same
                # week + code match (mirrors _replacement_ids_for_occurrences).
                replaced_ids = []
                for lp in existing:
                    occ = lp.source_occurrence_id or ""
                    if occ:
                        if occ in accepted_occs:
                            replaced_ids.append(lp.id)
                        continue
                    if accepted_codes & set(lp.indicator_codes or []):
                        replaced_ids.append(lp.id)
                    elif not (lp.indicator_codes or []) and lp.week_number in accepted_weeks:
                        replaced_ids.append(lp.id)
            elif replace_mode == "occurrence":
                replaced_ids = _replacement_ids_for_occurrences(
                    existing,
                    accepted_occs & set(config.selected_occurrence_ids),
                    [a for a in chosen_allocs
                     if a.source_occurrence_id in accepted_occs],
                )
            else:  # codes: every occurrence of the accepted selected codes
                code_set = set(config.selected_indicator_codes) & accepted_codes
                replaced_ids = [
                    lp.id for lp in existing
                    if code_set & set(lp.indicator_codes or [])
                ]

            for lp in accepted:
                data_service.create_lesson_plan(
                    db, user.id, job_db.id, scheme_id, lp, commit=False)

            data_service.delete_lesson_plans_by_ids(
                db, user.id, replaced_ids, commit=False)
            data_service.rehome_lesson_plans_for_scheme(
                db, scheme_id, user.id, job_db.id, commit=False
            )

            # Commit exactly the credits that paid for ACCEPTED lessons and
            # refund any reserved unit that did not become a lesson.
            if reservation is not None and reservation.charged:
                produced_codes = set()
                for lp in accepted:
                    for c in (lp.indicator_codes or []):
                        produced_codes.add(c)
                credit_service.commit(db, reservation, produced_codes,
                                      commit=False)

            # Cumulative totals: after any partial run this job represents the
            # scheme's complete lesson set — which is exactly what
            # get_lesson_plans_for_job (workspace/status/coverage/exports)
            # returns, so the numbers the teacher sees match the lessons.
            scheme_total = data_service.count_lessons_for_scheme(
                db, scheme_id, user.id
            )
            _job_snapshot = dict(job_db.config_snapshot or {})
            if config.generation_method == GenerationMethod.ZELI:
                _job_snapshot["zeli_provider"] = {
                    "primary_provider": getattr(job, "_zeli_primary_provider", None),
                    "primary_model": getattr(job, "_zeli_primary_model", None),
                    "fallback_provider": getattr(job, "_zeli_fallback_provider", None),
                    "fallback_model": getattr(job, "_zeli_fallback_model", None),
                    "fallback_used": bool(getattr(job, "_zeli_fallback_used", False)),
                    "primary_error": getattr(job, "_zeli_primary_error", None),
                    "cache_hits": int(getattr(job, "_zeli_cache_hits", 0) or 0),
                    "external_calls": int(getattr(job, "_zeli_fresh_calls", 0) or 0),
                    "attempts": list(getattr(job, "_zeli_attempts", []) or []),
                }
            # The terminal job state commits WITH the lessons, replacement,
            # rehome and unused-unit release. Previously the job was marked
            # completed in a separate earlier commit, so a hard failure during
            # persistence could leave a "completed" job with no lessons.
            data_service.update_job(db, job_db.id,
                status=job.status.value,
                total_lessons=scheme_total,
                completed_lessons=scheme_total,
                progress=100,
                heartbeat_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                config_snapshot=_job_snapshot,
                commit=False,
            )
            db.commit()
            persistence_committed = True
        else:
            scheme_total = actual_lesson_count
            # Legacy engines without an in-memory lesson list still expose a
            # terminal job, but this update does not make the run's lesson
            # transaction durable; a later failure may still release units.
            data_service.update_job(
                db, job_db.id,
                status=job.status.value,
                total_lessons=scheme_total,
                completed_lessons=scheme_total,
                progress=100,
                heartbeat_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )

        # Only accepted lessons are billed (Priority 4: a gate-rejected lesson
        # consumes nothing).
        actual_lesson_count = len(accepted)

        # ── Honest batch semantics (backlog item 4E) ─────────────────────
        # Name exactly what was produced, what the gate refused (and which
        # therefore stays pending for a retry), and what remains ungenerated.
        # A successful HTTP response must never make a dropped/unstarted
        # lesson look generated.
        _accepted_occurrences = {
            lp.source_occurrence_id for lp in accepted
            if getattr(lp, "source_occurrence_id", "")
        }
        _candidate_occurrences = {
            lp.source_occurrence_id
            for lp in (getattr(job, "_lesson_plans", None) or [])
            if getattr(lp, "source_occurrence_id", "")
        }
        rejected_occurrence_ids = sorted(
            _candidate_occurrences - _accepted_occurrences)
        _pending_pool = {
            a.source_occurrence_id for a in _all_allocations
            if a.source_occurrence_id
            and not getattr(a, "is_special_period", False)
            and not getattr(a, "needs_review", False)
        }
        pending_occurrence_ids = sorted(
            _pending_pool - _accepted_occurrences - _existing_occ)

        # The durable resume scope: the plan persisted on this job, intersected
        # with occurrences still present in the scheme. This is deliberately
        # narrower than ``pending_occurrence_ids`` above: the latter also names
        # quota-skipped/unselected scheme occurrences for the UI's honest
        # whole-scheme summary, but resume must never silently expand the batch
        # the teacher originally approved.
        _batch_planned = set(
            (job_db.config_snapshot or {}).get("planned_occurrence_ids")
            or _planned_ids)
        _known_ids = {
            a.source_occurrence_id for a in _all_allocations
            if a.source_occurrence_id
        }
        _resumable = sorted(
            (_batch_planned & _known_ids)
            - _accepted_occurrences
            - _existing_occ
            - set(_blocked_ids)
        )
        _preserved = sorted(_batch_planned & _existing_occ)

        # Release any reserved unit that did not become a lesson (defensive: a
        # selected indicator that had no allocation must not consume quota).
        # Priority 4: a unit is only "produced" by an ACCEPTED lesson — one the
        # quality gate refused releases its unit (gate failure = 0 consumed).
        # The normal persistence path already did this atomically above; this
        # covers a job without an in-memory lesson set.
        if reservation is not None and reservation.charged and not persistence_committed:
            produced_codes = set()
            for lp in accepted:
                for c in (lp.indicator_codes or []):
                    produced_codes.add(c)
            credit_service.commit(db, reservation, produced_codes)

        # Everything below this line is AFTER the atomic lesson/quota commit.
        # It can enrich the response but must never turn durable work into a
        # 500. Each step degrades independently; failures are logged with
        # detail server-side and exposed only as a safe warning.
        finalization_warnings: List[str] = []

        def _finalization_failure(step: str, exc: Exception) -> None:
            # Clear a failed statement/aborted PostgreSQL transaction before
            # the next safe read. Already committed rows are untouched.
            db.rollback()
            finalization_warnings.append(step)
            log_error(
                "generation_finalization_failed",
                user_id=user.id, scheme_id=scheme_id, job_id=job_db.id,
                step=step, error=str(exc),
            )

        quota_after = None
        try:
            quota_after = lesson_quota_status(db, user)
        except Exception as exc:
            _finalization_failure("lesson quota status could not be read", exc)
            # The reservation already knows what this run charged. Reporting it
            # is more truthful than a null quota; unlimited runs stay null-free
            # too (as_quota marks them unlimited).
            if reservation is not None:
                quota_after = reservation.as_quota()

        try:
            log_event(
                "generation_completed", user_id=user.id, scheme_id=scheme_id,
                job_id=job_db.id, total_lessons=job.total_lessons,
                lessons_billed=actual_lesson_count,
                quota_used=(quota_after or {}).get("used"),
            )
        except Exception as exc:
            _finalization_failure("completion logging failed", exc)

        # ── AI lifetime credits (separate from the lesson-plan quota) ────
        # Batch AI generation that actually produced AI content consumes ONE
        # AI generation per successful request (idempotent on the job id).
        # Failed generation, AI OFF without Zeli, or a fully deterministic
        # fallback never consumes AI credits. Local Ollama cannot bypass this.
        ai_credit_remaining = None
        _is_zeli = config.generation_method == GenerationMethod.ZELI
        # A Zeli run consumes an AI request credit only when at least one
        # lesson required a real external call. A pure cache replay (all
        # lessons served from zeli_generation_cache) consumes none.
        _ai_content_produced = (
            (config.ai_mode != AIMode.OFF
             and getattr(job, "ai_enrichment_succeeded", 0) > 0)
            or (
                _is_zeli
                and getattr(job, "ai_enrichment_succeeded", 0) > 0
                and getattr(job, "_zeli_fresh_calls", 0) > 0
            )
        )
        if _ai_content_produced:
            try:
                ai_credit_remaining = consume_ai_generation(
                    user, db, request_id=job_db.id,
                )
                try:
                    log_event(
                        "ai_generation_consumed", user_id=user.id,
                        job_id=job_db.id, provider_batch=True,
                        remaining=ai_credit_remaining,
                    )
                except Exception as exc:
                    _finalization_failure("AI usage logging failed", exc)
            except Exception as exc:
                # The lessons and lesson-plan quota are already durable. The
                # AI ledger may or may not have committed inside the failed
                # call; because it is keyed by this job id, retrying the same
                # job (resume) cannot double-consume. Report the uncertainty
                # instead of claiming a rolled-back run.
                ai_credit_remaining = None
                _finalization_failure(
                    "AI usage ledger could not be finalized", exc)

        # Report the ACTUAL generation method and provider that produced this
        # job, so the UI can never claim "Zeli" while the engine generated
        # deterministically (or vice versa).
        ai_lessons = int(getattr(job, "ai_enrichment_succeeded", 0) or 0)
        is_zeli = config.generation_method == GenerationMethod.ZELI
        ai_info = {
            "mode": config.ai_mode.value,
            "generation_method": config.generation_method.value,
            "active": bool(is_zeli and ai_lessons > 0),
            "provider": None,
            "state": (
                "CONFIGURED" if is_zeli and ai_lessons > 0
                else "NOT_CONFIGURED" if is_zeli
                else "OFF" if config.ai_mode == AIMode.OFF
                else "NOT_CONFIGURED"
            ),
            "lessons_ai": ai_lessons,
            "lessons_deterministic": max(job.completed_lessons - ai_lessons, 0),
            "reason": None,
        }
        if is_zeli:
            _fallback_used = bool(getattr(job, "_zeli_fallback_used", False))
            ai_info.update({
                "primary_provider": getattr(job, "_zeli_primary_provider", None),
                "primary_model": getattr(job, "_zeli_primary_model", None),
                "fallback_configured": bool(
                    getattr(job, "_zeli_fallback_provider", None)),
                "fallback_used": _fallback_used,
                # Only the provider/model that actually ran is reported. A
                # configured-but-unused fallback is not presented as the
                # source of this lesson.
                "fallback_provider": (
                    getattr(job, "_zeli_fallback_provider", None)
                    if _fallback_used else None),
                "fallback_model": (
                    getattr(job, "_zeli_fallback_model", None)
                    if _fallback_used else None),
                "primary_error": (
                    getattr(job, "_zeli_primary_error", None)
                    if _fallback_used else None),
                "cache_hits": int(getattr(job, "_zeli_cache_hits", 0) or 0),
                "external_calls": int(getattr(job, "_zeli_fresh_calls", 0) or 0),
                "attempts": list(getattr(job, "_zeli_attempts", []) or []),
            })
        try:
            from ..engines.ai_provider import (
                resolve_provider_mode, get_provider, provider_status, NAMED_PROVIDERS,
            )
            if is_zeli:
                # Report the provider/model that actually produced the lessons.
                produced = [
                    lp for lp in (getattr(job, "_lesson_plans", None) or [])
                    if getattr(lp, "ai_provider", "")
                ]
                if produced:
                    ai_info["provider"] = produced[0].ai_provider
                    ai_info["provider_key"] = produced[0].ai_provider
                ai_info["state"] = "CONFIGURED" if ai_lessons else "NOT_CONFIGURED"
                ai_info["reason"] = (
                    None if ai_lessons
                    else "Zeli did not produce usable lesson content for this run."
                )
            elif config.ai_mode != AIMode.OFF:
                resolved = resolve_provider_mode(config.ai_mode)
                if resolved in NAMED_PROVIDERS:
                    prov = get_provider(resolved)
                    ai_info["provider"] = prov.get_name() if prov else None
                    ai_info["provider_key"] = resolved
                    ai_info["state"] = provider_status(prov)
                    ai_info["active"] = bool(prov and prov.is_available())
                # A BASIC/ENHANCED token after resolution means NO real provider
                # was found (deterministic fallback) — never report the Mock
                # provider as "AI active" (CASE C, PART 13/14).
                if not ai_info["active"]:
                    # CASE B (PART 14): name the ACTUAL provider that was tried —
                    # including the auto-resolved one — never a generic "no AI".
                    tried = ai_info.get("provider") or resolved
                    ai_info["reason"] = (
                        f"AI provider {tried or 'configured'} was not available — "
                        "every lesson was generated by the deterministic engine."
                    )
                elif ai_lessons == 0:
                    # CASE D (PART 14/15): the provider was configured and reachable
                    # but the actual calls failed (rate limit, malformed output,
                    # quality gate) — the lessons are deterministic. Say so, and
                    # make the no-consumption explicit (PART 19).
                    prov = get_provider(resolved) if resolved in NAMED_PROVIDERS else None
                    detail = getattr(prov, "last_error", "") or "provider returned no usable content"
                    ai_info["reason"] = (
                        f"AI provider {ai_info.get('provider') or resolved} did not "
                        f"produce usable content ({detail}) — every lesson was "
                        "generated by the deterministic engine. No AI generation "
                        "was consumed."
                    )
            else:
                ai_info["reason"] = "AI is off — lessons come from the deterministic engine."
        except Exception as exc:
            ai_info = {
                "mode": config.ai_mode.value,
                "generation_method": config.generation_method.value,
                "active": False,
                "provider": None,
                "state": "UNKNOWN",
                "lessons_ai": ai_lessons,
                "lessons_deterministic": max(
                    job.completed_lessons - ai_lessons, 0),
                "reason": (
                    "AI provider status could not be finalized; "
                    "no provider claim is made for this run."
                ),
            }
            _finalization_failure(
                "AI provider status could not be finalized", exc)

        warning = None
        if finalization_warnings:
            warning = (
                "Generation completed and its lessons and lesson-plan quota "
                "are saved. Some response details could not be finalized: "
                + "; ".join(finalization_warnings)
                + ". Reload the saved job to see the durable result."
            )
            _persist_finalization_warning(db, job_db, warning)

        return {
            "job_id": job_db.id,
            "status": job.status.value,
            "total_lessons": scheme_total,
            "completed_lessons": scheme_total,
            "generated_indicator_codes": requested_codes,
            "generated_occurrence_ids": sorted(_accepted_occurrences),
            "rejected_occurrence_ids": rejected_occurrence_ids,
            "pending_occurrence_ids": pending_occurrence_ids,
            "planned_occurrence_ids": sorted(_batch_planned),
            "resumable_occurrence_ids": _resumable,
            "preserved_occurrence_ids": _preserved,
            "blocked_for_review_occurrence_ids": sorted(_blocked_ids),
            "already_generated_occurrence_ids": already_generated_occurrence_ids,
            "resumed": bool(resume),
            "resumed_from_job_id": existing_job.id if resume and existing_job else None,
            "quota": quota_after,
            "ai_credits_remaining": ai_credit_remaining,
            "ai": ai_info,
            # Priority 4: the deterministic quality gate's run metrics
            # (first-pass rate, rebuilds, rejections, teacher-ready rate).
            "quality": gate_metrics,
            "recovered": bool(finalization_warnings),
            "warning": warning,
            "finalization": {
                "state": (
                    "completed_with_warning" if finalization_warnings
                    else "completed"
                ),
                "warnings": finalization_warnings,
            },
        }

    except HTTPException:
        if not persistence_committed:
            # Clear any failed statement (PostgreSQL aborts the transaction)
            # before returning the reservation in its own transaction.
            db.rollback()
            if reservation and reservation.charged:
                credit_service.release(db, reservation)
            # The job row exists (it is created before the run); never leave
            # it "pending" forever when the run was refused after creation.
            data_service.update_job(db, job_db.id, status="failed")
        raise
    except Exception as e:
        # A failed generation must not consume quota — but only when nothing
        # was persisted. Once lessons are durable, the units that paid for them
        # stay charged; releasing here was audit defect #2.
        if not persistence_committed:
            db.rollback()
            if reservation and reservation.charged:
                credit_service.release(db, reservation)
            data_service.update_job(db, job_db.id, status="failed", error_message=str(e))
            log_error("generation_failed", user_id=user.id, scheme_id=scheme_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
        # The run committed. Any later error is a finalization problem, not a
        # rolled-back generation: recover the truthful result from durable
        # state and return a success with an explicit warning.
        return _recovered_committed_response(db, user, job_db, scheme_id, e)


@router.post("/{scheme_id}/generate/resume")
def resume_generation(
    scheme_id: str,
    request: ResumeGenerationRequest,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    """Continue the eligible pending occurrences of an existing job.

    This is intentionally not a synonym for Generate again. The original job
    is reused (including its AI-credit request identity), occurrences that
    already have a persisted lesson are excluded, and only the planned-but-
    unproduced set is sent through the normal generation, quality-gate,
    atomic-persistence and quota paths.
    """
    with _generation_guard(db, user.id, scheme_id):
        return _resume_lesson_plans(scheme_id, request.job_id, user, db)


def _resume_lesson_plans(
    scheme_id: str,
    job_id: str,
    user: User,
    db: Session,
):
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    if not scheme_db:
        raise HTTPException(status_code=404, detail="Scheme not found")
    job = data_service.get_job(db, job_id, user.id)
    if not job or job.scheme_id != scheme_id:
        raise HTTPException(status_code=404, detail="Generation job not found")
    enforce_authenticated_budget(user.id, "resume")

    if job.status in ("pending", "processing"):
        data_service.reconcile_stale_generation_jobs(db)
        db.expire(job)
        job = data_service.get_job(db, job_id, user.id)
        if job is None:
            raise HTTPException(status_code=404, detail="Generation job not found")
        if job.status in ("pending", "processing"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This generation is still running. Wait for it to finish "
                    "before resuming."
                ),
            )

    snapshot = dict(job.config_snapshot or {})
    try:
        config = _config_from_snapshot(snapshot)
    except Exception:
        raise HTTPException(
            status_code=409,
            detail=(
                "This job's original generation settings are unavailable, so "
                "it cannot be resumed safely. Start a new generation instead."
            ),
        )
    config.scheme_of_work_id = scheme_id

    scheme = data_service.scheme_to_model(scheme_db)
    allocations = _allocations_for_config(scheme, config)
    by_id = {
        a.source_occurrence_id: a for a in allocations
        if a.source_occurrence_id
    }

    planned = list(dict.fromkeys(
        snapshot.get("planned_occurrence_ids")
        or snapshot.get("selected_occurrence_ids")
        or []
    ))
    if not planned:
        # Older jobs predate the planned-occurrence snapshot. Reconstruct the
        # only safe scope they can support: their selected codes, else all
        # eligible occurrences. Unknown occurrence ids are never invented.
        codes = set(config.selected_indicator_codes or [])
        planned = [
            a.source_occurrence_id for a in allocations
            if a.source_occurrence_id
            and (not codes or a.indicator_code in codes)
        ]
    known = [occ for occ in planned if occ in by_id]
    if not known:
        raise HTTPException(
            status_code=409,
            detail=(
                "This job no longer matches the scheme's curriculum, so there "
                "is no safe occurrence set to resume. Start a new generation."
            ),
        )

    blocked = sorted({
        occ for occ in known if bool(getattr(by_id[occ], "needs_review", False))
    })
    existing = {
        (getattr(lp, "source_occurrence_id", "") or "")
        for lp in data_service.get_lesson_plans_for_scheme(
            db, scheme_id, user.id)
    }
    existing.discard("")
    pending = [
        occ for occ in known
        if occ not in existing
        and occ not in set(blocked)
        and not bool(getattr(by_id[occ], "is_special_period", False))
    ]

    # Persist the union before any work so a crash during resume is recoverable
    # too. The blocked set stays visible; it is not silently converted to work.
    prior = dict(snapshot)
    prior["planned_occurrence_ids"] = sorted(
        set(prior.get("planned_occurrence_ids") or []) | set(known))
    prior["blocked_for_review_occurrence_ids"] = sorted(
        set(prior.get("blocked_for_review_occurrence_ids") or []) | set(blocked))
    data_service.update_job(db, job.id, config_snapshot=prior)

    if not pending:
        total = data_service.count_lessons_for_scheme(db, scheme_id, user.id)
        data_service.update_job(
            db, job.id,
            status="completed" if total else "failed",
            total_lessons=total,
            completed_lessons=total,
            progress=100 if total else job.progress,
            error_message=(
                "" if total else
                "No planned occurrences can be resumed; review the scheme or "
                "start a new generation."
            ),
            completed_at=datetime.utcnow() if total else job.completed_at,
        )
        return {
            "job_id": job.id,
            "status": "completed" if total else "failed",
            "total_lessons": total,
            "completed_lessons": total,
            "generated_indicator_codes": [],
            "generated_occurrence_ids": [],
            "rejected_occurrence_ids": [],
            "pending_occurrence_ids": [],
            "planned_occurrence_ids": sorted(set(known)),
            "resumable_occurrence_ids": [],
            "preserved_occurrence_ids": sorted(set(known) & existing),
            "blocked_for_review_occurrence_ids": blocked,
            "already_generated_occurrence_ids": sorted(set(known) & existing),
            "resumed": False,
            "resumed_from_job_id": job.id,
            "quota": None,
            "ai_credits_remaining": None,
            "ai": None,
            "quality": None,
            "message": (
                "No pending lessons remain in this batch."
                if total else
                "No planned occurrence can be resumed; start a new generation."
            ),
        }

    resume_config = config.model_copy(deep=True)
    resume_config.selected_occurrence_ids = pending
    # Occurrence ids are the authority for a resume. Emptying the code list
    # prevents an old code-level selection from widening the batch.
    resume_config.selected_indicator_codes = []
    return _generate_lesson_plans(
        scheme_id, resume_config, user, db,
        existing_job=job, resume=True,
    )


@router.get("/{job_id}/status")
async def get_generation_status(
    job_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    job = data_service.get_job(db, job_id, user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("pending", "processing"):
        # A status poll is the place the UI learns a job died with the server.
        # Reclaim orphaned work after the same conservative threshold used by
        # the generate endpoint, then report the terminal status honestly.
        data_service.reconcile_stale_generation_jobs(db)
        db.expire(job)
        job = data_service.get_job(db, job_id, user.id)
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "total_lessons": job.total_lessons,
        "completed_lessons": job.completed_lessons,
        "failed_lessons": job.failed_lessons,
        "error_message": job.error_message,
        # The method that produced (or is producing) this job. Persisted in the
        # snapshot, so a status poll, reload or resume can never disagree.
        "generation_method": (job.config_snapshot or {}).get(
            "generation_method", "standard"),
        "finalization_warning": (job.config_snapshot or {}).get(
            "finalization_warning"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "coverage": {
            "total_generated_lessons": job.completed_lessons,
        },
        **_job_resume_view(db, job, user.id),
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
    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    return {
        "lesson_plans": [_serialize_lesson(lp, scheme_db) for lp in lessons],
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
    scheme_db = data_service.get_scheme(db, lp.scheme_id, user.id)
    return _serialize_lesson(lp, scheme_db)


@router.get("/lessons/{lesson_id}/provenance")
async def get_lesson_provenance(
    lesson_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """The source/alignment record for one lesson ("Why this lesson?").

    Owner-enforced: another user's lesson is never readable. A lesson with no
    resovable source still returns a truthful record (empty scheme, the stored
    week/indicator) — the panel never fabricates a source.
    """
    lp = data_service.get_lesson_plan(db, lesson_id, user.id)
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson not found")
    scheme_db = data_service.get_scheme(db, lp.scheme_id, user.id)
    from ..curriculum.spine import lesson_provenance
    return lesson_provenance(lp, scheme_db)


@router.put("/lessons/{lesson_id}")
async def update_lesson_plan(
    lesson_id: str,
    updates: dict,
    user: User = Depends(require_teacher_workflow),
    db=Depends(get_db),
):
    try:
        lp = data_service.update_lesson_plan(db, lesson_id, user.id, updates)
    except UnsupportedLessonFieldError as exc:
        raise HTTPException(
            status_code=422,
            detail="Unsupported lesson field(s): " + ", ".join(exc.fields),
        )
    if not lp:
        raise HTTPException(status_code=404, detail="Lesson not found")
    log_event("lesson_edited", user_id=user.id, lesson_id=lesson_id)
    scheme_db = data_service.get_scheme(db, lp.scheme_id, user.id)
    return _serialize_lesson(lp, scheme_db)


@router.get("/scheme/{scheme_id}/status")
async def get_latest_job_for_scheme(
    scheme_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return the most recent generation job for a scheme (so the UI can restore state)."""
    # This is the endpoint the generate page uses on load/reload. Reclaim a
    # job orphaned by a server restart here too, otherwise the page shows a
    # live-looking job and never surfaces the recovery banner.
    data_service.reconcile_stale_generation_jobs(db)
    jobs = data_service.list_jobs(db, user.id)
    for job in jobs:
        if job.scheme_id == scheme_id:
            snapshot = job.config_snapshot or {}
            # Already-generated info (backlog item 4): which source occurrences
            # already carry a persisted lesson, so the restored page can mark
            # them instead of inviting a blind duplicate submission.
            _lessons = data_service.get_lesson_plans_for_scheme(
                db, scheme_id, user.id)
            _occ = sorted({
                (getattr(lp, "source_occurrence_id", "") or "")
                for lp in _lessons
            } - {""})
            return {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "total_lessons": job.total_lessons,
                "completed_lessons": job.completed_lessons,
                "failed_lessons": job.failed_lessons,
                "error_message": job.error_message,
                "finalization_warning": (job.config_snapshot or {}).get(
                    "finalization_warning"),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                # The template the lessons were actually generated with, so a
                # reloaded generate page exports with the same form instead of
                # silently falling back to the level default (a WAPEF lesson
                # would otherwise export onto a GES sheet).
                "template_id": snapshot.get("template_id"),
                "coverage": {
                    "total_generated_lessons": job.completed_lessons,
                },
                "already_generated_occurrence_ids": _occ,
                **_job_resume_view(db, job, user.id),
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

    # In the source-occurrence model each lesson carries exactly one primary
    # indicator for ONE source occurrence, so total_indicators == total lessons
    # with an indicator.
    total_lessons = len(lessons)
    total_indicators = sum(1 for lp in lessons if lp.indicator_codes)
    indicators_duplicated = 0
    from collections import Counter
    # Duplicate detection keys on the SOURCE OCCURRENCE identity (source week
    # + indicator), never on indicator_code alone: the same code in two
    # different source weeks is two legitimate occurrences, not duplicates.
    code_counter = Counter()
    for lp in lessons:
        for c in (lp.indicator_codes or []):
            code_counter[(lp.week_number, c)] += 1
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
    enforce_authenticated_budget(user.id, "export")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'

    custom_structure = _custom_structure_for(db, user.id, template_id)
    render_context = _render_context(db, user.id, job, scheme_db, lp_models)
    # What the lessons were generated with, when the teacher picked nothing
    # here — otherwise a single-lesson export renders in the default layout.
    resolved_template_id = _resolve_export_template_id(job, lp_models, template_id)
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
        files = await _run_pipeline(pipeline.export_docx_batch, lp_models, tt, output_dir,
                                    template_id=resolved_template_id)
        out = files[0]
        download_name = out.name
    else:
        # One combined document: all lessons, each starting on a new page
        out = await _run_pipeline(
            pipeline.export_docx_combined,
            "",
            lp_models, tt,
            Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
            template_id=resolved_template_id,
            context=render_context,
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


def _render_structured_pdf(pipeline, lesson_plans, output_path: Path,
                           template_id, context) -> Path:
    """Render the lesson PDF directly with ReportLab — runs in the executor.

    This is the always-available path on hosts with no DOCX -> PDF converter.
    It is deliberately a function (not an inline lambda) so tests and operators
    can replace it with a failing implementation to exercise the 503 branch.
    """
    return pipeline.export_pdf_structured(
        lesson_plans, output_path, template_id=template_id, context=context)


async def _build_export_pdf(db, user, job, scheme_label, lp_models, tt,
                            template_id, context) -> Path:
    """Produce the job's PDF and return the path to serve.

    Two layers, both reported as controlled errors and never as a raw
    traceback or a body that only claims to be a PDF:

    * a DOCX -> PDF toolchain exists -> build the combined DOCX (the same
      document the Word download serves) and convert it. Failure here is a
      conversion failure: 500 `PDF_CONVERSION_FAILED`.
    * no toolchain (a bare server) -> render the lesson directly with the
      structured renderer, which needs no external converter. If even that
      fails the environment really is the problem: 503 with the converter
      requirement, so the teacher is told exactly what to install.
    """
    from ..engines.pdf_export import (
        PDFExportEngine, PDFConversionError, _is_real_pdf,
        PDF_CONVERTER_REQUIREMENT, PDF_CONVERSION_FAILED,
    )
    user_id, job_id = user.id, job.id
    resolved = _resolve_export_template_id(job, lp_models, template_id)
    target = Path(f"exports/{user_id}/{job_id}/pdf/lesson_plans.pdf")

    if PDFExportEngine.is_available():
        # ONE combined DOCX, converted once. The previous per-lesson batch held
        # the request open for the whole multi-minute conversion — long enough
        # for the browser to abort the fetch — and then returned only the first
        # lesson's PDF.
        combined_docx = target.with_suffix(".docx")
        try:
            await _run_pipeline(
                pipeline.export_docx_combined, scheme_label, lp_models, tt,
                combined_docx, template_id=resolved, context=context)
        except Exception as e:
            logger.error("pdf_source_docx_failed", user_id=user_id, job_id=job_id, detail=str(e))
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)

        # Layer 2 — converter present but produced nothing usable.
        try:
            await _run_pipeline(_convert_only, pipeline, combined_docx, target)
        except PDFConversionError as e:
            logger.error("pdf_conversion_failed", user_id=user_id, job_id=job_id, detail=str(e))
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)

        if not _is_real_pdf(target):
            logger.error("pdf_conversion_failed", user_id=user_id, job_id=job_id,
                         detail="output failed PDF signature check")
            raise HTTPException(status_code=500, detail=PDF_CONVERSION_FAILED)
        return target

    log_event("pdf_export_structured", user_id=user_id, job_id=job_id)
    try:
        await _run_pipeline(_render_structured_pdf, pipeline, lp_models,
                            target, resolved, context)
    except Exception as e:
        logger.error("pdf_structured_render_failed", user_id=user_id,
                     job_id=job_id, detail=str(e))
        raise HTTPException(status_code=503, detail=PDF_CONVERTER_REQUIREMENT)
    if not _is_real_pdf(target):
        logger.error("pdf_structured_render_failed", user_id=user_id, job_id=job_id,
                     detail="output failed PDF signature check")
        raise HTTPException(status_code=503, detail=PDF_CONVERTER_REQUIREMENT)
    return target


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
    enforce_authenticated_budget(user.id, "export")

    lessons = data_service.get_lesson_plans_for_job(db, job_id, user.id)
    if not lessons:
        raise HTTPException(status_code=404, detail="No lesson plans found")

    lp_models = [_db_to_lesson_model(lp) for lp in lessons]
    tt = TemplateType(template_type) if template_type in [t.value for t in TemplateType] else TemplateType.GES_STYLE

    scheme_db = data_service.get_scheme(db, job.scheme_id, user.id)
    scheme_stem = Path(scheme_db.filename).stem if scheme_db and scheme_db.filename else ""
    scheme_label = re.sub(r'[^A-Za-z0-9]+', '_', scheme_stem).strip('_') or 'lesson_plans'

    target = await _build_export_pdf(
        db, user, job, scheme_label, lp_models, tt, template_id,
        _render_context(db, user.id, job, scheme_db, lp_models))

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

import secrets as _secrets
from datetime import datetime as _dt, timedelta as _timedelta

from ..database import DownloadTokenDB, generate_id

#: How long an issued one-time download URL stays valid.
DOWNLOAD_TOKEN_TTL_SECONDS = 600


def _issue_download_token(db: Session, user_id: str, job_id: str, path,
                          media_type: str, filename: str) -> str:
    """Create a single-use, short-lived download token bound to (user, job).

    The token is PERSISTED (``download_tokens``). A process-local dict looked
    correct but broke on any deployment with more than one worker or dyno: the
    POST that issued the token and the browser's GET are separate requests and
    can land on different processes, so the token was missing and the download
    404'd. Persisting it makes the handoff worker-agnostic while keeping every
    security property (unguessable, user-bound, expiring, single-use).
    """
    token = _secrets.token_urlsafe(32)
    db.add(DownloadTokenDB(
        token=token,
        user_id=user_id,
        job_id=job_id,
        path=str(path),
        media_type=media_type,
        filename=filename,
        expires_at=_dt.utcnow() + _timedelta(seconds=DOWNLOAD_TOKEN_TTL_SECONDS),
    ))
    db.commit()
    return token


def _consume_download_token(db: Session, token: Optional[str],
                            user_id: Optional[str] = None) -> Optional[dict]:
    """Claim a valid, unexpired token exactly once; else None.

    ``user_id`` is optional: the browser reaches this URL by *navigation* and
    cannot attach a Bearer header, so the single-use token itself is the
    credential (a presigned URL). When an authenticated identity IS present it
    must still match the issuing user, so an authenticated caller can never
    consume another user's token.

    Single-use is enforced with a guarded UPDATE (``used_at IS NULL``) so two
    concurrent consumers cannot both win the same token.
    """
    if not token:
        return None
    row = db.query(DownloadTokenDB).filter(
        DownloadTokenDB.token == token).first()
    if not row:
        return None
    if user_id is not None and row.user_id != user_id:
        return None
    if row.used_at is not None:
        return None
    if row.expires_at and row.expires_at < _dt.utcnow():
        db.delete(row)
        db.commit()
        return None
    updated = db.query(DownloadTokenDB).filter(
        DownloadTokenDB.token == token,
        DownloadTokenDB.used_at.is_(None),
    ).update({DownloadTokenDB.used_at: _dt.utcnow()}, synchronize_session=False)
    db.commit()
    if updated != 1:
        return None
    return {
        "user_id": row.user_id,
        "job_id": row.job_id,
        "path": row.path,
        "media_type": row.media_type,
        "filename": row.filename,
    }


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
    enforce_authenticated_budget(user.id, "export")
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
    resolved_template_id = _resolve_export_template_id(job, lp_models, template_id)

    if fmt == "docx":
        custom_structure = _custom_structure_for(db, user.id, template_id)
        if custom_structure is not None:
            log_event("custom_template_export", user_id=user.id, job_id=job_id)
            render_context = _render_context(db, user.id, job, scheme_db, lp_models)
            out = await _run_pipeline(
                pipeline.export_docx_combined_custom, lp_models, custom_structure,
                Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
                render_context,
            )
        else:
            out = await _run_pipeline(
                pipeline.export_docx_combined, "", lp_models, tt,
                Path(f"exports/{user.id}/{job_id}/lesson_plans.docx"),
                template_id=resolved_template_id,
                context=_render_context(db, user.id, job, scheme_db, lp_models))
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
            template_id=resolved_template_id, structure=custom_structure,
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
        out = await _build_export_pdf(
            db, user, job, scheme_label, lp_models, tt, template_id,
            _render_context(db, user.id, job, scheme_db, lp_models))
        media_type = "application/pdf"
        filename = f"Lesson_Plans_{scheme_label}.pdf"

    data_service.log_export_event(db, job.id, job.scheme_id, user.id, fmt)
    token = _issue_download_token(db, user.id, job.id, out, media_type, filename)
    return {
        "download_url": f"/api/generation/downloads/{token}",
        "filename": filename,
        "media_type": media_type,
    }


@router.get("/downloads/{token}")
async def download_by_token(
    token: str,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
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
    entry = _consume_download_token(db, token, user.id if user else None)
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
    enforce_authenticated_budget(user.id, "export")

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
    enforce_authenticated_budget(user.id, "export")

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
                        template_id=_resolve_export_template_id(job, lp_models, template_id),
                        structure=custom_structure,
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
        scheme = schemes_map.get(lp.scheme_id)
        serialized = _serialize_lesson(lp, scheme)
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
    scheme_db = data_service.get_scheme(db, scheme_id, user.id)
    return {
        "lesson_plans": [_serialize_lesson(lp, scheme_db) for lp in lessons],
        "total": len(lessons),
    }


def _persist_confirmed_class(db: Session, user: User, scheme_db, config) -> None:
    """Store a teacher-confirmed class on a scheme that never stated one.

    PART 3: the document is allowed not to name its class, but the lesson must
    never carry "Unknown". A class the SCHEME states is never overwritten; only a
    genuine detection gap is filled from the teacher's explicit, catalogue-valid
    choice, and it is persisted so the preview, the generation and every export
    agree on one class.
    """
    if scheme_db.class_level not in ("Unknown", "", None):
        return
    confirmed = (getattr(config, "class_level", "") or "").strip()
    if not confirmed or confirmed == "Unknown" or not _is_known_class_level(confirmed):
        return
    scheme_db.class_level = confirmed
    db.commit()
    log_event("class_level_confirmed", user_id=user.id,
              scheme_id=scheme_db.id, class_level=confirmed)


def _is_known_class_level(value: str) -> bool:
    """True when ``value`` is a class level from the canonical catalogue.

    The teacher-confirmed class is validated against the SAME enum the
    ``/api/settings/class-levels`` endpoint serves, so the confirm control and
    this check can never disagree. Free text is rejected.
    """
    try:
        from ..models import ClassLevel
    except Exception:
        return False
    return any(c.value == value for c in ClassLevel)


def _resolve_school_name(db: Session, user: User) -> Optional[str]:
    """The authenticated user's real school / institution name.

    Identity is server-authoritative (PART 15): the teacher's school membership
    is looked up from the authenticated user, never accepted from the client.

    A teacher with no school relationship is an INDEPENDENT teacher (PART 7).
    They state the institution they teach at once, on their own profile, and
    that value is used here — so every lesson carries the school on its header
    without retyping it, and without a lesson ever accepting a client-supplied
    school. Blank when neither source states one: a lesson with no school
    renders an empty header cell rather than a fake placeholder.
    """
    from ..database import SchoolDB
    if getattr(user, "school_id", None):
        school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
        if school and school.name:
            return school.name
    own = (getattr(user, "school_name", "") or "").strip()
    return own or None


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


def _apply_saved_lesson_config(db: Session, scheme_db, config: TermConfig,
                               user: User) -> None:
    """Merge the plan's saved lesson configuration into the request config.

    The saved configuration is what the teacher confirmed in the guided step;
    it wins over any client default so a stale browser payload can never
    generate with old settings. Fields the teacher never configured fall back
    to the request/preference values exactly as before.
    """
    saved = _saved_lesson_config(scheme_db)
    if not saved:
        return
    if saved.get("school_name"):
        config.school_name = saved["school_name"]
    if saved.get("teacher_name"):
        config.teacher_name = saved["teacher_name"]
    if saved.get("class_size") is not None:
        config.class_size = saved["class_size"]
    if saved.get("lesson_duration_minutes") is not None:
        config.lesson_duration_minutes = saved["lesson_duration_minutes"]
    if saved.get("period"):
        config.period = saved["period"]
    if saved.get("periods_per_week") is not None:
        config.lessons_per_week = saved["periods_per_week"]
    if saved.get("teaching_days"):
        config.teaching_days = list(saved["teaching_days"])
    if saved.get("reference"):
        config.references = [saved["reference"]]


def _require_lesson_config(config: TermConfig) -> None:
    """Block generation when REQUIRED configuration is missing (Phase 2.2).

    The guided step must be completed first; the server never invents a class
    size, duration or timetable to make the request pass.
    """
    missing = []
    if not (getattr(config, "school_name", None) or "").strip():
        missing.append("school name")
    if not (getattr(config, "teacher_name", None) or "").strip():
        missing.append("teacher's name")
    if getattr(config, "class_size", None) in (None, 0):
        missing.append("class size")
    if not getattr(config, "lesson_duration_minutes", 0):
        missing.append("lesson duration")
    if not getattr(config, "teaching_days", None):
        missing.append("teaching days")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=(
                "Complete the lesson configuration before generating: "
                + ", ".join(missing)
                + ". Open Configure lesson rubrics and save the missing "
                  "details."
            ),
        )


def _replacement_ids_for_occurrences(existing, occurrence_ids, chosen_allocs) -> list:
    """Existing lessons replaced by an occurrence-selected generation run.

    Priority 3: "[Generate lesson]" on one week's copy of a repeating
    indicator must regenerate ONLY that occurrence. Lessons carrying an
    occurrence id are matched directly; legacy rows from before occurrence
    ids existed (empty ``source_occurrence_id``) fall back to the same source
    week + indicator code, so one week's regeneration can never touch another
    week's copy of the same code. A codeless legacy row (Nursery-style)
    matches only on its source week when the run chose one of that week's
    codeless occurrences.
    """
    if not occurrence_ids:
        return []
    week_codes: dict = {}
    codeless_weeks: set = set()
    for a in chosen_allocs:
        code = ((getattr(a, "indicator_code", "") or "")).strip()
        if code:
            week_codes.setdefault(getattr(a, "week_number", None), set()).add(code)
        else:
            codeless_weeks.add(getattr(a, "week_number", None))
    ids = []
    for lp in existing:
        oid = getattr(lp, "source_occurrence_id", "") or ""
        if oid:
            if oid in occurrence_ids:
                ids.append(lp.id)
            continue
        codes = set(lp.indicator_codes or [])
        if codes:
            if codes & week_codes.get(lp.week_number, set()):
                ids.append(lp.id)
        elif lp.week_number in codeless_weeks:
            ids.append(lp.id)
    return ids


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
    seq = getattr(lp, "lesson_sequence", None)
    draft = drafts.get(str(seq)) if seq is not None else None
    # NOTE: no "sequence - 1" fallback. The review rows are numbered the same
    # way the lessons are, and the generate page re-saves its rows immediately
    # before generating, so a missing key means this lesson really has no
    # draft. Falling back to the previous number would put one lesson's
    # teacher additions onto its neighbour — the off-by-one being fixed here.
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
    if "period" in draft:
        # Teacher-adjusted timetable slot for this lesson (Pattern 1). Blank is
        # permitted (the source/config supplied no period); never invented.
        lp.period = str(draft.get("period") or "")
    if "keywords" in draft:
        # CANONICAL (PART 9/11): the client may send a string or dirty list;
        # always store the normalized list form, and never store empty-string
        # placeholders (", ," was previously stored verbatim).
        from ..ai_resource_text import normalize_text_items
        lp.keywords = normalize_text_items(draft.get("keywords"))
    if "other_tlrs" in draft:
        from ..ai_resource_text import normalize_text_items
        lp.other_tlrs = normalize_text_items(draft.get("other_tlrs"))
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
            entry
            for entry in (
                _reference_entry(r)
                for r in normalize_structured_references(draft.get("structured_references"))
            )
            if entry is not None
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


#: Lesson fields the allocation loop (not the builder) assigns, which a rebuilt
#: candidate must inherit from the original so drafts, replacement keys,
#: exports and provenance stay byte-for-byte aligned (Priority 4).
_REBUILD_METADATA_FIELDS = (
    "lesson_sequence", "lesson_number", "period", "week_number", "teaching_week",
    "source_occurrence_id", "week_ending", "week_ending_derived",
    "special_period_label", "special_period_type",
    "educational_level", "subject", "class_level", "template_id",
)


def _run_quality_gate(job, config, scheme_id, drafts, allow_rebuild: bool = True):
    """Priority 4 — validate every built lesson BEFORE any row is written.

    ``allow_rebuild=False`` is used for the "Generate with Zeli" method: the
    deterministic pattern rebuild would substitute engine-written content for a
    lesson the teacher asked Zeli to write, which is exactly the silent fallback
    the method forbids. Such a lesson is instead rejected (never persisted) and
    reported honestly. Mechanical repair — punctuation/whitespace and missing
    boundary rows — still runs because it never invents content.

    Returns ``{"accepted", "reports", "metrics"}``:

    * ``accepted`` — the candidates that passed the gate, in batch order. Only
      these may be persisted. A rebuilt candidate REPLACES its original.
    * ``reports`` — per-lesson findings (hard failures, unmet floors, repairs,
      rebuild patterns) for the run's gate metrics.
    * ``metrics`` — first-pass rate, hard/soft rejections, rebuild counts,
      teacher-ready rate and mean score (logged and surfaced in the response).

    A lesson is never padded with generic prose to clear the gate: it is
    mechanically repaired, then rebuilt with a different teaching pattern, and
    refused when no candidate passes. The rebuild is bounded
    (``MAX_REBUILD_ATTEMPTS``) and deterministic — same inputs, same candidates,
    same winner (tie-breakers in ``lesson_quality_gate.pick_best``).
    """
    from ..curriculum.lesson_builder import build_lesson
    from ..engines.lesson_quality_gate import (
        MAX_REBUILD_ATTEMPTS,
        LessonReport,
        Scored,
        build_entry,
        count_collisions,
        evaluate,
        lesson_fingerprint,
        mechanical_repair,
        pick_alternate_pattern,
        pick_best,
        summarize,
    )
    from ..engines.wapef_fields import normalize_wapef_payload

    def _wapef_canonical_for(lp) -> Optional[Dict[str, Any]]:
        """The teacher's saved WAPEF selection for this lesson, canonicalized.

        Loss check T compares the lesson against exactly what the review draft
        stored (the same normalization ``_apply_lesson_review_draft`` used), so
        a value that survived generation→save is byte-identical and a lost one
        is caught. No saved selection → ``None`` (the legitimate empty state).
        """
        if not drafts:
            return None
        seq = getattr(lp, "lesson_sequence", None)
        draft = drafts.get(str(seq)) if seq is not None else None
        if not isinstance(draft, dict):
            return None
        if not any(k in draft for k in (
                "wapef_deep_hope", "wapef_storyline",
                "wapef_through_lines", "wapef_gods_story")):
            return None
        return normalize_wapef_payload(draft)

    lessons = list(getattr(job, "_lesson_plans", None) or [])
    ledger = getattr(job, "_build_ledger", None)
    contexts = getattr(ledger, "contexts", {}) if ledger is not None else {}
    history = getattr(ledger, "history", None) if ledger is not None else None

    reports = []
    accepted: list = []
    prior_fingerprints: list = []

    for lp in lessons:
        ctx = contexts.get(lp.id)
        alloc = getattr(ctx, "alloc", None)
        entry = build_entry(alloc, lp)
        report = LessonReport(
            lesson_id=lp.id,
            lesson_sequence=getattr(lp, "lesson_sequence", 0),
            indicator_code=(lp.indicator_codes[0] if lp.indicator_codes else ""),
            accepted=False,
        )

        # ── Candidate 0: the built lesson (mechanical repair only on failure)
        # A lesson that passes the gate is persisted byte-for-byte as built —
        # the gate never rewrites good output.
        wapef_canonical = _wapef_canonical_for(lp)
        outcome = evaluate(lp, entry, wapef_canonical=wapef_canonical)
        repairs: list = []
        if outcome.needs_work:
            repairs = mechanical_repair(lp)
            if repairs:
                outcome = evaluate(lp, entry)
        candidates = [{
            "lp": lp, "outcome": outcome, "repairs": repairs,
            "pattern_id": getattr(ctx, "pattern_id", "") or "", "order": 0,
        }]

        # ── Candidates 1..N: rebuild with an untried teaching pattern ─────
        # Only pattern-shaped lessons have an alternative (early years and
        # pre-pattern paths compose their own pedagogy — nothing to swap).
        if (allow_rebuild and outcome.needs_work
                and ctx is not None and (ctx.pattern_id or "")):
            tried = [ctx.pattern_id]
            for attempt in range(MAX_REBUILD_ATTEMPTS):
                pattern = pick_alternate_pattern(
                    ctx.alloc, config, history,
                    ctx.previous_indicator, tried,
                )
                if pattern is None:
                    break
                tried.append(pattern.id)
                rebuilt = build_lesson(
                    ctx.alloc, config, scheme_id,
                    previous_indicator=ctx.previous_indicator,
                    next_indicator=ctx.next_indicator,
                    pattern=pattern,
                )
                # The rebuilt candidate keeps the original's batch identity so
                # draft keys, replacement and provenance are unchanged, then
                # re-applies the teacher's saved review/WAPEF selections.
                for field_name in _REBUILD_METADATA_FIELDS:
                    setattr(rebuilt, field_name, getattr(lp, field_name))
                _apply_lesson_review_draft(rebuilt, drafts)
                rebuilt_outcome = evaluate(
                    rebuilt, build_entry(ctx.alloc, rebuilt),
                    wapef_canonical=_wapef_canonical_for(rebuilt))
                rebuilt_repairs: list = []
                if rebuilt_outcome.needs_work:
                    rebuilt_repairs = mechanical_repair(rebuilt)
                    if rebuilt_repairs:
                        rebuilt_outcome = evaluate(
                            rebuilt, build_entry(ctx.alloc, rebuilt))
                candidates.append({
                    "lp": rebuilt, "outcome": rebuilt_outcome,
                    "repairs": rebuilt_repairs, "pattern_id": pattern.id,
                    "order": attempt + 1,
                })
                report.rebuild_pattern_ids.append(pattern.id)
                if rebuilt_outcome.accepted:
                    break

        # ── Best-candidate selection (only among PASSING candidates) ──────
        passing = [c for c in candidates if c["outcome"].accepted]
        if passing:
            scored = []
            for cand in passing:
                fingerprint = lesson_fingerprint(cand["lp"])
                scored.append(Scored(
                    lp=cand["lp"],
                    outcome=cand["outcome"],
                    fingerprint=fingerprint,
                    collisions=count_collisions(fingerprint, prior_fingerprints),
                    order=cand["order"],
                ))
            best = pick_best(scored)
            best_candidate = next(
                c for c in passing if c["order"] == best.order)
            current = best.lp
            outcome = best.outcome
            repairs = best_candidate["repairs"]
            prior_fingerprints.append(best.fingerprint)
        else:
            current = lp

        report.accepted = outcome.accepted
        report.hard_failures = outcome.hard
        report.floors_failed = outcome.floors
        report.scores = outcome.scores
        report.total = outcome.total
        report.attempts = (
            next((c["order"] for c in candidates if c["lp"] is current), 0)
        )
        report.repairs = repairs
        report.status = (
            "accepted_first_pass"
            if outcome.accepted and not repairs and report.attempts == 0
            else "accepted_after_repair"
            if outcome.accepted and report.attempts == 0
            else "accepted_after_rebuild"
            if outcome.accepted
            else "rejected"
        )
        report.final_lesson = current if outcome.accepted else None
        reports.append(report)
        if outcome.accepted:
            accepted.append(current)

    return {
        "accepted": accepted,
        "reports": reports,
        "metrics": summarize(reports),
    }


def _reference_entry(entry):
    """Coerce one stored entry to a ReferenceEntry — never raises.

    Corrupted rows can hold dicts with non-string values (lists, numbers,
    nested objects). A raw ``ReferenceEntry(**entry)`` would raise a
    pydantic ValidationError and take the whole export down; here anything
    that isn't a usable scalar is dropped to the model default instead.
    """
    if isinstance(entry, ReferenceEntry):
        return entry
    if not isinstance(entry, dict):
        return None
    safe = {}
    for key, value in entry.items():
        if isinstance(value, str):
            safe[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            safe[key] = str(value)
        # None / bool / list / dict values: fall back to the field default.
    return ReferenceEntry(**safe)


def _serialize_lesson(lp, scheme_db=None) -> dict:
    from ..database import LessonPlanDB
    # CANONICAL LIST FIELDS (PART 8/9/11): normalize at the API boundary so
    # the review UI never receives serialized/legacy list text for any
    # array-typed field.
    from ..ai_resource_text import normalize_text_items
    # "Why this lesson?" — the source/provenance record every lesson carries so
    # the workspace can answer which part of the teacher's scheme produced it.
    from ..curriculum.spine import lesson_provenance
    return {
        "id": lp.id,
        "scheme_id": lp.scheme_id,
        "job_id": lp.job_id,
        "week_number": lp.week_number,
        "source_week": lp.week_number,
        "source_occurrence_id": (
            getattr(lp, "source_occurrence_id", "") or ""),
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
        "indicators": normalize_exact_items(lp.indicators),
        "indicator_codes": lp.indicator_codes or [],
        "lesson_topic": lp.lesson_topic,
        "previous_knowledge": lp.previous_knowledge,
        "wapef_deep_hope": getattr(lp, "wapef_deep_hope", "") or "",
        "wapef_storyline": getattr(lp, "wapef_storyline", "") or "",
        "wapef_through_lines": list(getattr(lp, "wapef_through_lines", None) or []),
        "wapef_gods_story": getattr(lp, "wapef_gods_story", "") or "",
        "remarks": getattr(lp, "remarks", "") or "",
        "learning_objectives": lp.learning_objectives or [],
        "core_competencies": normalize_text_items(lp.core_competencies),
        "source_tlrs": normalize_text_items(getattr(lp, "source_tlrs", None)),
        "other_tlrs": normalize_text_items(getattr(lp, "other_tlrs", None)),
        "teaching_learning_resources": normalize_resource_items(
            lp.teaching_learning_resources),
        "introduction": lp.introduction,
        "main_activities": lp.main_activities or [],
        "learner_activities": lp.learner_activities or [],
        "teacher_activities": lp.teacher_activities or [],
        "assessment": lp.assessment,
        # Phase 3 structured assessment: the same parse-safe path the export
        # model uses, so the workspace read model and DOCX/PDF never diverge.
        "assessment_items": [
            (i.model_dump(mode="json") if hasattr(i, "model_dump") else i)
            for i in parse_assessment_items(
                getattr(lp, "assessment_items", None))
        ],
        "assessment_rubric": _rubric_json(
            parse_assessment_rubric(getattr(lp, "assessment_rubric", None))),
        "conclusion": lp.conclusion,
        "references": normalize_text_items(lp.references),
        "structured_references": normalize_structured_references(
            getattr(lp, "structured_references", None)),
        "keywords": normalize_text_items(lp.keywords),
        # Teacher-owned text/assignment/template fields: serialized on every
        # read path so a saved value round-trips (persistence matrix).
        "homework": getattr(lp, "homework", "") or "",
        "class_assignment": getattr(lp, "class_assignment", "") or "",
        "home_assignment": getattr(lp, "home_assignment", "") or "",
        "starter_activity": getattr(lp, "starter_activity", "") or "",
        "differentiation": getattr(lp, "differentiation", "") or "",
        "essential_questions": normalize_text_items(
            getattr(lp, "essential_questions", None)),
        "template_id": getattr(lp, "template_id", None),
        "status": lp.status,
        "ai_generated": lp.ai_generated,
        "ai_provider": getattr(lp, "ai_provider", "") or "",
        "ai_model": getattr(lp, "ai_model", "") or "",
        "generation_method": (
            getattr(lp, "generation_method", "") or "standard"),
        "teacher_edited": lp.teacher_edited,
        "provenance": lesson_provenance(
            lp, scheme_db, ai_provider=getattr(lp, "ai_provider", "") or None),
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


def parse_assessment_items(raw) -> list:
    """Stored assessment_items JSON → AssessmentItem models (legacy-safe)."""
    from ..models import AssessmentItem, ContentSource
    out = []
    for entry in (raw or []):
        if isinstance(entry, AssessmentItem):
            out.append(entry)
        elif isinstance(entry, dict) and (entry.get("prompt") or "").strip():
            try:
                payload = {
                    k: entry.get(k) for k in
                    ("prompt", "dok_level", "bloom_category",
                     "expected_evidence", "marking_guidance",
                     "misconception", "follow_up", "source")
                }
                # Hand-seeded/legacy rows without a source key stay readable
                # instead of being dropped by enum validation.
                if not payload.get("source"):
                    payload["source"] = ContentSource.DETERMINISTIC
                out.append(AssessmentItem(**payload))
            except Exception:
                continue
    return out


def _rubric_json(rubric):
    """AnalyticRubric model (or None) → JSON-safe dict for API responses."""
    if rubric is None:
        return None
    return rubric.model_dump(mode="json") if hasattr(rubric, "model_dump") \
        else rubric


def parse_assessment_rubric(raw):
    """Stored assessment_rubric JSON → AnalyticRubric model (legacy-safe)."""
    from ..models import AnalyticRubric
    if isinstance(raw, AnalyticRubric):
        return raw
    if isinstance(raw, dict) and raw.get("criteria"):
        try:
            return AnalyticRubric(**raw)
        except Exception:
            return None
    return None


def _db_to_lesson_model(lp) -> LessonPlan:
    from ..database import LessonPlanDB
    from ..models import TeachingActivity, LearningObjective
    # CANONICAL LIST FIELDS (PART 5/6/9/11): every list-typed column passes
    # through normalize_text_items so a serialized/legacy/empty-dirty stored
    # value can never reach the review UI or an export as display text. This
    # is the load path for review AND every export, so a repair here fixes
    # both without touching the stored rows (teacher edits stay untouched).
    from ..ai_resource_text import normalize_text_items
    return LessonPlan(
        id=lp.id,
        scheme_of_work_id=lp.scheme_id,
        term_config_id=lp.job_id,
        week_number=lp.week_number,
        source_occurrence_id=(getattr(lp, "source_occurrence_id", "") or ""),
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
        core_competencies=normalize_text_items(lp.core_competencies),
        source_tlrs=normalize_text_items(getattr(lp, "source_tlrs", None)),
        other_tlrs=normalize_text_items(getattr(lp, "other_tlrs", None)),
        teaching_learning_resources=normalize_resource_items(
            lp.teaching_learning_resources),
        introduction=lp.introduction,
        main_activities=_parse_activity_list(lp.main_activities, TeachingActivity),
        learner_activities=_parse_activity_list(lp.learner_activities, TeachingActivity),
        teacher_activities=_parse_activity_list(lp.teacher_activities, TeachingActivity),
        assessment=lp.assessment,
        # Phase 3 structured assessment (additive columns; legacy rows stay
        # valid with empty list / None).
        assessment_items=parse_assessment_items(
            getattr(lp, "assessment_items", None)),
        assessment_rubric=parse_assessment_rubric(
            getattr(lp, "assessment_rubric", None)),
        conclusion=lp.conclusion,
        references=normalize_text_items(lp.references),
        structured_references=[
            entry
            for entry in (
                _reference_entry(entry)
                for entry in normalize_structured_references(
                    getattr(lp, "structured_references", None))
            )
            if entry is not None
        ],
        keywords=normalize_text_items(lp.keywords),
        homework=getattr(lp, "homework", "") or "",
        class_assignment=getattr(lp, "class_assignment", "") or "",
        home_assignment=getattr(lp, "home_assignment", "") or "",
        starter_activity=getattr(lp, "starter_activity", "") or "",
        differentiation=getattr(lp, "differentiation", "") or "",
        essential_questions=normalize_text_items(
            getattr(lp, "essential_questions", None)),
        template_id=getattr(lp, "template_id", None),
        special_period_label=getattr(lp, "special_period_label", "") or "",
        special_period_type=getattr(lp, "special_period_type", "") or "",
        ai_generated=bool(getattr(lp, "ai_generated", False)),
        ai_provider=getattr(lp, "ai_provider", "") or "",
        ai_model=getattr(lp, "ai_model", "") or "",
        generation_method=(
            getattr(lp, "generation_method", "") or "standard"),
        teacher_edited=bool(getattr(lp, "teacher_edited", False)),
    )

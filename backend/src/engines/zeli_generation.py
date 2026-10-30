"""Zeli whole-lesson generation helpers.

Zeli is SchemeKnit's teacher-facing generation assistant. Its verified engine is
DeepSeek (``DEEPSEEK_API_KEY`` + ``ZELI_*`` overrides, default model
``deepseek-flash``), implemented by :class:`src.engines.ai_provider.DeepSeekProvider`.
Selecting ``ZELI_PROVIDER=groq`` keeps the previous Groq integration working.
This module contains only the method-specific contracts: validated server-side
configuration, a strict output validator, a durable cache keyed by every
material input, and teacher-safe failure mapping.

Nothing here reads, returns or logs an API key. Provider construction and
authentication stay in the existing provider abstraction, and the key is only
ever attached to the server-side provider instance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import ZeliGenerationCacheDB
from .ai_provider import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    NAMED_PROVIDERS,
    get_provider,
    provider_status,
)

#: Default provider behind Zeli — the verified production integration.
ZELI_PROVIDER_KEY = "deepseek"
#: Method label persisted on jobs/lessons.
ZELI_METHOD = "zeli"
#: Bump when the prompt/contract changes enough to invalidate cached output.
ZELI_PROMPT_VERSION = "zeli-generation-v4"

#: The canonical V2 sections a whole Zeli lesson must carry. A partial object
#: is rejected before any of it is applied to the deterministic scaffold.
ZELI_REQUIRED_SECTIONS = (
    "learning_objectives",
    "starter",
    "main_learning",
    "assessment",
    "plenary",
    "differentiation",
)

#: Provider kwargs accepted by ``generate_lesson_v2`` that the pipeline fills.
#: Kept explicit so a provider that predates a field is never sent it blindly.
_CONTEXT_KWARGS = (
    "subject", "class_level", "strand", "sub_strand", "content_standard",
    "indicator_code", "indicator_text", "class_size", "duration_minutes",
    "source_resources", "previous_lesson_context", "next_lesson_context",
    "teaching_day", "week_number", "source_week_ending", "term",
    "teaching_week", "period", "teacher_keywords", "other_tlrs",
    "core_competencies", "references", "wapef_context",
)


class ZeliGenerationError(RuntimeError):
    """A teacher-safe, classified whole-lesson Zeli failure.

    ``status_code`` lets the HTTP layer answer truthfully (429 / 503 / 504 /
    502) without exposing provider diagnostics. ``message`` is safe to show.
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = int(status_code)


@dataclass(frozen=True)
class ZeliConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.3
    max_tokens: int = 2000
    thinking_mode: str = "disabled"
    connect_timeout: float = 10.0
    read_timeout: float = 90.0
    max_retries: int = 2


def _zeli_config(settings=None) -> ZeliConfig:
    """Resolve validated Zeli settings, falling back to provider defaults.

    ``ZELI_*`` overrides are optional. For DeepSeek (the default) a blank
    model/base URL resolves to ``deepseek-flash`` / ``https://api.deepseek.com``
    and a blank ``ZELI_API_KEY`` falls back to ``DEEPSEEK_API_KEY``. Selecting
    ``ZELI_PROVIDER=groq`` falls back to ``GROQ_MODEL`` / ``GROQ_BASE_URL`` /
    ``GROQ_API_KEY``, so the earlier integration keeps working and a Groq key is
    never sent to DeepSeek (or vice versa).
    """
    s = settings or get_settings()
    provider = (getattr(s, "ZELI_PROVIDER", "") or ZELI_PROVIDER_KEY).strip().lower()
    enabled = bool(getattr(s, "ZELI_ENABLED", True))

    model = (getattr(s, "ZELI_MODEL", "") or "").strip()
    base_url = (getattr(s, "ZELI_BASE_URL", "") or "").strip()
    api_key = (getattr(s, "ZELI_API_KEY", "") or "").strip()
    if provider == "deepseek":
        model = model or DEFAULT_DEEPSEEK_MODEL
        base_url = base_url or DEFAULT_DEEPSEEK_BASE_URL
        api_key = api_key or (
            getattr(s, "DEEPSEEK_API_KEY", "") or "").strip()
    elif provider == "groq":
        model = model or (getattr(s, "GROQ_MODEL", "") or "").strip()
        base_url = base_url or (getattr(s, "GROQ_BASE_URL", "") or "").strip()
        api_key = api_key or (getattr(s, "GROQ_API_KEY", "") or "").strip()

    return ZeliConfig(
        enabled=enabled, provider=provider, model=model,
        base_url=base_url, api_key=api_key,
        temperature=float(getattr(s, "ZELI_TEMPERATURE", 0.3) or 0.3),
        max_tokens=int(getattr(s, "ZELI_MAX_TOKENS", 2000) or 2000),
        thinking_mode=str(
            getattr(s, "ZELI_THINKING_MODE", "disabled") or "auto").strip().lower(),
        connect_timeout=float(
            getattr(s, "ZELI_CONNECT_TIMEOUT_SECONDS", 10.0) or 10.0),
        read_timeout=float(
            getattr(s, "ZELI_READ_TIMEOUT_SECONDS", 90.0) or 90.0),
        max_retries=int(getattr(s, "ZELI_MAX_RETRIES", 2) or 0),
    )


def get_zeli_provider(settings=None):
    """Build the configured Zeli provider or raise ``ZeliGenerationError``.

    Configuration is validated HERE (server-side) — never in the browser — and
    the key is attached only to the in-process provider instance.
    """
    config = _zeli_config(settings)
    if not config.enabled:
        raise ZeliGenerationError(
            "Zeli is turned off on this server. Choose Standard generation, "
            "or ask your administrator to enable Zeli.",
            503,
        )
    if config.provider not in NAMED_PROVIDERS:
        raise ZeliGenerationError(
            "Zeli is not configured correctly on this server. Choose Standard "
            "generation, or ask your administrator to check the Zeli settings.",
            503,
        )

    provider = get_provider(config.provider)
    # Apply the validated overrides explicitly. Constructing with kwargs would
    # let ``get_provider`` silently drop them on a TypeError; assigning after
    # construction keeps the endpoint/model/key exactly as configured.
    provider.api_key = config.api_key
    if config.model:
        provider.model = config.model
    if config.base_url and hasattr(provider, "base_url"):
        provider.base_url = config.base_url
    # Tuning is only consumed by the DeepSeek transport; assigning it to other
    # providers is inert but keeps the contract uniform for tests.
    for attr, value in (
        ("temperature", config.temperature),
        ("max_tokens", config.max_tokens),
        ("thinking_mode", config.thinking_mode),
        ("connect_timeout", config.connect_timeout),
        ("read_timeout", config.read_timeout),
        ("max_retries", config.max_retries),
    ):
        setattr(provider, attr, value)
    return provider


def zeli_availability(settings=None) -> Dict[str, Any]:
    """Secret-free availability snapshot for the UI.

    Returns only booleans and teacher-safe text — never a key, endpoint, model
    identifier or raw provider diagnostic.
    """
    try:
        config = _zeli_config(settings)
    except Exception:
        return {
            "enabled": False, "configured": False, "available": False,
            "state": "INVALID_CONFIG", "method": ZELI_METHOD,
            "reason": "Zeli is not configured correctly on this server.",
        }

    if not config.enabled:
        return {
            "enabled": False, "configured": False, "available": False,
            "state": "DISABLED", "method": ZELI_METHOD,
            "reason": "Zeli is turned off on this server.",
        }
    if config.provider not in NAMED_PROVIDERS:
        return {
            "enabled": True, "configured": False, "available": False,
            "state": "INVALID_CONFIG", "method": ZELI_METHOD,
            "reason": "Zeli is not configured correctly on this server.",
        }

    try:
        provider = get_zeli_provider(settings)
        available = bool(provider and provider.is_available())
        state = provider_status(provider) if provider else "NOT_CONFIGURED"
    except ZeliGenerationError as exc:
        return {
            "enabled": True, "configured": False, "available": False,
            "state": "INVALID_CONFIG", "method": ZELI_METHOD,
            "reason": exc.message,
        }
    except Exception:
        return {
            "enabled": True, "configured": True, "available": False,
            "state": "NOT_CONFIGURED", "method": ZELI_METHOD,
            "reason": "Zeli is unavailable right now. Standard generation still works.",
        }

    if available:
        return {
            "enabled": True, "configured": True, "available": True,
            "state": "CONFIGURED", "method": ZELI_METHOD, "reason": None,
        }
    return {
        "enabled": True, "configured": True, "available": False,
        "state": state or "MISSING_KEY", "method": ZELI_METHOD,
        "reason": (
            "Zeli is unavailable right now. Standard generation still works."
        ),
    }


def zeli_cache_key(
    *,
    provider: str,
    model: str,
    lesson_payload: Dict[str, Any],
) -> str:
    """Stable identity for one Zeli whole-lesson output.

    Includes the method, provider, model and prompt version plus every
    material lesson/config input supplied by the caller. A different method,
    model, teacher instruction, curriculum occurrence or duration therefore
    cannot collide with this result.
    """
    payload = {
        "prompt_version": ZELI_PROMPT_VERSION,
        "generation_method": ZELI_METHOD,
        "provider": provider or "",
        "model": model or "",
        "lesson": lesson_payload or {},
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def zeli_lesson_context(
    lp,
    config=None,
    *,
    previous_lesson_context: Optional[str] = None,
    next_lesson_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Every material generation input for one lesson.

    The same dict feeds the provider prompt and the cache key, so a change to
    any teacher-visible input necessarily produces a different cache entry.
    """
    source_resources = list(
        getattr(lp, "source_tlrs", None)
        or getattr(lp, "teaching_learning_resources", None)
        or []
    )
    week_ending = getattr(lp, "week_ending", None)
    context = {
        "subject": str(getattr(lp, "subject", "") or ""),
        "class_level": str(getattr(lp, "class_level", "") or ""),
        "strand": str(getattr(lp, "strand", "") or ""),
        "sub_strand": str(getattr(lp, "sub_strand", "") or ""),
        "content_standard": str(getattr(lp, "content_standard", "") or ""),
        "indicator_code": (
            getattr(lp, "indicator_codes", None)[0]
            if getattr(lp, "indicator_codes", None) else ""
        ),
        "indicator_text": (
            getattr(lp, "indicators", None)[0]
            if getattr(lp, "indicators", None) else ""
        ),
        # No invented fallbacks: an unconfigured class size/duration is 0 and
        # the provider is told to leave the form cell blank, never to guess.
        "class_size": int(getattr(lp, "class_size", 0) or 0),
        "duration_minutes": int(getattr(lp, "duration_minutes", 0) or 0),
        "source_resources": source_resources,
        "previous_lesson_context": previous_lesson_context,
        "next_lesson_context": next_lesson_context,
        "teaching_day": getattr(lp, "teaching_day", None),
        "week_number": getattr(lp, "week_number", None),
        "source_week_ending": week_ending.isoformat() if week_ending else None,
        "term": getattr(config, "term", None),
        "teaching_week": getattr(lp, "teaching_week", None),
        "period": getattr(lp, "period", None),
        "teacher_keywords": (
            # Only teacher-entered terms. The deterministic scaffold's keyword
            # guesses are not teacher input and were being sent to the provider
            # as if they were (then echoed back into the lesson).
            list(getattr(config, "keywords", None) or [])
            if config is not None
            else list(getattr(lp, "keywords", None) or [])
        ),
        "other_tlrs": list(getattr(lp, "other_tlrs", None) or []),
        "core_competencies": list(
            getattr(lp, "core_competencies", None) or []),
        "references": list(getattr(lp, "references", None) or []),
        "wapef_context": list(getattr(lp, "wapef_context", None) or []),
    }
    return context


def validate_zeli_content(content: Any) -> str:
    """Return a short failure code, or ``""`` when the payload is usable.

    This is deliberately stricter than the generic V2 parser: a whole Zeli
    lesson must carry all substantive sections. Partial JSON is never merged
    into the deterministic scaffold (that would be a silent mixed fallback).
    """
    if not isinstance(content, dict):
        return "not_an_object"
    missing = [
        key for key in ZELI_REQUIRED_SECTIONS
        if not content.get(key)
    ]
    if missing:
        return "missing_sections:" + ",".join(missing)
    main = content.get("main_learning")
    if isinstance(main, dict):
        phases = [value for value in main.values() if isinstance(value, dict)]
        if len(phases) < 2:
            return "incomplete_main_learning"
    elif isinstance(main, list):
        if len([value for value in main if value]) < 2:
            return "incomplete_main_learning"
    else:
        return "incomplete_main_learning"
    if not str(content.get("assessment") or "").strip():
        return "empty_assessment"
    return ""


def read_zeli_cache(
    db: Optional[Session], cache_key: str
) -> Optional[Dict[str, Any]]:
    """Return cached whole-lesson content for this exact key, or None."""
    if db is None or not cache_key:
        return None
    try:
        row = (
            db.query(ZeliGenerationCacheDB)
            .filter(ZeliGenerationCacheDB.cache_key == cache_key)
            .first()
        )
    except Exception:
        db.rollback()
        return None
    if row is None or not (row.content or "").strip():
        return None
    try:
        value = json.loads(row.content)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def write_zeli_cache(
    db: Optional[Session],
    *,
    cache_key: str,
    content: Dict[str, Any],
    provider: str,
    model: str,
) -> None:
    """Persist one whole-lesson result for safe retry/replay.

    Cache rows are committed independently of the lesson transaction: the
    provider output is reusable even if the later persistence step fails. A
    cache write failure never blocks generation. A concurrent writer may win
    the unique key; that is harmless and never surfaces.
    """
    if db is None or not cache_key or not isinstance(content, dict):
        return
    try:
        existing = (
            db.query(ZeliGenerationCacheDB)
            .filter(ZeliGenerationCacheDB.cache_key == cache_key)
            .first()
        )
        if existing is not None:
            return
        db.add(ZeliGenerationCacheDB(
            cache_key=cache_key,
            content=json.dumps(content, ensure_ascii=False),
            provider=provider or "",
            model=model or "",
            generation_method=ZELI_METHOD,
        ))
        db.commit()
    except Exception:
        db.rollback()


def generate_zeli_content(
    *,
    provider,
    context: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Generate one whole lesson, cache first, then validate strictly.

    Raises ``ZeliGenerationError`` on any failure. It NEVER returns a
    deterministic or partial substitute: the caller decides how to report the
    failure, and the existing lesson content is left untouched.
    """
    if provider is None:
        raise ZeliGenerationError(
            "Zeli is unavailable right now. Your existing lessons were kept. "
            "Please try again later, or choose Standard generation.",
            503,
        )
    provider_name = provider.get_name() if hasattr(provider, "get_name") else "zeli"
    model = str(getattr(provider, "model", "") or "")
    cache_key = zeli_cache_key(
        provider=provider_name, model=model, lesson_payload=context)

    cached = read_zeli_cache(db, cache_key)
    if cached is not None and validate_zeli_content(cached) == "":
        return cached

    kwargs = {
        key: context[key] for key in _CONTEXT_KWARGS if key in context
    }
    try:
        content = provider.generate_lesson_v2(**kwargs)
    except ZeliGenerationError:
        raise
    except Exception:
        raise zeli_failure_from_provider(
            getattr(provider, "last_error", None))

    if not content:
        raise zeli_failure_from_provider(
            getattr(provider, "last_error", None))

    problem = validate_zeli_content(content)
    if problem:
        # The provider answered, but the output cannot be trusted. Never merge
        # it into the lesson; report a safe generation failure instead.
        raise ZeliGenerationError(
            "Zeli returned an incomplete lesson plan, so nothing was saved "
            "and no lesson-plan quota was used. Please try again, or choose "
            "Standard generation.",
            502,
        )

    write_zeli_cache(
        db, cache_key=cache_key, content=content,
        provider=provider_name, model=model,
    )
    return content


def zeli_failure_from_provider(last_error: Optional[str]) -> ZeliGenerationError:
    """Map a provider diagnostic to a teacher-safe status/message.

    No provider vocabulary, model id, response body or secret is exposed.
    """
    error = (last_error or "").lower()
    if "rate_limit" in error or "429" in error:
        return ZeliGenerationError(
            "Zeli is busy right now. No lesson plans were saved and no "
            "lesson-plan quota was used. Please try again shortly, or choose "
            "Standard generation.",
            429,
        )
    if "timeout" in error or "connection" in error:
        return ZeliGenerationError(
            "Zeli took too long to respond. No lesson plans were saved and no "
            "lesson-plan quota was used. Please try again, or choose Standard "
            "generation.",
            504,
        )
    if any(token in error for token in (
        "auth", "missing_api_key", "invalid_api_key", "model_not_found",
        "http_401", "http_403", "http_404", "unavailable",
        "insufficient_balance", "http_402",
    )):
        return ZeliGenerationError(
            "Zeli is unavailable right now. No lesson plans were saved and no "
            "lesson-plan quota was used. Please try again later, or choose "
            "Standard generation.",
            503,
        )
    return ZeliGenerationError(
        "Zeli could not generate usable lesson plans. No lesson plans were "
        "saved and no lesson-plan quota was used. Please try again, or choose "
        "Standard generation.",
        502,
    )

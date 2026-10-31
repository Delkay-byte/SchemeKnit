"""AI provider spending controls and usage accounting.

Three independent layers protect SchemeKnit from AI cost abuse:

* **Request abuse** lives in ``security.AUTHENTICATED_BUDGETS`` (per account).
* **Teacher entitlements** live in ``entitlements``/``credits`` (who may bill
  a generation, and how many).
* **Provider cost** lives here: every real provider attempt reserves a
  conservative estimate in a shared database counter, then settles the actual
  reported usage. A hard monthly cap (plus optional daily and per-provider
  caps) stops new billable attempts once the budget is exhausted.

The provider ledger is intentionally separate from the teacher-credit ledger.
A failed DeepSeek attempt followed by a successful Groq fallback costs money
on both providers but charges the teacher once. ``attempt_id`` is unique, so
replaying the same DB record can never double-count expenditure.

No secret, raw provider body, or provider diagnostic is exposed by this
module's owner summary.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from .config import get_settings
from .database import (
    AIProviderUsageDB, AISpendCounterDB, AISpendReservationDB, generate_id,
)
from .logging_config import get_logger, log_event

logger = get_logger()

#: Version of the price schedule below. Recorded on every usage row so an old
#: estimate can always be explained after a price change.
PRICING_VERSION = "2026-10-31"

#: USD per 1,000,000 tokens. DeepSeek figures are the PEAK rate from
#: https://api-docs.deepseek.com/quick_start/pricing (off-peak is half, so the
#: peak rate is the conservative choice). Groq figures are from
#: https://console.groq.com/docs/model/openai/gpt-oss-120b.
PRICING: Dict[str, Dict[str, float]] = {
    "deepseek": {
        "input": 0.30,
        "cached_input": 0.006,
        "output": 1.20,
    },
    "groq": {
        "input": 0.15,
        "cached_input": 0.075,
        "output": 0.60,
    },
}

#: Unknown providers are priced conservatively; SchemeKnit never silently
#: treats an unrecognised model as free.
DEFAULT_PRICING = {"input": 1.00, "cached_input": 0.50, "output": 3.00}

#: Error codes that prove no billable provider request was made (missing
#: credentials, rejected request). They still appear in the ledger with a
#: zero cost so the attempt itself is auditable.
_NO_CALL_ERRORS = frozenset({
    "missing_api_key", "auth_failed", "invalid_api_key", "model_not_found",
    "invalid_request",
})

_MICRO = 1_000_000


class AISpendError(Exception):
    """Base class for a safe, teacher-facing provider-spend block."""

    status_code = 503
    code = "ai_spend_unavailable"
    message = (
        "AI generation is temporarily paused. No lesson plans were saved and "
        "no lesson-plan quota was used. Please try again later, or choose "
        "Standard generation."
    )

    def __init__(self, message: Optional[str] = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class AISpendBudgetExceeded(AISpendError):
    code = "ai_budget_paused"


class AISpendConcurrencyExceeded(AISpendError):
    status_code = 429
    code = "ai_concurrency_limited"
    message = (
        "Another AI generation is already running for this account. Wait for "
        "it to finish, then try again. No lesson-plan quota was used."
    )


class AIPromptTooLarge(AISpendError):
    status_code = 413
    code = "ai_input_too_large"
    message = (
        "This AI request is too large. Reduce the material sent for "
        "generation and try again. No lesson-plan quota was used."
    )


def _micros(usd: float) -> int:
    return max(0, int(math.ceil(float(usd) * _MICRO)))


def _usd(micros: int) -> float:
    return round(int(micros) / _MICRO, 6)


def _ceil_div(value: int, divisor: int) -> int:
    return max(0, (int(value) + divisor - 1) // divisor)


def pricing_for(provider: str) -> Dict[str, float]:
    return PRICING.get((provider or "").strip().lower(), DEFAULT_PRICING)


def estimate_tokens(chars: int) -> int:
    """Conservative token estimate from a character count.

    Roughly 4 characters per token, with a 20 % safety margin so the reserved
    estimate is normally above the provider's reported input usage.
    """
    return max(1, int(math.ceil(max(0, int(chars)) / 4.0 * 1.2)))


def cost_micros(
    provider: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> int:
    """Cost in micro-USD for one attempt at the recorded price schedule."""
    rates = pricing_for(provider)
    cached = max(0, min(int(cached_input_tokens or 0), int(input_tokens or 0)))
    uncached = max(0, int(input_tokens or 0) - cached)
    usd = (
        uncached * rates["input"]
        + cached * rates.get("cached_input", rates["input"])
        + max(0, int(output_tokens or 0)) * rates["output"]
    ) / 1_000_000.0
    return _micros(usd)


def _settings():
    return get_settings()


def budget_config() -> Dict[str, Any]:
    s = _settings()
    return {
        "enabled": bool(getattr(s, "AI_SPEND_CONTROL_ENABLED", True)),
        "monthly": float(getattr(s, "AI_MONTHLY_BUDGET_USD", 10.0) or 0.0),
        "daily": float(getattr(s, "AI_DAILY_BUDGET_USD", 2.0) or 0.0),
        "providers": {
            "deepseek": float(
                getattr(s, "AI_DEEPSEEK_MONTHLY_BUDGET_USD", 8.0) or 0.0),
            "groq": float(getattr(s, "AI_GROQ_MONTHLY_BUDGET_USD", 2.0) or 0.0),
        },
        "warning_threshold": float(
            getattr(s, "AI_BUDGET_WARNING_THRESHOLD", 0.8) or 0.8),
        "max_input_chars": int(getattr(s, "AI_MAX_INPUT_CHARS", 60000) or 60000),
        "max_output_tokens": int(
            getattr(s, "AI_MAX_OUTPUT_TOKENS", 2000) or 2000),
        "max_concurrent_per_teacher": int(
            getattr(s, "AI_MAX_CONCURRENT_PER_TEACHER", 2) or 2),
        "global_max_concurrent": int(
            getattr(s, "AI_GLOBAL_MAX_CONCURRENT", 8) or 8),
    }


def current_period_keys(at: Optional[datetime] = None) -> tuple[str, str]:
    at = at or datetime.utcnow()
    return at.strftime("%Y-%m"), at.strftime("%Y-%m-%d")


def ensure_prompt_size(prompt: str) -> int:
    """Reject an oversized prompt before a provider is constructed."""
    chars = len(prompt or "")
    limit = budget_config()["max_input_chars"]
    if chars > limit:
        raise AIPromptTooLarge()
    return chars


def enforce_output_cap(provider) -> None:
    """Clamp a provider's completion budget to the server-side ceiling."""
    cap = budget_config()["max_output_tokens"]
    current = getattr(provider, "max_tokens", None)
    try:
        current_int = int(current) if current is not None else cap
    except (TypeError, ValueError):
        current_int = cap
    if current_int > cap:
        provider.max_tokens = cap


def _dialect(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _insert_ignore(db: Session, model, values: dict) -> None:
    if _dialect(db) == "postgresql":
        stmt = _pg_insert(model.__table__).values(**values).on_conflict_do_nothing()
    else:
        stmt = _sqlite_insert(model.__table__).values(**values).on_conflict_do_nothing()
    db.execute(stmt)


def _counter_row(
    db: Session, scope: str, period_key: str, provider: str = "",
) -> AISpendCounterDB:
    row = db.query(AISpendCounterDB).filter(
        AISpendCounterDB.scope == scope,
        AISpendCounterDB.period_key == period_key,
        AISpendCounterDB.provider == provider,
    ).first()
    if row is None:
        _insert_ignore(db, AISpendCounterDB, {
            "id": generate_id(),
            "scope": scope,
            "period_key": period_key,
            "provider": provider,
            "reserved_micros": 0,
            "spent_micros": 0,
            "active_requests": 0,
            "warning_sent": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        db.flush()
        row = db.query(AISpendCounterDB).filter(
            AISpendCounterDB.scope == scope,
            AISpendCounterDB.period_key == period_key,
            AISpendCounterDB.provider == provider,
        ).first()
    return row


def _budget_scopes(provider: str, at: Optional[datetime] = None) -> List[dict]:
    cfg = budget_config()
    monthly_key, daily_key = current_period_keys(at)
    scopes: List[dict] = []
    if cfg["monthly"] > 0:
        scopes.append({
            "scope": "monthly", "period_key": monthly_key, "provider": "",
            "limit_micros": _micros(cfg["monthly"]),
        })
    if cfg["daily"] > 0:
        scopes.append({
            "scope": "daily", "period_key": daily_key, "provider": "",
            "limit_micros": _micros(cfg["daily"]),
        })
    provider_limit = cfg["providers"].get((provider or "").lower(), 0.0)
    if provider_limit > 0:
        scopes.append({
            "scope": "provider_monthly", "period_key": monthly_key,
            "provider": (provider or "").lower(),
            "limit_micros": _micros(provider_limit),
        })
    return scopes


def _reserve_scope(db: Session, scope: dict, amount_micros: int) -> None:
    row = _counter_row(
        db, scope["scope"], scope["period_key"], scope["provider"])
    # Guarded atomic increment: the row only changes when the reserve still
    # fits under the hard budget. A second worker sees the first increment.
    result = db.execute(
        text(
            "UPDATE ai_spend_counters "
            "SET reserved_micros = reserved_micros + :amount, updated_at = :now "
            "WHERE id = :row_id "
            "AND reserved_micros + spent_micros + :amount <= :limit"
        ),
        {
            "amount": int(amount_micros),
            "now": datetime.utcnow(),
            "row_id": row.id,
            "limit": int(scope["limit_micros"]),
        },
    )
    if (result.rowcount or 0) != 1:
        raise AISpendBudgetExceeded()


def _acquire_concurrency(db: Session, user_id: Optional[str]) -> List[dict]:
    cfg = budget_config()
    now = datetime.utcnow()
    # A crashed process cannot hold a slot forever: the expiry is refreshed by
    # every new request and any expired counter is reset before incrementing.
    expiry = now + timedelta(
        seconds=max(120, int(getattr(_settings(), "ZELI_READ_TIMEOUT_SECONDS", 90) or 90) + 60)
    )
    scopes = [
        {
            "scope": "concurrency_global", "period_key": "global",
            "provider": "", "limit": cfg["global_max_concurrent"],
        },
        {
            "scope": "concurrency_user",
            "period_key": user_id or "anonymous",
            "provider": "", "limit": cfg["max_concurrent_per_teacher"],
        },
    ]
    acquired: List[dict] = []
    for item in scopes:
        row = _counter_row(db, item["scope"], item["period_key"], "")
        result = db.execute(
            text(
                "UPDATE ai_spend_counters "
                "SET active_requests = CASE "
                "WHEN expires_at IS NULL OR expires_at < :now THEN 1 "
                "ELSE active_requests + 1 END, "
                "expires_at = :expiry, updated_at = :now "
                "WHERE id = :row_id "
                "AND (expires_at IS NULL OR expires_at < :now "
                "OR active_requests < :limit)"
            ),
            {
                "now": now, "expiry": expiry, "row_id": row.id,
                "limit": int(item["limit"]),
            },
        )
        if (result.rowcount or 0) != 1:
            for done in acquired:
                _release_concurrency_scope(db, done)
            raise AISpendConcurrencyExceeded()
        acquired.append(item)
    return acquired


def _release_concurrency_scope(db: Session, item: dict) -> None:
    db.execute(
        text(
            "UPDATE ai_spend_counters "
            "SET active_requests = CASE WHEN active_requests > 0 "
            "THEN active_requests - 1 ELSE 0 END, updated_at = :now "
            "WHERE scope = :scope AND period_key = :pk AND provider = ''"
        ),
        {
            "now": datetime.utcnow(), "scope": item["scope"],
            "pk": item["period_key"],
        },
    )


class SpendAttempt:
    """One provider attempt with a reserved cost estimate.

    ``finish`` is idempotent per object and records the provider's actual
    ``last_usage`` when available; otherwise it accounts conservatively from
    the configured maximum request size.
    """

    def __init__(
        self,
        db: Session,
        *,
        attempt_id: str,
        reservation_id: str,
        provider: str,
        model: str,
        user_id: Optional[str],
        request_id: Optional[str],
        prompt_chars: int,
        max_output_tokens: int,
        estimated_micros: int,
        budget_scopes: Sequence[dict],
        concurrency_scopes: Sequence[dict],
    ):
        self.db = db
        self.attempt_id = attempt_id
        self.reservation_id = reservation_id
        self.provider = provider
        self.model = model
        self.user_id = user_id
        self.request_id = request_id
        self.prompt_chars = prompt_chars
        self.max_output_tokens = max_output_tokens
        self.estimated_micros = estimated_micros
        self.budget_scopes = list(budget_scopes)
        self.concurrency_scopes = list(concurrency_scopes)
        self._finished = False
        self.cost_micros = 0

    def finish(
        self,
        outcome: str,
        *,
        usage: Optional[Dict[str, Any]] = None,
        error_code: str = "",
    ) -> int:
        if self._finished:
            return self.cost_micros
        self._finished = True
        try:
            self.cost_micros = settle_attempt(
                self, outcome=outcome, usage=usage, error_code=error_code)
        except Exception as exc:  # accounting must never hide real output
            logger.error("ai_spend_settlement_failed", error=str(exc)[:200])
            self.cost_micros = 0
        finally:
            for item in self.concurrency_scopes:
                try:
                    _release_concurrency_scope(self.db, item)
                except Exception:
                    pass
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
        return self.cost_micros


def begin_attempt(
    db: Optional[Session],
    *,
    provider: str,
    model: str,
    prompt_chars: int,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    attempt_id: Optional[str] = None,
) -> Optional[SpendAttempt]:
    """Reserve budget + concurrency and return an attempt to settle.

    Returns ``None`` when spend control is disabled or no DB session is
    available (the caller then behaves exactly as before). Raises a
    teacher-safe ``AISpendError`` when the budget or concurrency cap blocks
    the call, so no provider request is made.
    """
    if db is None:
        return None
    cfg = budget_config()
    if not cfg["enabled"]:
        return None

    provider = (provider or "").strip().lower()
    max_out = int(max_output_tokens or cfg["max_output_tokens"])
    max_out = max(1, min(max_out, cfg["max_output_tokens"]))
    estimated_input_tokens = estimate_tokens(prompt_chars)
    estimated_micros = cost_micros(
        provider, input_tokens=estimated_input_tokens,
        output_tokens=max_out,
    )
    # A reservation must be at least one micro-USD so a zero-price call still
    # participates in the counter guard.
    estimated_micros = max(1, estimated_micros)

    scopes = _budget_scopes(provider)
    attempt_id = attempt_id or str(uuid.uuid4())
    reservation_id = generate_id()

    try:
        with db.begin_nested():
            for scope in scopes:
                _reserve_scope(db, scope, estimated_micros)
            concurrency = _acquire_concurrency(db, user_id)
            db.add(AISpendReservationDB(
                id=reservation_id,
                attempt_id=attempt_id,
                user_id=user_id,
                request_id=request_id,
                provider=provider,
                model=model or "",
                estimated_micros=estimated_micros,
                settled_micros=0,
                status="held",
                scopes=[
                    {
                        "scope": s["scope"], "period_key": s["period_key"],
                        "provider": s["provider"],
                    }
                    for s in scopes
                ],
            ))
        db.commit()
    except AISpendError:
        db.rollback()
        try:
            log_event(
                "ai_budget_stop", user_id=user_id, request_id=request_id,
                provider=provider,
            )
        except Exception:
            pass
        raise
    except Exception as exc:
        db.rollback()
        logger.error("ai_spend_reservation_failed", error=str(exc)[:200])
        raise AISpendError() from exc

    return SpendAttempt(
        db, attempt_id=attempt_id, reservation_id=reservation_id,
        provider=provider, model=model or "", user_id=user_id,
        request_id=request_id, prompt_chars=prompt_chars,
        max_output_tokens=max_out, estimated_micros=estimated_micros,
        budget_scopes=scopes, concurrency_scopes=concurrency,
    )


def _usage_tokens(
    attempt: SpendAttempt, usage: Optional[Dict[str, Any]],
) -> tuple[int, int, int, str, str]:
    """Return (input, cached, output, usage_source, model)."""
    if isinstance(usage, dict):
        try:
            inp = int(usage.get("input_tokens") or 0)
            cached = int(usage.get("cached_input_tokens") or 0)
            out = int(usage.get("output_tokens") or 0)
        except (TypeError, ValueError):
            inp = cached = out = 0
        if inp or out:
            return inp, max(0, min(cached, inp)), out, "actual", str(
                usage.get("model") or attempt.model or "")
    return (
        estimate_tokens(attempt.prompt_chars),
        0,
        int(attempt.max_output_tokens),
        "estimated",
        attempt.model or "",
    )


def settle_attempt(
    attempt: SpendAttempt,
    *,
    outcome: str,
    usage: Optional[Dict[str, Any]],
    error_code: str,
) -> int:
    """Record idempotently and move reserved money to spent."""
    db = attempt.db
    payload_error = (error_code or "").strip().lower()
    if outcome != "success" and any(
        token in payload_error for token in _NO_CALL_ERRORS
    ):
        inp = cached = out = 0
        source = "none"
        model = attempt.model or ""
    else:
        inp, cached, out, source, model = _usage_tokens(attempt, usage)
    actual = cost_micros(
        attempt.provider, input_tokens=inp, output_tokens=out,
        cached_input_tokens=cached,
    )
    if source == "none":
        actual = 0
    total = inp + out

    try:
        with db.begin_nested():
            existing = db.query(AIProviderUsageDB).filter(
                AIProviderUsageDB.attempt_id == attempt.attempt_id
            ).first()
            if existing is not None:
                # Same attempt recorded twice (retry/replay): release the hold
                # and touch no money or usage counters twice.
                row = db.query(AISpendReservationDB).filter(
                    AISpendReservationDB.attempt_id == attempt.attempt_id
                ).first()
                if row is not None and row.status == "held":
                    _release_reservation_scopes(db, row)
                    row.status = "released"
                return int(existing.cost_micros or 0)

            db.add(AIProviderUsageDB(
                id=generate_id(),
                attempt_id=attempt.attempt_id,
                reservation_id=attempt.reservation_id,
                user_id=attempt.user_id,
                request_id=attempt.request_id,
                provider=attempt.provider,
                model=model,
                input_tokens=inp,
                cached_input_tokens=cached,
                output_tokens=out,
                total_tokens=total,
                usage_source=source,
                pricing_version=PRICING_VERSION,
                cost_micros=actual,
                cost_usd=_usd(actual),
                outcome=outcome,
                created_at=datetime.utcnow(),
            ))

            row = db.query(AISpendReservationDB).filter(
                AISpendReservationDB.attempt_id == attempt.attempt_id
            ).first()
            stored = (
                list(row.scopes or []) if row is not None
                else [
                    {
                        "scope": s["scope"], "period_key": s["period_key"],
                        "provider": s["provider"],
                    }
                    for s in attempt.budget_scopes
                ]
            )
            for scope in stored:
                _settle_scope(
                    db, scope, attempt.estimated_micros, actual)
            if row is not None:
                row.settled_micros = actual
                row.status = "settled"
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        _maybe_warn(db)
    except Exception:
        pass
    return actual


def _release_reservation_scopes(db: Session, row: AISpendReservationDB) -> None:
    for scope in list(row.scopes or []):
        db.execute(
            text(
                "UPDATE ai_spend_counters "
                "SET reserved_micros = CASE "
                "WHEN reserved_micros >= :amount "
                "THEN reserved_micros - :amount ELSE 0 END, "
                "updated_at = :now "
                "WHERE scope = :scope AND period_key = :pk "
                "AND provider = :provider"
            ),
            {
                "amount": int(row.estimated_micros or 0),
                "now": datetime.utcnow(),
                "scope": scope.get("scope", ""),
                "pk": scope.get("period_key", ""),
                "provider": scope.get("provider", ""),
            },
        )


def _settle_scope(
    db: Session, scope: dict, reserved_micros: int, actual_micros: int,
) -> None:
    db.execute(
        text(
            "UPDATE ai_spend_counters SET "
            "reserved_micros = CASE WHEN reserved_micros >= :reserved "
            "THEN reserved_micros - :reserved ELSE 0 END, "
            "spent_micros = spent_micros + :actual, updated_at = :now "
            "WHERE scope = :scope AND period_key = :pk "
            "AND provider = :provider"
        ),
        {
            "reserved": int(reserved_micros),
            "actual": int(actual_micros),
            "now": datetime.utcnow(),
            "scope": scope.get("scope", ""),
            "pk": scope.get("period_key", ""),
            "provider": scope.get("provider", ""),
        },
    )


def _maybe_warn(db: Session) -> None:
    cfg = budget_config()
    if cfg["monthly"] <= 0:
        return
    monthly_key, _ = current_period_keys()
    row = db.query(AISpendCounterDB).filter(
        AISpendCounterDB.scope == "monthly",
        AISpendCounterDB.period_key == monthly_key,
        AISpendCounterDB.provider == "",
    ).first()
    if row is None or row.warning_sent:
        return
    committed = int(row.spent_micros or 0)
    limit = _micros(cfg["monthly"])
    if limit <= 0 or committed < int(limit * cfg["warning_threshold"]):
        return
    row.warning_sent = True
    db.commit()
    try:
        log_event(
            "ai_budget_warning",
            spent_usd=_usd(committed),
            budget_usd=cfg["monthly"],
            threshold=cfg["warning_threshold"],
            period=monthly_key,
        )
    except Exception:
        pass
    logger.warning(
        "ai_budget_warning spent_usd=%s budget_usd=%s period=%s",
        _usd(committed), cfg["monthly"], monthly_key,
    )


def release_attempt(attempt: Optional[SpendAttempt]) -> None:
    """Release a reservation that was never used (defensive cleanup)."""
    if attempt is None or attempt._finished:
        return
    attempt._finished = True
    try:
        row = attempt.db.query(AISpendReservationDB).filter(
            AISpendReservationDB.attempt_id == attempt.attempt_id
        ).first()
        if row is not None and row.status == "held":
            with attempt.db.begin_nested():
                _release_reservation_scopes(attempt.db, row)
                row.status = "released"
        attempt.db.commit()
    except Exception:
        attempt.db.rollback()
    finally:
        for item in attempt.concurrency_scopes:
            try:
                _release_concurrency_scope(attempt.db, item)
            except Exception:
                pass
        try:
            attempt.db.commit()
        except Exception:
            attempt.db.rollback()


def budget_status(db: Session, at: Optional[datetime] = None) -> Dict[str, Any]:
    """Safe, secret-free budget snapshot for owners and tests."""
    cfg = budget_config()
    monthly_key, daily_key = current_period_keys(at)

    def _row(scope: str, key: str, provider: str = ""):
        return db.query(AISpendCounterDB).filter(
            AISpendCounterDB.scope == scope,
            AISpendCounterDB.period_key == key,
            AISpendCounterDB.provider == provider,
        ).first()

    monthly = _row("monthly", monthly_key)
    daily = _row("daily", daily_key)
    spent = int(monthly.spent_micros or 0) if monthly else 0
    reserved = int(monthly.reserved_micros or 0) if monthly else 0
    monthly_limit = _micros(cfg["monthly"])
    remaining = max(monthly_limit - spent - reserved, 0) if monthly_limit else 0
    daily_spent = int(daily.spent_micros or 0) if daily else 0
    daily_reserved = int(daily.reserved_micros or 0) if daily else 0
    daily_limit = _micros(cfg["daily"])
    daily_remaining = (
        max(daily_limit - daily_spent - daily_reserved, 0)
        if daily_limit else 0
    )

    providers: Dict[str, Any] = {}
    for name, limit_usd in cfg["providers"].items():
        row = _row("provider_monthly", monthly_key, name)
        p_spent = int(row.spent_micros or 0) if row else 0
        p_reserved = int(row.reserved_micros or 0) if row else 0
        limit = _micros(limit_usd)
        providers[name] = {
            "budget_usd": round(limit_usd, 4),
            "spent_usd": _usd(p_spent),
            "reserved_usd": _usd(p_reserved),
            "remaining_usd": _usd(max(limit - p_spent - p_reserved, 0)),
            "paused": bool(limit and p_spent + p_reserved >= limit),
        }

    return {
        "enabled": cfg["enabled"],
        "pricing_version": PRICING_VERSION,
        "period_monthly": monthly_key,
        "period_daily": daily_key,
        "monthly": {
            "budget_usd": round(cfg["monthly"], 4),
            "spent_usd": _usd(spent),
            "reserved_usd": _usd(reserved),
            "remaining_usd": _usd(remaining),
            "warning_threshold": cfg["warning_threshold"],
            "warning_reached": bool(
                monthly_limit
                and spent >= int(monthly_limit * cfg["warning_threshold"])),
            "paused": bool(monthly_limit and spent + reserved >= monthly_limit),
        },
        "daily": {
            "budget_usd": round(cfg["daily"], 4),
            "spent_usd": _usd(daily_spent),
            "reserved_usd": _usd(daily_reserved),
            "remaining_usd": _usd(daily_remaining),
            "paused": bool(daily_limit and daily_spent + daily_reserved >= daily_limit),
        },
        "providers": providers,
        "max_input_chars": cfg["max_input_chars"],
        "max_output_tokens": cfg["max_output_tokens"],
        "max_concurrent_per_teacher": cfg["max_concurrent_per_teacher"],
        "global_max_concurrent": cfg["global_max_concurrent"],
    }


def usage_summary(db: Session, at: Optional[datetime] = None) -> Dict[str, Any]:
    """Owner-facing usage totals grouped by provider for the current month."""
    at = at or datetime.utcnow()
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.query(
        AIProviderUsageDB.provider,
        func.count(AIProviderUsageDB.id),
        func.coalesce(func.sum(AIProviderUsageDB.input_tokens), 0),
        func.coalesce(func.sum(AIProviderUsageDB.cached_input_tokens), 0),
        func.coalesce(func.sum(AIProviderUsageDB.output_tokens), 0),
        func.coalesce(func.sum(AIProviderUsageDB.cost_micros), 0),
    ).filter(
        AIProviderUsageDB.created_at >= start
    ).group_by(AIProviderUsageDB.provider).all()

    providers = {}
    total_micros = 0
    for name, attempts, inp, cached, out, cost in rows:
        total_micros += int(cost or 0)
        providers[name or "unknown"] = {
            "attempts": int(attempts or 0),
            "input_tokens": int(inp or 0),
            "cached_input_tokens": int(cached or 0),
            "output_tokens": int(out or 0),
            "cost_usd": _usd(int(cost or 0)),
        }
    return {
        "period_monthly": at.strftime("%Y-%m"),
        "pricing_version": PRICING_VERSION,
        "providers": providers,
        "total_cost_usd": _usd(total_micros),
    }

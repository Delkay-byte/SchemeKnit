"""
SchemeKnit Structured Logging

JSON-structured logging for production observability.
"""

import logging
import sys
import time
from datetime import datetime

import structlog


def setup_logging(log_level: str = "INFO"):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def get_logger(name: str = "SchemeKnit"):
    return structlog.get_logger(name)


# Event loggers for audit trail
def log_event(event: str, **kwargs):
    logger = get_logger()
    logger.info(event, **kwargs)


def log_error(event: str, error: str = "", **kwargs):
    logger = get_logger()
    logger.error(event, error=error, **kwargs)


def log_security(event: str, **kwargs):
    logger = get_logger("security")
    logger.warning(event, **kwargs)


_alert_last_sent: dict[str, float] = {}
_ALERT_THROTTLE_SECONDS = 900


def _alert_summary(event: str, severity: str, kwargs: dict) -> str:
    safe = []
    for key, value in kwargs.items():
        text = str(value)
        if len(text) > 300:
            text = text[:300] + "…"
        safe.append(f"{key}={text}")
    return (f"event={event}; severity={severity}; "
            f"time={datetime.utcnow().isoformat()}Z; " + "; ".join(safe))


def alert_security(event: str, severity: str = "warning", **kwargs) -> bool:
    """Record a security event and deliver at most one alert per 15 minutes.

    Delivery uses the configured webhook, then the owner email fallback. The
    structured log entry is always written first. No secret or raw IP is added
    by this function; callers pass HMAC identifiers where applicable.
    """
    log_security(event, severity=severity, **kwargs)
    now = time.time()
    if now - _alert_last_sent.get(event, 0) < _ALERT_THROTTLE_SECONDS:
        return False
    _alert_last_sent[event] = now

    summary = _alert_summary(event, severity, kwargs)
    try:
        from .config import get_settings
        settings = get_settings()
        url = (getattr(settings, "SECURITY_ALERT_WEBHOOK_URL", "") or "").strip()
        owner = (getattr(settings, "OWNER_ALERT_EMAIL", "") or "").strip()
    except Exception:
        return False

    if url:
        try:
            import requests
            response = requests.post(
                url,
                json={"event": event, "severity": severity, **kwargs},
                timeout=5,
            )
            if response.status_code < 300:
                return True
            log_error("security_alert_delivery_failed",
                      error=str(response.status_code))
        except Exception as exc:
            log_error("security_alert_delivery_failed",
                      error=type(exc).__name__)

    if owner:
        try:
            from .email_service import get_email
            result = get_email().send_owner_alert(owner, event, summary)
            return bool(result.success)
        except Exception as exc:
            log_error("owner_alert_delivery_failed", error=type(exc).__name__)
    return False

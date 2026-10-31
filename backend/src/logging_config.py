"""
SchemeKnit Structured Logging

JSON-structured logging for production observability.
"""

import logging
import sys
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


def alert_security(event: str, severity: str = "warning", **kwargs) -> bool:
    """Record a security event and optionally deliver it to a webhook.

    Returns True only when a configured webhook accepted the request. With no
    webhook configured the event is logged and delivery is reported False, so
    callers cannot claim central delivery exists.
    """
    log_security(event, severity=severity, **kwargs)
    try:
        from .config import get_settings
        url = (getattr(get_settings(), "SECURITY_ALERT_WEBHOOK_URL", "") or "").strip()
    except Exception:
        return False
    if not url:
        return False
    try:
        import requests
        response = requests.post(
            url,
            json={"event": event, "severity": severity, **kwargs},
            timeout=5,
        )
        if response.status_code >= 300:
            log_error("security_alert_delivery_failed", error=str(response.status_code))
            return False
        return True
    except Exception as exc:
        log_error("security_alert_delivery_failed", error=type(exc).__name__)
        return False

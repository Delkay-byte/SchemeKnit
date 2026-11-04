"""Idempotent purchase notifications.

Payment fulfilment is authoritative; notifications are best-effort side
effects. A failed email never rolls back credits or a licence. Each channel's
attempt is recorded on the transaction so a retry can see what remains unsent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from . import paystack
from .database import (
    SubscriptionPlanDB, SubscriptionTransactionDB, User, UserLicenseDB,
    UserSubscriptionDB,
)
from .logging_config import log_error, log_event


def _notifications(details: Any) -> Dict[str, Any]:
    out = dict(details) if isinstance(details, dict) else {}
    current = out.get("notifications")
    return dict(current) if isinstance(current, dict) else {}


def _write_state(db: Session, tx: SubscriptionTransactionDB,
                 notifications: Dict[str, Any]) -> None:
    details = dict(tx.payment_details or {}) if isinstance(
        tx.payment_details, dict) else {}
    details["notifications"] = notifications
    tx.payment_details = details
    try:
        db.commit()
    except Exception:
        db.rollback()


def _mark(notifications: Dict[str, Any], channel: str, result: Any,
          error: str = "") -> None:
    entry = dict(notifications.get(channel) or {})
    entry.update({
        "status": "sent" if getattr(result, "success", False) else "failed",
        "attempted_at": datetime.utcnow().isoformat(),
        "attempts": int(entry.get("attempts") or 0) + 1,
        "provider_id": getattr(result, "provider_id", "") or "",
        "error": (str(error) or getattr(result, "message", "") or "")[:200],
    })
    notifications[channel] = entry


def notify_purchase(db: Session, tx: SubscriptionTransactionDB, user: User,
                    plan: SubscriptionPlanDB,
                    sub: Optional[UserSubscriptionDB],
                    lic: Optional[UserLicenseDB]) -> Dict[str, Any]:
    """Send each missing notification once; record every attempt."""
    from .email_service import get_email

    notifications = _notifications(tx.payment_details)
    state = paystack.fulfilment_state(db, tx)
    if tx.status != "success":
        return notifications

    service = get_email()
    sent_any = False

    # Owner notification: every successful paid transaction, with the honest
    # fulfilment state. Persistent visibility also lives on the admin page.
    owner = notifications.get("owner") or {}
    if owner.get("status") != "sent":
        from .config import get_settings
        to = (getattr(get_settings(), "OWNER_ALERT_EMAIL", "") or "").strip()
        if to:
            amount = f"GHS {int(tx.amount_pesewas or 0) / 100:.2f}"
            summary = (
                f"paid purchase {tx.reference}: {plan.name}; amount {amount}; "
                f"channel {tx.channel or tx.payment_method or 'unknown'}; "
                f"account {user.id}; fulfilment {state}"
            )
            result = service.send_owner_purchase(
                to=to,
                plan_name=plan.name,
                amount=amount,
                reference=tx.reference,
                channel=tx.channel or tx.payment_method or "",
                account_ref=user.id,
                fulfilment=state,
            )
            _mark(notifications, "owner", result)
            sent_any = True
        else:
            notifications["owner"] = {
                "status": "not_configured",
                "attempted_at": datetime.utcnow().isoformat(),
                "attempts": 0,
                "error": "OWNER_ALERT_EMAIL is not configured",
            }

    # Customer notification: only describe activation as complete when the
    # licence and credits really exist.
    customer = notifications.get("customer") or {}
    if customer.get("status") != "sent":
        from . import credits as credit_service

        credit_status = credit_service.status(db, user.id)
        amount = f"GHS {int(tx.amount_pesewas or 0) / 100:.2f}"
        result = service.send_subscription_notification(
            to=user.email,
            plan_name=plan.name,
            amount=amount,
            expiry=(sub.paid_through.strftime("%d %B %Y")
                    if sub is not None and sub.paid_through else ""),
            credits_granted=paystack._plan_credit_allowance(plan),
            credit_balance=credit_status.get("total", 0),
            licence_key=(lic.licence_key if lic is not None else ""),
            reference=tx.reference,
            fulfilment=state,
        )
        _mark(notifications, "customer", result)
        sent_any = True

    if sent_any:
        _write_state(db, tx, notifications)
    try:
        log_event(
            "purchase_notifications",
            reference=tx.reference,
            customer=notifications.get("customer", {}).get("status"),
            owner=notifications.get("owner", {}).get("status"),
            fulfilment=state,
        )
    except Exception:
        pass
    return notifications


def retry_pending(db: Session, limit: int = 20) -> int:
    """Retry failed/missing notifications for recent successful purchases."""
    rows = (db.query(SubscriptionTransactionDB)
            .filter(SubscriptionTransactionDB.status == "success")
            .order_by(SubscriptionTransactionDB.created_at.desc())
            .limit(max(1, min(int(limit), 100))).all())
    retried = 0
    for tx in rows:
        details = tx.payment_details or {}
        notes = _notifications(details)
        if all((notes.get(ch) or {}).get("status") in ("sent", "not_configured")
               for ch in ("customer", "owner")):
            continue
        user = db.query(User).filter(User.id == tx.user_id).first()
        plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.id == tx.plan_id).first()
        if user is None or plan is None:
            continue
        sub = db.query(UserSubscriptionDB).filter(
            UserSubscriptionDB.user_id == user.id).first()
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.user_id == user.id).first()
        try:
            notify_purchase(db, tx, user, plan, sub, lic)
            retried += 1
        except Exception as exc:
            log_error("purchase_notification_retry_failed",
                      reference=tx.reference, error=type(exc).__name__)
    return retried

"""Idempotent purchase notifications.

Payment fulfilment is authoritative; notifications are best-effort side
effects. A failed email never rolls back credits or a licence. Each channel's
attempt is recorded on the transaction so a retry can see what remains unsent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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
                    lic: Optional[UserLicenseDB],
                    only_channels: Optional[set] = None) -> Dict[str, Any]:
    """Send each missing notification once; record every attempt.

    ``only_channels`` limits a background retry to the channels that are
    actually due (backoff respected); a direct webhook/verify call leaves it
    unset and sends every missing channel immediately.
    """
    from .email_service import get_email

    notifications = _notifications(tx.payment_details)
    state = paystack.fulfilment_state(db, tx)
    if tx.status != "success":
        return notifications
    details = tx.payment_details if isinstance(tx.payment_details, dict) else {}
    snapshot = details.get("package_snapshot") if isinstance(
        details.get("package_snapshot"), dict) else {}
    package_name = snapshot.get("name") or plan.name
    package_credits = int(snapshot.get("credits")
                          or paystack._plan_credit_allowance(plan))

    service = get_email()
    sent_any = False

    # Owner notification: every successful paid transaction, with the honest
    # fulfilment state. Persistent visibility also lives on the admin page.
    owner = notifications.get("owner") or {}
    if owner.get("status") != "sent" and (
            only_channels is None or "owner" in only_channels):
        from .config import get_settings
        to = (getattr(get_settings(), "OWNER_ALERT_EMAIL", "") or "").strip()
        if to:
            amount = f"GHS {int(tx.amount_pesewas or 0) / 100:.2f}"
            summary = (
                f"paid purchase {tx.reference}: {package_name}; amount {amount}; "
                f"channel {tx.channel or tx.payment_method or 'unknown'}; "
                f"account {user.id}; fulfilment {state}"
            )
            result = service.send_owner_purchase(
                to=to,
                plan_name=package_name,
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
    if customer.get("status") != "sent" and (
            only_channels is None or "customer" in only_channels):
        from . import credits as credit_service

        credit_status = credit_service.status(db, user.id)
        amount = f"GHS {int(tx.amount_pesewas or 0) / 100:.2f}"
        result = service.send_subscription_notification(
            to=user.email,
            plan_name=package_name,
            amount=amount,
            expiry=(sub.paid_through.strftime("%d %B %Y")
                    if sub is not None and sub.paid_through else ""),
            credits_granted=package_credits,
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


#: A notification is attempted at most this many times automatically. Failed
#: records are retained (status stays "failed") for authorised manual recovery.
MAX_NOTIFICATION_ATTEMPTS = 8
#: Base delay for exponential backoff between automatic attempts.
NOTIFICATION_BACKOFF_SECONDS = 60


def _parse_attempted_at(entry: Dict[str, Any]) -> Optional[datetime]:
    raw = entry.get("attempted_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(
            tzinfo=None)
    except ValueError:
        return None


def notification_due(entry: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True when an unsent notification may be attempted automatically.

    Respects the per-channel retry limit and exponential backoff. A record
    already marked ``sent`` or ``not_configured`` is never due.
    """
    if entry.get("status") in ("sent", "not_configured"):
        return False
    attempts = int(entry.get("attempts") or 0)
    if attempts >= MAX_NOTIFICATION_ATTEMPTS:
        return False
    last = _parse_attempted_at(entry)
    if last is None:
        return True
    now = now or datetime.utcnow()
    delay = NOTIFICATION_BACKOFF_SECONDS * (2 ** max(attempts - 1, 0))
    return now - last >= timedelta(seconds=min(delay, 3600))


def retry_pending(db: Session, batch_size: int = 100,
                  max_batches: int = 100) -> int:
    """Recover failed/missing notifications for ALL successful purchases.

    Uses stable keyset pagination (``created_at`` + ``id``) in bounded batches,
    so an old notification gap outside the most recent 20 records is still
    found after a restart. The per-transaction state remains the idempotency
    key per channel: a delivered notification is never resent.
    """
    batch_size = max(1, min(int(batch_size or 100), 500))
    max_batches = max(1, min(int(max_batches or 100), 1000))
    retried = 0
    cursor_id = ""

    for _ in range(max_batches):
        query = db.query(SubscriptionTransactionDB).filter(
            SubscriptionTransactionDB.status == "success")
        if cursor_id:
            query = query.filter(SubscriptionTransactionDB.id > cursor_id)
        rows = (query.order_by(
            SubscriptionTransactionDB.id.asc(),
        ).limit(batch_size).all())
        if not rows:
            break
        cursor_id = rows[-1].id

        now = datetime.utcnow()
        for tx in rows:
            notes = _notifications(tx.payment_details)
            due = {
                channel for channel in ("customer", "owner")
                if notification_due(notes.get(channel) or {}, now)
            }
            if not due:
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
                notify_purchase(db, tx, user, plan, sub, lic,
                                only_channels=due)
                retried += 1
            except Exception as exc:
                log_error("purchase_notification_retry_failed",
                          reference=tx.reference, error=type(exc).__name__)
        if len(rows) < batch_size:
            break
    return retried

"""Paystack subscription service: config, checkout, verification, webhooks.

Secret values are read from the server environment only and never returned.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import (
    EntitlementDB, PaystackWebhookEventDB, SubscriptionEventDB,
    SubscriptionPlanDB, SubscriptionTransactionDB, User, UserLicenseDB,
    UserSubscriptionDB, generate_id,
)

API_BASE = "https://api.paystack.co"
TIMEOUT = 20
GRACE_DAYS = 3


class PaystackError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _secret() -> str:
    return (os.environ.get("PAYSTACK_SECRET_KEY") or "").strip()


def _public() -> str:
    return (os.environ.get("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY")
            or os.environ.get("PAYSTACK_PUBLIC_KEY") or "").strip()


def _paid_enabled() -> bool:
    raw = (os.environ.get("PAYSTACK_ENABLED") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off", "disabled")


def _configured_mode() -> str:
    return (os.environ.get("PAYSTACK_MODE") or "test").strip().lower()


def currency() -> str:
    return (os.environ.get("PAYSTACK_CURRENCY") or "GHS").strip().upper()


def environment() -> str:
    """Return ``test`` or ``live``; refuse mismatched/incomplete configuration.

    A live key is accepted only when ``PAYSTACK_MODE=live`` is also set, so a
    development host cannot accidentally initiate a real-money payment.
    """
    if not _paid_enabled():
        raise PaystackError(
            "Payments are temporarily disabled. No payment was taken.", 503)
    sk, pk = _secret(), _public()
    if not sk:
        raise PaystackError(
            "Paystack is not configured on this server. No payment was taken.",
            503,
        )
    if sk.startswith("sk_test_"):
        env = "test"
    elif sk.startswith("sk_live_"):
        env = "live"
    else:
        raise PaystackError("Paystack configuration is invalid.", 503)
    mode = _configured_mode()
    if mode not in ("test", "live"):
        raise PaystackError(
            "PAYSTACK_MODE must be 'test' or 'live'. No payment was taken.", 503)
    if env != mode:
        raise PaystackError(
            "Paystack key type does not match PAYSTACK_MODE. "
            "No payment was taken.", 503)
    if pk:
        if pk.startswith("sk_"):
            raise PaystackError(
                "A Paystack secret key was supplied in a public-key variable. "
                "No payment was taken.", 503)
        expected = "pk_test_" if env == "test" else "pk_live_"
        if not pk.startswith(expected):
            raise PaystackError(
                "Paystack public and secret keys belong to different environments.",
                503,
            )
    if currency() != "GHS":
        raise PaystackError("Paystack currency must be GHS.", 503)
    return env


def plan_code(plan: SubscriptionPlanDB) -> str:
    env = environment()
    code = (plan.paystack_test_plan_code if env == "test"
            else plan.paystack_live_plan_code) or ""
    if not code:
        raise PaystackError(
            "This plan is not configured for the current Paystack environment. "
            "No payment was taken.",
            503,
        )
    return code.strip()


def _api(method: str, path: str, payload: Optional[dict] = None) -> dict:
    # Validate enabled/mode/key before any network call. This is also the
    # explicit kill switch: PAYSTACK_ENABLED=false fails here.
    environment()
    secret = _secret()
    try:
        resp = requests.request(
            method, f"{API_BASE}{path}", json=payload,
            headers={"Authorization": f"Bearer {secret}",
                     "Content-Type": "application/json"},
            timeout=TIMEOUT,
            verify=True,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise PaystackError(
            "Paystack could not be reached. No payment was taken; please try again.",
            504,
        )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok or not body.get("status"):
        message = str(body.get("message") or "")
        if resp.status_code in (401, 403):
            raise PaystackError("Paystack rejected the server credentials.", 503)
        if resp.status_code == 429:
            raise PaystackError(
                "Paystack is busy. No payment was taken; please try again.", 429)
        raise PaystackError(
            "Paystack could not start the payment. No payment was taken.", 502)
    return body.get("data") or {}


def initialize(plan: SubscriptionPlanDB, user: User, reference: str,
               callback_url: str) -> Dict[str, Any]:
    """Card checkout is retired from the customer-facing flow.

    The route returns a clear 410 before reaching here; this guard makes the
    server-side refusal explicit even if an old client calls the service.
    """
    raise PaystackError(
        "Card checkout is no longer available. Please pay by Bank Transfer "
        "or Mobile Money.", 410,
    )


def charge_bank_transfer(plan: SubscriptionPlanDB, user: User, reference: str,
                         account_expires_at: Optional[datetime] = None) -> dict:
    """Start Paystack's Ghana Pay-with-Transfer charge.

    Paystack returns a temporary bank account in ``data`` with
    ``status=pending_bank_transfer``. The package activates only after a
    verified ``charge.success`` webhook (or a successful verify call).
    """
    expiry = account_expires_at or (datetime.utcnow() + timedelta(hours=8))
    payload = {
        "email": user.email,
        "amount": int(plan.price_pesewas),
        "currency": "GHS",
        "reference": reference,
        "bank_transfer": {
            "account_expires_at": expiry.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        },
        "metadata": {
            "user_id": user.id, "plan_id": plan.id, "plan_slug": plan.slug,
            "environment": environment(), "billing_mode": "prepaid",
            "payment_method": "bank_transfer",
        },
    }
    return _api("POST", "/charge", payload)


def verify(reference: str) -> dict:
    return _api("GET", f"/transaction/verify/{reference}")


# Ghana Mobile Money provider codes (Paystack docs).
MOMO_PROVIDERS = {"mtn": "mtn", "telecel": "vod", "vod": "vod",
                  "airteltigo": "atl", "atl": "atl"}
MOMO_PREFIXES = {
    "mtn": ("024", "054", "055", "059"),
    "vod": ("020", "050"),
    "atl": ("026", "027", "056", "057"),
}


def normalize_momo(provider: str, phone: str) -> Tuple[str, str]:
    code = MOMO_PROVIDERS.get((provider or "").strip().lower())
    if not code:
        raise PaystackError("Choose MTN, Telecel or AirtelTigo Mobile Money.", 400)
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("233") and len(digits) == 12:
        digits = "0" + digits[3:]
    if len(digits) != 10 or not digits.startswith("0"):
        raise PaystackError("Enter a valid 10-digit Ghana Mobile Money number.", 400)
    if not digits.startswith(MOMO_PREFIXES[code]):
        raise PaystackError(
            "That number does not match the selected Mobile Money provider.", 400)
    return code, digits


def charge_mobile_money(plan: SubscriptionPlanDB, user: User, reference: str,
                        provider: str, phone: str) -> dict:
    """Start a one-time Mobile Money charge (no recurring authorisation)."""
    code, digits = normalize_momo(provider, phone)
    payload = {
        "email": user.email,
        "amount": int(plan.price_pesewas),
        "currency": "GHS",
        "reference": reference,
        "mobile_money": {"phone": digits, "provider": code},
        "metadata": {
            "user_id": user.id, "plan_id": plan.id, "plan_slug": plan.slug,
            "environment": environment(), "billing_mode": "prepaid",
            "provider": code,
        },
    }
    return _api("POST", "/charge", payload)


def check_charge(reference: str) -> dict:
    return _api("GET", f"/charge/{reference}")



def _licence_key() -> str:
    raw = secrets.token_hex(16).upper()
    return "TF-" + "-".join(raw[i:i + 4] for i in range(0, 32, 4))


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _update_entitlement(db: Session, user_id: str, plan: SubscriptionPlanDB,
                        paid_through: datetime, is_timed: bool = True) -> None:
    ent = db.query(EntitlementDB).filter(EntitlementDB.user_id == user_id).first()
    cfg = plan.entitlements or {}
    if ent is None:
        ent = EntitlementDB(id=generate_id(), user_id=user_id)
        db.add(ent)
    ent.edition = "teacher"
    ent.subscription_type = "individual"
    ent.status = "active"
    ent.source = "paystack"
    # A flexible pack has no period of its own; it must not clear an active
    # timed package's expiry.
    if is_timed or ent.expires_at is None:
        ent.expires_at = paid_through
    ent.generation_limit = int(cfg.get("generation_limit", 0) or 0)
    ent.batch_generation = bool(cfg.get("batch_generation", True))
    ent.zip_export = bool(cfg.get("zip_export", True))
    ent.pdf_export = bool(cfg.get("pdf_export", True))
    ent.ai_enabled = bool(cfg.get("ai_enabled", True))
    ent.ai_credits = int(cfg.get("ai_credits", 0) or 0)
    ent.max_lessons_per_scheme = int(cfg.get("max_lessons_per_scheme", 50) or 50)

def _event(db: Session, sub: UserSubscriptionDB, kind: str,
           from_status: str, to_status: str, meta: dict) -> None:
    db.add(SubscriptionEventDB(
        id=generate_id(), subscription_id=sub.id, event_type=kind,
        from_status=from_status or "", to_status=to_status or "",
        metadata_json=meta or {},
    ))


def activate_paid_transaction(db: Session, tx: SubscriptionTransactionDB,
                              payload: dict) -> Tuple[UserSubscriptionDB, UserLicenseDB]:
    """Idempotently credit ONE verified transaction and issue/renew the licence."""
    # Serialize concurrent webhook + verify attempts on the transaction row.
    # SQLite ignores FOR UPDATE; PostgreSQL (production) blocks the second
    # caller until the first commits, then that caller sees status=success.
    locked = (db.query(SubscriptionTransactionDB)
              .filter(SubscriptionTransactionDB.id == tx.id)
              .with_for_update().first())
    if locked is not None:
        tx = locked
    else:
        db.refresh(tx)
    if tx.status == "success":
        sub = (db.query(UserSubscriptionDB)
               .filter(UserSubscriptionDB.user_id == tx.user_id).first())
        lic = (db.query(UserLicenseDB)
               .filter(UserLicenseDB.user_id == tx.user_id).first())
        return sub, lic
    if tx.status in ("failed", "reversed", "refunded"):
        # A failed/reversed payment must never be activated by a late or
        # duplicate success delivery.
        raise PaystackError(
            "This payment is not eligible for activation.", 409)

    plan = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.id == tx.plan_id).first()
    user = db.query(User).filter(User.id == tx.user_id).first()
    if plan is None or user is None:
        raise PaystackError("The local payment record is incomplete.", 500)

    _validate_verified_payment(tx, payload, user)

    paid_at = datetime.utcnow()
    raw_paid = payload.get("paid_at") or payload.get("paidAt")
    if raw_paid:
        try:
            paid_at = datetime.fromisoformat(str(raw_paid).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass

    sub = (db.query(UserSubscriptionDB)
           .filter(UserSubscriptionDB.user_id == user.id).first())
    if sub is None:
        sub = UserSubscriptionDB(id=generate_id(), user_id=user.id,
                                 plan_id=plan.id)
        db.add(sub)
        db.flush()
    old_status = sub.status or ""

    # A flexible credit pack is not a period-limited package: it must never
    # shorten an existing timed package, and it has no expiry of its own.
    kind = getattr(plan, "package_kind", "") or "timed"
    is_timed = kind == "timed"
    if is_timed:
        base = sub.paid_through or paid_at
        if base < paid_at:
            base = paid_at
        paid_through = base + timedelta(days=int(plan.duration_days or 0))
    else:
        paid_through = sub.paid_through

    # Older transactions reconciled after a newer payment still earn their
    # credits, but must not move the account's period start backwards.
    is_late_reconciliation = bool(
        sub.current_period_start and paid_at < sub.current_period_start)

    sub.plan_id = plan.id
    sub.provider = "paystack"
    sub.environment = tx.environment
    if not is_late_reconciliation:
        sub.billing_mode = "prepaid"
        if tx.payment_method in ("mobile_money", "bank_transfer"):
            sub.payment_method = tx.payment_method
        else:
            # Historical card transaction reconciled late: keep the account's
            # existing prepaid method instead of relabelling it as card.
            sub.payment_method = sub.payment_method or "card"
        sub.provider = tx.provider or sub.payment_method
        sub.current_period_start = paid_at
    sub.status = "active"
    sub.current_period_end = paid_through
    sub.paid_through = paid_through
    sub.grace_until = None
    sub.cancel_at_period_end = False
    customer_payload = (payload.get("customer")
                        if isinstance(payload.get("customer"), dict) else {})
    sub.provider_customer_code = str(
        customer_payload.get("customer_code")
        or sub.provider_customer_code or "")
    plan_field = payload.get("plan")
    sub.provider_subscription_code = str(
        ((plan_field.get("subscription_code") if isinstance(plan_field, dict) else "")
         or (payload.get("subscription_code") if isinstance(payload.get("subscription_code"), str) else "")
         or sub.provider_subscription_code or ""))

    lic = db.query(UserLicenseDB).filter(
        UserLicenseDB.user_id == user.id).first()
    licence_expiry = paid_through
    if lic is None:
        key = _licence_key()
        lic = UserLicenseDB(
            id=generate_id(), user_id=user.id, plan_id=plan.id,
            subscription_id=sub.id, licence_key=key,
            key_hash=_hash_key(key), status="active",
            issued_at=paid_at, starts_at=paid_at, expires_at=licence_expiry,
            activated_at=paid_at,
        )
        db.add(lic)
    else:
        lic.plan_id = plan.id
        lic.subscription_id = sub.id
        lic.status = "active"
        if is_timed or licence_expiry is None:
            lic.expires_at = licence_expiry

    _update_entitlement(db, user.id, plan, paid_through, is_timed=is_timed)
    tx.status = "success"
    tx.provider_transaction_id = str(payload.get("id") or "")
    tx.channel = str(payload.get("channel") or "")
    tx.paid_at = paid_at
    tx.subscription_id = sub.id
    tx.payment_method = sub.payment_method
    tx.provider = sub.provider
    _event(db, sub, "payment_success", old_status, "active",
           {"reference": tx.reference, "amount": tx.amount_pesewas})

    # Exactly once per verified transaction (unique grant key).
    from . import credits
    credits.grant_package(
        db, user.id, plan, tx.reference, activated_at=paid_at, commit=False)
    db.commit()
    db.refresh(sub)
    db.refresh(lic)

    # Referral rewards are best-effort AFTER the paid entitlement is durable;
    # a failure here must never revoke a payment the customer made.
    try:
        from . import referrals
        referrals.qualify(db, user, tx)
    except Exception:
        db.rollback()
    _notify(user, plan, paid_through, tx.amount_pesewas)
    return sub, lic


def _validate_verified_payment(tx: SubscriptionTransactionDB, payload: dict,
                               user: User) -> None:
    """Verify status, reference, amount, currency, channel, package and customer."""
    if str(payload.get("status") or "").lower() != "success":
        raise PaystackError("Paystack has not confirmed this payment.", 400)
    if str(payload.get("reference") or "") != tx.reference:
        raise PaystackError("Payment reference does not match this transaction.", 400)
    if int(payload.get("amount") or 0) != int(tx.amount_pesewas):
        raise PaystackError("Payment amount does not match the package.", 400)
    if str(payload.get("currency") or "").upper() != "GHS":
        raise PaystackError("Payment currency is not GHS.", 400)
    if tx.environment and tx.environment != environment():
        raise PaystackError("Payment environment does not match this server.", 400)

    channel = str(payload.get("channel") or "").strip().lower()
    if tx.payment_method in ("bank_transfer", "mobile_money"):
        expected = tx.payment_method
        if channel != expected:
            raise PaystackError(
                "Payment channel is not one of the approved prepaid methods.", 400)

    metadata = payload.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("user_id"):
            if str(metadata["user_id"]) != str(tx.user_id):
                raise PaystackError("Payment belongs to a different account.", 400)
        if metadata.get("plan_id"):
            if str(metadata["plan_id"]) != str(tx.plan_id):
                raise PaystackError("Payment package does not match this purchase.", 400)
        if metadata.get("environment"):
            if str(metadata["environment"]).lower() != str(tx.environment).lower():
                raise PaystackError("Payment environment does not match this purchase.", 400)

    customer = (payload.get("customer")
                if isinstance(payload.get("customer"), dict) else {})
    email = str(customer.get("email") or "").strip().lower()
    if email and email != (user.email or "").strip().lower():
        raise PaystackError("Payment customer does not match this account.", 400)


def _notify(user: User, plan: SubscriptionPlanDB, paid_through: datetime,
            amount_pesewas: int = 0) -> None:
    """Best-effort email; never fails the verified payment."""
    try:
        from .email_service import get_email
        get_email().send_subscription_notification(
            to=user.email, plan_name=plan.name,
            amount=f"GHS {int(amount_pesewas or plan.price_pesewas) / 100:.2f}",
            expiry=paid_through.strftime("%d %B %Y"),
        )
    except Exception:
        pass


def event_key(event: str, data: dict) -> str:
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    ident = (
        data.get("id")
        or data.get("refund_reference")
        or data.get("transaction_reference")
        or data.get("reference")
        or data.get("invoice_code")
        or data.get("subscription_code")
        or customer.get("email")
        or ""
    )
    # Refund lifecycle events for one transaction share a reference but have
    # distinct statuses (pending → processing → processed). Include the status
    # so a later lifecycle event is not mistaken for a duplicate delivery.
    return f"{event}:{ident}:{data.get('status', '')}"


def verify_signature(raw: bytes, signature: str) -> bool:
    try:
        environment()
    except PaystackError:
        return False
    secret = _secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def record_webhook(db: Session, event: str, data: dict, raw: bytes) -> Tuple[PaystackWebhookEventDB, bool]:
    key = event_key(event, data)
    row = PaystackWebhookEventDB(
        id=generate_id(), event_key=key, event_type=event,
        reference=str(data.get("reference") or ""),
        payload_hash=hashlib.sha256(raw).hexdigest(),
    )
    db.add(row)
    try:
        db.commit()
        return row, True
    except IntegrityError:
        db.rollback()
        existing = db.query(PaystackWebhookEventDB).filter(
            PaystackWebhookEventDB.event_key == key).first()
        return existing, False


def handle_webhook(db: Session, event: str, data: dict) -> None:
    sub = None
    code = data.get("subscription_code") or (
        (data.get("subscription") or {}).get("subscription_code"))
    if code:
        sub = db.query(UserSubscriptionDB).filter(
            UserSubscriptionDB.provider_subscription_code == code).first()
    if sub is None and isinstance(data.get("customer"), dict) \
            and data["customer"].get("email"):
        user = db.query(User).filter(
            User.email == data["customer"]["email"]).first()
        if user:
            sub = db.query(UserSubscriptionDB).filter(
                UserSubscriptionDB.user_id == user.id).first()

    if event == "charge.success":
        ref = str(data.get("reference") or "")
        tx = db.query(SubscriptionTransactionDB).filter(
            SubscriptionTransactionDB.reference == ref).first()
        if tx is None:
            return
        verified = verify(ref)
        _validate_verified_payment(
            tx, verified, db.query(User).filter(User.id == tx.user_id).first())
        activate_paid_transaction(db, tx, verified)
        return

    if event == "bank.transfer.rejected":
        # Documented for Ghana Pay with Transfer: an incorrect amount or a
        # rejected transfer. Never grant credits.
        ref = str(data.get("reference") or "")
        tx = db.query(SubscriptionTransactionDB).filter(
            SubscriptionTransactionDB.reference == ref).first()
        if tx is not None and tx.status != "success":
            tx.status = "failed"
            tx.charge_status = str(data.get("status") or event)
            tx.instructions = str(data.get("gateway_response") or data.get("message") or "")
            db.commit()
        return

    if event in (
        "refund.pending", "refund.processing", "refund.needs-attention",
        "refund.failed", "refund.processed",
    ):
        tx_data = (data.get("transaction")
                   if isinstance(data.get("transaction"), dict) else {})
        ref = str(
            data.get("transaction_reference")
            or data.get("reference")
            or tx_data.get("reference")
            or ""
        )
        tx = db.query(SubscriptionTransactionDB).filter(
            SubscriptionTransactionDB.reference == ref).first()
        if tx is None:
            return
        details = dict(tx.payment_details or {}) if isinstance(tx.payment_details, dict) else {}
        details["refund_status"] = str(data.get("status") or event.split(".", 1)[-1])
        details["refund_reference"] = str(data.get("refund_reference") or "")
        details["refund_updated_at"] = datetime.utcnow().isoformat()
        tx.payment_details = details
        if event == "refund.processed":
            # Only a processed refund is a completed reversal. Pending,
            # processing, needs-attention and failed refunds never revoke
            # credits or entitlements.
            tx.status = "reversed"
            db.commit()
            from . import referrals
            referrals.reverse_for_transaction(db, tx, reason="Paystack refund.processed")
        else:
            db.commit()
        return

    if sub is None:
        return
    old = sub.status
    if event == "subscription.create":
        sub.provider_subscription_code = code or sub.provider_subscription_code
        sub.provider_email_token = str(data.get("email_token") or "")
        sub.status = "active"
    elif event == "invoice.create":
        sub.status = sub.status
    elif event == "invoice.update":
        status = str(data.get("status") or "").lower()
        if status == "success":
            # Successful invoice: extend once per invoice event key.
            plan = db.query(SubscriptionPlanDB).filter(
                SubscriptionPlanDB.id == sub.plan_id).first()
            if plan:
                base = sub.paid_through or datetime.utcnow()
                sub.paid_through = base + timedelta(days=int(plan.duration_days))
                sub.current_period_end = sub.paid_through
                sub.status = "active"
                sub.grace_until = None
                _update_entitlement(db, sub.user_id, plan, sub.paid_through)
    elif event == "invoice.payment_failed":
        sub.status = "past_due"
        sub.grace_until = datetime.utcnow() + timedelta(days=GRACE_DAYS)
    elif event == "subscription.not_renew":
        sub.status = "non_renewing"
        sub.cancel_at_period_end = True
    elif event == "subscription.disable":
        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()
    elif event == "subscription.expiring_cards":
        pass
    _event(db, sub, event, old, sub.status, {"reference": data.get("reference", "")})
    db.commit()


def expire_overdue(db: Session) -> int:
    now = datetime.utcnow()
    rows = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.status.in_(("active", "past_due", "non_renewing")),
        UserSubscriptionDB.paid_through.isnot(None),
        UserSubscriptionDB.paid_through < now,
    ).all()
    changed = 0
    for sub in rows:
        grace = sub.grace_until or sub.paid_through
        if grace and grace >= now:
            continue
        old = sub.status
        sub.status = "expired"
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.user_id == sub.user_id).first()
        if lic:
            lic.status = "expired"
        ent = db.query(EntitlementDB).filter(
            EntitlementDB.user_id == sub.user_id).first()
        if ent and ent.source == "paystack":
            ent.status = "expired"
            ent.expires_at = sub.paid_through
        _event(db, sub, "expired", old, "expired", {})
        changed += 1
    if changed:
        db.commit()
    return changed


def cancel_subscription(db: Session, sub: UserSubscriptionDB) -> None:
    if sub.provider_subscription_code:
        _api("POST", "/subscription/disable", {
            "code": sub.provider_subscription_code,
            "token": sub.provider_email_token,
        })
    old = sub.status
    sub.status = "non_renewing"
    sub.cancel_at_period_end = True
    sub.cancelled_at = datetime.utcnow()
    _event(db, sub, "cancelled_by_user", old, sub.status, {})
    db.commit()

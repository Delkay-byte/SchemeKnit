"""Paystack subscription service: config, checkout, verification, webhooks.

Secret values are read from the server environment only and never returned.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import requests
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from .database import (
    EntitlementDB, PaystackWebhookEventDB, PurchaseEntitlementDB,
    SubscriptionEventDB, SubscriptionPlanDB, SubscriptionTransactionDB, User,
    UserLicenseDB, UserSubscriptionDB, generate_id,
)

logger = logging.getLogger(__name__)

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


def package_snapshot(plan: SubscriptionPlanDB) -> dict:
    """Immutable package details captured at purchase initiation."""
    entitlement = dict(plan.entitlements or {})
    return {
        "plan_id": plan.id,
        "slug": plan.slug,
        "name": plan.name,
        "package_kind": getattr(plan, "package_kind", "") or "timed",
        "price_pesewas": int(plan.price_pesewas or 0),
        "currency": plan.currency or "GHS",
        "credits": int(getattr(plan, "credit_allowance", 0) or 0)
        or int(entitlement.get("credit_allowance", 0) or 0),
        "duration_days": int(plan.duration_days or 0),
        "credit_validity_days": getattr(plan, "credit_validity_days", None),
    }


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


def _api(method: str, path: str, payload: Optional[dict] = None, *,
         preserve_client_errors: bool = False) -> dict:
    # Validate enabled/mode/key before any network call. This is also the
    # explicit kill switch: PAYSTACK_ENABLED=false fails here.
    environment()
    secret = _secret()
    try:
        resp = requests.request(
            method, f"{API_BASE}{path}", json=payload,
            headers={"Authorization": f"Bearer {secret}",
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     # Paystack's edge rejects generic urllib/python-requests
                     # user agents with Cloudflare 1010. An explicit client
                     # identity keeps production and staging charges working.
                     "User-Agent": "SchemeKnit/1.0 (+https://schemeknit.com)"},
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
        # Status + provider message only; never headers or the secret key.
        logger.warning(
            "paystack_api_error path=%s status=%s message=%s",
            path, resp.status_code, message[:200])
        if resp.status_code in (401, 403):
            raise PaystackError("Paystack rejected the server credentials.", 503)
        if resp.status_code == 429:
            raise PaystackError(
                "Paystack is busy. No payment was taken; please try again.", 429)
        if preserve_client_errors and 400 <= resp.status_code < 500:
            # Submit-OTP validation errors must stay retryable and readable;
            # the caller maps them to a teacher-facing message.
            raise PaystackError(
                message or "Paystack rejected the request; please try again.",
                resp.status_code)
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


def submit_charge_otp(reference: str, otp: str) -> dict:
    """Submit the Paystack OTP for a charge awaiting ``send_otp``.

    The OTP is sent only to Paystack in this request body; it is never logged,
    stored, or returned by this module.
    """
    return _api("POST", "/charge/submit_otp", {
        "reference": reference,
        "otp": otp,
    }, preserve_client_errors=True)



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
    # timed package's expiry. It DOES clear an already-elapsed expiry, because
    # the shared entitlement row is what grants access and the new pack is
    # still valid.
    if is_timed:
        ent.expires_at = paid_through
    elif ent.expires_at is not None and ent.expires_at < datetime.utcnow():
        ent.expires_at = None
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


def _plan_credit_allowance(plan: SubscriptionPlanDB) -> int:
    entitlement = (plan.entitlements or {}) if plan is not None else {}
    return int(getattr(plan, "credit_allowance", 0) or 0) or int(
        entitlement.get("credit_allowance", 0) or 0)


def _tx_package(tx: SubscriptionTransactionDB,
                plan: SubscriptionPlanDB) -> Dict[str, Any]:
    """The immutable package snapshot, or a safe live-plan fallback."""
    details = tx.payment_details if isinstance(tx.payment_details, dict) else {}
    snapshot = details.get("package_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("slug"):
        return snapshot
    return package_snapshot(plan)


def _with_fulfilment_state(details: Any, **values: Any) -> dict:
    out = dict(details) if isinstance(details, dict) else {}
    current = out.get("fulfilment")
    fulfilment = dict(current) if isinstance(current, dict) else {}
    fulfilment.update(values)
    out["fulfilment"] = fulfilment
    return out


def _credit_grant_for(db: Session, tx: SubscriptionTransactionDB):
    from .database import CreditBalanceDB

    return (db.query(CreditBalanceDB)
            .filter(CreditBalanceDB.grant_key == f"package:{tx.reference}")
            .first())


def purchase_entitlement(db: Session, reference: str) -> Optional[PurchaseEntitlementDB]:
    """The entitlement row owned by one transaction reference (or None).

    Tolerates a database that has not yet applied v054 (rolling deploy or a
    read-only reconciliation before migration): callers fall back to the
    legacy licence/credit evidence instead of failing.
    """
    try:
        return (db.query(PurchaseEntitlementDB)
                .filter(PurchaseEntitlementDB.reference == reference).first())
    except (ProgrammingError, OperationalError):
        db.rollback()
        return None


def active_purchase_entitlements(db: Session, user_id: str,
                                 now: Optional[datetime] = None,
                                 ) -> list[PurchaseEntitlementDB]:
    """Live purchased entitlements: flexible always, timed only while in date."""
    now = now or datetime.utcnow()
    try:
        rows = (db.query(PurchaseEntitlementDB)
                .filter(PurchaseEntitlementDB.user_id == user_id,
                        PurchaseEntitlementDB.status == "active")
                .order_by(PurchaseEntitlementDB.starts_at.desc()).all())
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []
    return [row for row in rows
            if row.kind == "flexible"
            or row.expires_at is None
            or row.expires_at > now]


def has_live_flexible_entitlement(db: Session, user_id: str) -> bool:
    """True when the teacher still owns a flexible pack (independent of time)."""
    try:
        return (db.query(PurchaseEntitlementDB.id)
                .filter(PurchaseEntitlementDB.user_id == user_id,
                        PurchaseEntitlementDB.kind == "flexible",
                        PurchaseEntitlementDB.status == "active").first()) is not None
    except (ProgrammingError, OperationalError):
        db.rollback()
        return False


def _record_purchase_entitlement(
    db: Session, tx: SubscriptionTransactionDB, plan: SubscriptionPlanDB,
    user: User, sub: Optional[UserSubscriptionDB],
    lic: Optional[UserLicenseDB], paid_at: datetime, snapshot: dict,
) -> PurchaseEntitlementDB:
    """Upsert the entitlement row for this exact transaction.

    Idempotent: the row is keyed by the payment reference, so repeated
    webhook/verify/reconcile deliveries update the same entitlement. A timed
    row already expired by its own lifecycle is never resurrected by a repair.
    """
    kind = snapshot.get("package_kind") or "timed"
    ent = purchase_entitlement(db, tx.reference)
    if ent is None:
        ent = PurchaseEntitlementDB(
            id=generate_id(), user_id=user.id, reference=tx.reference,
            status="active",
        )
        db.add(ent)
    ent.plan_id = plan.id if plan is not None else tx.plan_id
    ent.package_slug = (snapshot.get("slug")
                        or (plan.slug if plan is not None else ""))
    ent.package_name = (snapshot.get("name")
                        or (plan.name if plan is not None else ""))
    ent.kind = kind
    ent.starts_at = paid_at
    if kind == "timed":
        duration = int(snapshot.get("duration_days")
                       or (plan.duration_days if plan is not None else 0) or 0)
        if sub is not None and sub.paid_through:
            ent.expires_at = sub.paid_through
        elif duration:
            ent.expires_at = paid_at + timedelta(days=duration)
    else:
        # A flexible credit pack has no subscription period of its own.
        ent.expires_at = None
    if ent.status != "revoked":
        if kind == "timed" and ent.expires_at and ent.expires_at < datetime.utcnow():
            # A late reconciliation of an already-elapsed period is fulfilled
            # historically, but it is not a live entitlement.
            ent.status = "expired"
        elif ent.status != "expired":
            ent.status = "active"
    ent.licence_id = lic.id if lic is not None else ent.licence_id
    ent.updated_at = datetime.utcnow()
    return ent


def _repair_fulfilment(db: Session, tx: SubscriptionTransactionDB,
                       plan: SubscriptionPlanDB, user: User,
                       sub: Optional[UserSubscriptionDB],
                       lic: Optional[UserLicenseDB]) -> bool:
    """Heal a successful payment whose licence/credits are missing.

    Safe to repeat: every write is keyed by the original transaction and the
    credit grant uses the unique ``package:<reference>`` idempotency key.
    Does not extend a timed package again and does not move the period start.
    """
    repaired = False
    paid_at = tx.paid_at or datetime.utcnow()
    if tx.paid_at is None:
        tx.paid_at = paid_at
        repaired = True
    snapshot = _tx_package(tx, plan)
    kind = snapshot.get("package_kind") or "timed"
    if sub is None:
        sub = UserSubscriptionDB(
            id=generate_id(), user_id=user.id, plan_id=plan.id,
            status="active", billing_mode="prepaid",
            payment_method=tx.payment_method or "mobile_money",
            provider=tx.provider or "paystack", environment=tx.environment,
            current_period_start=paid_at, current_period_end=paid_at,
            paid_through=paid_at,
        )
        if kind == "timed":
            sub.current_period_end = paid_at + timedelta(
                days=int(snapshot.get("duration_days") or 0))
            sub.paid_through = sub.current_period_end
        db.add(sub)
        db.flush()
        repaired = True
    if lic is None:
        key = _licence_key()
        licence_expiry = sub.paid_through if kind == "timed" else None
        lic = UserLicenseDB(
            id=generate_id(), user_id=user.id, plan_id=plan.id,
            subscription_id=sub.id, licence_key=key,
            key_hash=_hash_key(key), status="active",
            issued_at=paid_at, starts_at=paid_at, expires_at=licence_expiry,
            activated_at=paid_at,
        )
        db.add(lic)
        db.flush()
        repaired = True
    elif kind == "flexible" and (lic.status != "active"
                                 or (lic.expires_at
                                     and lic.expires_at < datetime.utcnow())):
        # A flexible pack keeps the internal licence usable; a timed package
        # expiry elsewhere must not revoke it.
        lic.status = "active"
        lic.expires_at = None
        repaired = True

    expected_credits = int(snapshot.get("credits") or 0)
    balance = _credit_grant_for(db, tx)
    if expected_credits > 0 and balance is None:
        from . import credits as credit_service

        balance = credit_service.grant_package(
            db, user.id, plan, tx.reference, activated_at=paid_at,
            commit=False,
            credits_override=expected_credits,
            kind_override=kind,
            days_override=snapshot.get("duration_days"),
            label_override=snapshot.get("name"),
            slug_override=snapshot.get("slug"),
        )
        if balance is None:
            raise PaystackError(
                "The package credit grant could not be created.", 500)
        repaired = True

    _update_entitlement(
        db, user.id, plan, sub.paid_through or paid_at,
        is_timed=kind == "timed")
    _record_purchase_entitlement(
        db, tx, plan, user, sub, lic, paid_at, snapshot)
    tx.payment_details = _with_fulfilment_state(
        tx.payment_details,
        state="activated",
        plan_credits=expected_credits,
        licence_id=lic.id,
        credit_grant_key=f"package:{tx.reference}" if balance is not None else "",
        activated_at=(tx.paid_at or paid_at).isoformat(),
        repaired_at=(datetime.utcnow().isoformat() if repaired else None),
    )
    if repaired:
        _event(db, sub, "fulfilment_repaired", "active", "active",
               {"reference": tx.reference, "credits": expected_credits})
    return repaired


def fulfilment_state(db: Session, tx: SubscriptionTransactionDB) -> str:
    """Payment/fulfilment state for the API (never a provider claim).

    Fulfilment is scoped to THIS transaction. A flexible purchase must not be
    called ``needs_attention`` merely because an unrelated timed package on the
    same account has expired.
    """
    status = str(tx.status or "").lower()
    if status in ("failed", "expired"):
        return "payment_failed"
    if status in ("reversed", "refunded"):
        return "payment_reversed"
    if status != "success":
        if status == "pending" and str(tx.charge_status or "").lower() == "success":
            # Paystack already confirmed the charge but local activation did
            # not finish. This is not "pending payment" and must never invite
            # a second payment.
            details = tx.payment_details if isinstance(tx.payment_details, dict) else {}
            fulfilment = details.get("fulfilment") if isinstance(
                details.get("fulfilment"), dict) else {}
            return ("needs_attention" if fulfilment.get("error")
                    else "processing")
        return "payment_pending"
    plan = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.id == tx.plan_id).first()
    balance = _credit_grant_for(db, tx)
    expected = (int((_tx_package(tx, plan) if plan is not None else {})
                    .get("credits") or 0))

    entitlement = purchase_entitlement(db, tx.reference)
    lic = None
    if entitlement is not None and entitlement.licence_id:
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.id == entitlement.licence_id).first()
    if lic is None:
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.user_id == tx.user_id).first()
    if entitlement is not None:
        if entitlement.status == "revoked":
            return "needs_attention"
        if lic is None or (expected > 0 and balance is None):
            return "needs_attention"
        return "activated"

    # Legacy compatibility (records created before v054): the grant/ledger is
    # the durable proof of fulfilment. An expired licence for a different,
    # later product is not evidence that this purchase was never fulfilled.
    if lic is None:
        return "needs_attention"
    if expected > 0 and balance is None:
        return "needs_attention"
    return "activated"


def purchase_payload(db: Session, tx: SubscriptionTransactionDB) -> dict:
    """Everything the confirmation UI needs, in one redacted object."""
    from . import credits as credit_service

    plan = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.id == tx.plan_id).first()
    user = db.query(User).filter(User.id == tx.user_id).first()
    sub = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.user_id == tx.user_id).first()
    entitlement = purchase_entitlement(db, tx.reference)
    lic = None
    if entitlement is not None and entitlement.licence_id:
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.id == entitlement.licence_id).first()
    if lic is None:
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.user_id == tx.user_id).first()
    balance = _credit_grant_for(db, tx)
    snapshot = _tx_package(tx, plan) if plan is not None else {}
    state = fulfilment_state(db, tx)
    credit_status = credit_service.status(db, tx.user_id) if user else None
    details = dict(tx.payment_details or {}) if isinstance(tx.payment_details, dict) else {}
    notifications = details.get("notifications") if isinstance(
        details.get("notifications"), dict) else {}
    kind = (entitlement.kind if entitlement is not None else
            snapshot.get("package_kind") or "")
    expires_at = entitlement.expires_at if entitlement is not None else None
    if kind == "flexible":
        expires_at = None
    granted = int(balance.credits_granted) if balance is not None else 0
    remaining = int(balance.credits_remaining) if balance is not None else 0
    entitlement_status = (entitlement.status if entitlement is not None else
                          ("active" if state == "activated" else state))
    return {
        "reference": tx.reference,
        "payment_status": (
            "success" if (tx.status == "success"
                          or (tx.status == "pending"
                              and str(tx.charge_status or "").lower() == "success"))
            else "failed" if tx.status in ("failed", "expired")
            else "reversed" if tx.status in ("reversed", "refunded")
            else "pending"),
        "fulfilment_status": state,
        "package": {
            "slug": snapshot.get("slug") or (plan.slug if plan else ""),
            "name": snapshot.get("name") or (plan.name if plan else ""),
            "credits": int(snapshot.get("credits") or 0)
            if snapshot else (_plan_credit_allowance(plan) if plan else 0),
            "kind": kind,
        },
        "amount_pesewas": int(tx.amount_pesewas or 0),
        "currency": tx.currency or "GHS",
        "paid_at": tx.paid_at.isoformat() if tx.paid_at else None,
        "channel": tx.channel or "",
        "payment_method": tx.payment_method or "",
        "provider": tx.provider or "",
        "credits_granted": granted,
        "credits_used": max(granted - remaining, 0),
        "credits_remaining": remaining,
        "entitlement_status": entitlement_status,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "credit_balance": credit_status,
        "licence": _licence_public(lic),
        "subscription": {
            "status": sub.status if sub else None,
            "paid_through": sub.paid_through.isoformat() if sub and sub.paid_through else None,
        },
        "notifications": {
            "customer": notifications.get("customer"),
            "owner": notifications.get("owner"),
        },
        "next_action": (
            "Your package is active. No further action is needed."
            if state == "activated" else
            "Your payment was received. SchemeKnit is completing activation; "
            "refresh this page shortly or contact support with the reference."
            if state == "needs_attention" else
            "Approve the payment on your phone, then refresh this page."
            if state == "payment_pending" else
            "This payment did not complete. No credits were issued."
        ),
    }


def _licence_public(lic: Optional[UserLicenseDB]) -> Optional[dict]:
    if lic is None:
        return None
    return {
        "key": lic.licence_key,
        "status": lic.status,
        "issued_at": lic.issued_at.isoformat() if lic.issued_at else None,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "plan_id": lic.plan_id,
    }


def notify_purchase(db: Session, tx: SubscriptionTransactionDB,
                    user: User, plan: SubscriptionPlanDB,
                    sub: Optional[UserSubscriptionDB],
                    lic: Optional[UserLicenseDB]) -> None:
    """Best-effort, idempotent customer + owner notifications."""
    try:
        from . import purchase_notifications
        purchase_notifications.notify_purchase(
            db, tx, user, plan, sub, lic)
    except Exception:
        # Notification delivery must never undo a paid, activated purchase.
        try:
            db.rollback()
        except Exception:
            pass


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
        # Idempotent REPAIR path. A payment must never stay activated in
        # Paystack while the local licence or credit grant is missing. The
        # old code returned here unconditionally, so a partial/legacy state
        # could never heal on a later webhook or verification call.
        plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.id == tx.plan_id).first()
        user = db.query(User).filter(User.id == tx.user_id).first()
        sub = (db.query(UserSubscriptionDB)
               .filter(UserSubscriptionDB.user_id == tx.user_id).first())
        lic = (db.query(UserLicenseDB)
               .filter(UserLicenseDB.user_id == tx.user_id).first())
        if plan is None or user is None:
            raise PaystackError("The local payment record is incomplete.", 500)
        already_fulfilled = fulfilment_state(db, tx) == "activated"
        if already_fulfilled:
            # Legacy success records may predate the independent entitlement
            # table. Backfill it idempotently so future expiry checks and the
            # dashboard are transaction-scoped, without touching credits.
            if purchase_entitlement(db, tx.reference) is None:
                snapshot = _tx_package(tx, plan)
                _record_purchase_entitlement(
                    db, tx, plan, user, sub, lic,
                    tx.paid_at or datetime.utcnow(), snapshot)
                db.commit()
                db.refresh(sub)
                if lic is not None:
                    db.refresh(lic)
            notify_purchase(db, tx, user, plan, sub, lic)
            return sub, lic
        try:
            repaired = _repair_fulfilment(db, tx, plan, user, sub, lic)
        except Exception:
            # Keep the successful payment visible and notify honestly, then
            # let the caller report the activation problem.
            notify_purchase(db, tx, user, plan, sub, lic)
            raise
        if repaired:
            db.commit()
            db.refresh(sub)
            lic = (db.query(UserLicenseDB)
                   .filter(UserLicenseDB.user_id == tx.user_id).first())
            if lic is not None:
                db.refresh(lic)
        notify_purchase(db, tx, user, plan, sub, lic)
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

    snapshot = _tx_package(tx, plan)
    kind = snapshot.get("package_kind") or "timed"
    is_timed = kind == "timed"
    if is_timed:
        base = sub.paid_through or paid_at
        if base < paid_at:
            base = paid_at
        paid_through = base + timedelta(days=int(
            snapshot.get("duration_days") or plan.duration_days or 0))
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
    licence_expiry = paid_through if is_timed else None
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
        if is_timed:
            lic.expires_at = licence_expiry
        elif lic.expires_at is None or lic.expires_at < datetime.utcnow():
            # A flexible pack has no period; an old timed expiry must not
            # mark the newly bought pack as expired.
            lic.expires_at = None

    _update_entitlement(db, user.id, plan, paid_through, is_timed=is_timed)
    _record_purchase_entitlement(
        db, tx, plan, user, sub, lic, paid_at, snapshot)
    tx.status = "success"
    tx.provider_transaction_id = str(payload.get("id") or "")
    tx.channel = str(payload.get("channel") or "")
    tx.paid_at = paid_at
    tx.subscription_id = sub.id
    tx.payment_method = sub.payment_method
    tx.provider = sub.provider
    _event(db, sub, "payment_success", old_status, "active",
           {"reference": tx.reference, "amount": tx.amount_pesewas})

    # Exactly once per verified transaction (unique grant key). The balance is
    # REQUIRED: a licence without the purchased credits is a failed fulfilment,
    # not a success. `grant_package` is idempotent, so a retry returns the
    # existing bucket instead of adding again.
    from . import credits
    balance = credits.grant_package(
        db, user.id, plan, tx.reference, activated_at=paid_at, commit=False,
        credits_override=int(snapshot.get("credits") or 0),
        kind_override=kind,
        days_override=snapshot.get("duration_days"),
        label_override=snapshot.get("name"),
        slug_override=snapshot.get("slug"),
    )
    expected_credits = int(snapshot.get("credits") or 0)
    if expected_credits > 0 and balance is None:
        raise PaystackError(
            "The package credit grant could not be created.", 500)
    tx.payment_details = _with_fulfilment_state(
        tx.payment_details,
        state="activated",
        plan_credits=expected_credits,
        licence_id=lic.id,
        credit_grant_key=(balance.grant_key if balance is not None else ""),
        activated_at=paid_at.isoformat(),
    )
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
    notify_purchase(db, tx, user, plan, sub, lic)
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
        payload_json=data,
        status="received",
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
            # Never mark an unmatched successful payment "processed": that
            # silently loses the only delivery. The durable event row stays
            # failed/retryable and the reference is visible to support.
            raise PaystackError("Unknown local purchase for this reference.", 404)
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
    """Expire ONLY genuinely time-limited entitlements.

    A flexible credit pack never expires here, unspent credits are never
    deleted, and expiring one timed package never revokes an unrelated
    purchase. The shared licence/entitlement mirror is only marked expired
    when the teacher has no remaining live purchased entitlement.
    """
    now = datetime.utcnow()
    changed = 0

    # 1. Time-limited purchased entitlements have their own lifecycle.
    try:
        timed = (db.query(PurchaseEntitlementDB)
                 .filter(PurchaseEntitlementDB.kind == "timed",
                         PurchaseEntitlementDB.status == "active",
                         PurchaseEntitlementDB.expires_at.isnot(None),
                         PurchaseEntitlementDB.expires_at < now)
                 .all())
    except (ProgrammingError, OperationalError):
        db.rollback()
        timed = []
    for ent in timed:
        ent.status = "expired"
        ent.updated_at = now
        changed += 1

    # 2. Legacy/periodic subscription rows.
    rows = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.status.in_(("active", "past_due", "non_renewing")),
        UserSubscriptionDB.paid_through.isnot(None),
        UserSubscriptionDB.paid_through < now,
    ).all()
    for sub in rows:
        grace = sub.grace_until or sub.paid_through
        if grace and grace >= now:
            continue
        old = sub.status
        sub.status = "expired"
        changed += 1

        # A live flexible pack (or another in-date purchased entitlement)
        # means this expiry must not revoke account access or the licence.
        if active_purchase_entitlements(db, sub.user_id, now):
            ent = db.query(EntitlementDB).filter(
                EntitlementDB.user_id == sub.user_id).first()
            if ent and ent.source == "paystack":
                ent.status = "active"
                if ent.expires_at and ent.expires_at < now:
                    ent.expires_at = None
            lic = db.query(UserLicenseDB).filter(
                UserLicenseDB.user_id == sub.user_id).first()
            if lic and has_live_flexible_entitlement(db, sub.user_id):
                lic.status = "active"
                if lic.expires_at and lic.expires_at < now:
                    lic.expires_at = None
            _event(db, sub, "expired", old, "expired",
                   {"other_entitlement_active": True})
            continue

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

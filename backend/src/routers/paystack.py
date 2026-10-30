"""Prepaid Paystack endpoints: Ghana Bank Transfer and Mobile Money only.

No card checkout is offered. Every reference is generated server-side, every
amount is resolved from the package catalogue in the database, and a package
activates only from a verified Paystack transaction or webhook.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from ..auth import get_current_user
from ..config import get_settings
from ..database import (
    get_db, PaystackWebhookEventDB, SubscriptionPlanDB,
    SubscriptionTransactionDB, User, UserLicenseDB, UserSubscriptionDB,
)
from .. import credits, paystack, webhook_sweeper
from ..logging_config import log_event, log_error

router = APIRouter()


class MomoChargeRequest(BaseModel):
    plan_slug: str
    phone: str
    provider: str


class BankTransferRequest(BaseModel):
    plan_slug: str


def _callback_url(request: Request) -> str:
    settings = get_settings()
    base = (getattr(settings, "PUBLIC_WEB_URL", "") or "").strip().rstrip("/")
    if not base:
        origin = request.headers.get("origin") or ""
        base = origin.rstrip("/")
    return f"{base}/payments/callback"


def _plan_payload(plan: SubscriptionPlanDB) -> dict:
    kind = getattr(plan, "package_kind", "") or "timed"
    validity = getattr(plan, "credit_validity_days", None)
    return {
        "slug": plan.slug,
        "name": plan.name,
        "description": plan.description,
        "price_pesewas": int(plan.price_pesewas),
        "price_ghs": int(plan.price_pesewas) / 100,
        "currency": plan.currency,
        "interval": plan.interval,
        "duration_days": plan.duration_days,
        "credits": int(getattr(plan, "credit_allowance", 0) or 0),
        "credit_validity_days": validity,
        "package_kind": kind,
        "validity_label": (
            "Credits do not expire" if kind == "flexible"
            else f"{plan.duration_days} days" if plan.duration_days
            else "Monthly"
        ),
        "payment_terms": getattr(plan, "payment_terms", "")
        or "One-time prepaid payment. No automatic renewal.",
        "features": plan.features or [],
        "active": bool(plan.active),
    }


def _free_payload() -> dict:
    from ..catalogue import FREE
    return {
        "slug": FREE.slug,
        "name": FREE.name,
        "description": FREE.description,
        "price_pesewas": 0,
        "price_ghs": 0,
        "currency": "GHS",
        "interval": "free",
        "duration_days": 0,
        "credits": FREE.credits,
        "credit_validity_days": None,
        "package_kind": "free",
        "validity_label": "2 per calendar month",
        "payment_terms": FREE.payment_terms,
        "features": list(FREE.features),
        "active": False,
        "free": True,
    }


def _get_plan(db: Session, slug: str) -> SubscriptionPlanDB:
    plan = (db.query(SubscriptionPlanDB)
            .filter(SubscriptionPlanDB.slug == slug,
                    SubscriptionPlanDB.active.is_(True)).first())
    if plan is None:
        raise HTTPException(status_code=404, detail="Package not found or not available.")
    return plan


def _new_tx(db: Session, user: User, plan: SubscriptionPlanDB,
            method: str, provider: str = "") -> SubscriptionTransactionDB:
    env = paystack.environment()
    prefix = "TFB" if method == "bank_transfer" else "TFM"
    reference = f"{prefix}-{user.id[:8]}-{secrets.token_hex(10)}"
    tx = SubscriptionTransactionDB(
        reference=reference, user_id=user.id, plan_id=plan.id,
        environment=env, amount_pesewas=int(plan.price_pesewas),
        currency="GHS", status="pending", payment_method=method,
        provider=provider,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _charge_payload(tx: SubscriptionTransactionDB, data: dict) -> dict:
    state = str(data.get("status") or "").lower()
    tx.charge_status = state
    tx.instructions = str(data.get("display_text") or "")
    bank = data.get("bank") if isinstance(data.get("bank"), dict) else {}
    expires = data.get("account_expires_at")
    details = dict(tx.payment_details or {}) if isinstance(tx.payment_details, dict) else {}
    details.update({
        "display_text": tx.instructions,
        "account_name": data.get("account_name") or details.get("account_name", ""),
        "account_number": data.get("account_number") or details.get("account_number", ""),
        "bank_name": bank.get("name") or data.get("bank_name") or details.get("bank_name", ""),
        "bank_slug": bank.get("slug") or details.get("bank_slug", ""),
        "transaction_reference": data.get("transaction_reference")
        or details.get("transaction_reference", ""),
    })
    if expires:
        details["account_expires_at"] = expires
    tx.payment_details = details
    return {
        "reference": tx.reference,
        "status": tx.status,
        "charge_status": state,
        "display_text": tx.instructions,
        "payment_details": tx.payment_details,
        "payment_method": tx.payment_method,
        "billing_mode": "prepaid",
    }


def _settle_if_success(db: Session, tx: SubscriptionTransactionDB, data: dict) -> None:
    state = str(data.get("status") or "").lower()
    if state == "success":
        verified = paystack.verify(tx.reference)
        user = db.query(User).filter(User.id == tx.user_id).first()
        paystack._validate_verified_payment(tx, verified, user)
        paystack.activate_paid_transaction(db, tx, verified)
    elif state in ("failed", "timeout", "reversed"):
        tx.status = "failed"
        db.commit()


def _expire_if_needed(db: Session, tx: SubscriptionTransactionDB) -> None:
    if tx.status != "pending":
        return
    details = tx.payment_details or {}
    raw = details.get("account_expires_at") if isinstance(details, dict) else None
    at = None
    if raw:
        try:
            at = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            at = None
    # Mobile Money authorisation has a 180-second provider window. Keep a
    # small grace (5 minutes) before the UI reports the session expired; a
    # genuinely delayed success webhook can still activate the package.
    if at is None and tx.payment_method == "mobile_money" and tx.created_at:
        at = tx.created_at + timedelta(minutes=5)
    if at is not None and at < datetime.utcnow():
        tx.status = "expired"
        db.commit()


@router.get("/config-status")
async def config_status():
    try:
        env = paystack.environment()
    except paystack.PaystackError as exc:
        return {
            "configured": False,
            "environment": None,
            "mode": (paystack._configured_mode() or "test"),
            "enabled": paystack._paid_enabled(),
            "currency": "GHS",
            "payment_methods": ["bank_transfer", "mobile_money"],
            "reason": exc.message,
        }
    return {"configured": True, "environment": env, "mode": env,
            "enabled": True, "currency": "GHS",
            "payment_methods": ["bank_transfer", "mobile_money"]}


@router.get("/plans")
async def list_plans(db: Session = Depends(get_db)):
    plans = (db.query(SubscriptionPlanDB)
             .filter(SubscriptionPlanDB.active.is_(True))
             .order_by(SubscriptionPlanDB.display_order,
                       SubscriptionPlanDB.price_pesewas).all())
    return {"plans": [_plan_payload(p) for p in plans]}


@router.get("/catalogue")
async def catalogue_page(db: Session = Depends(get_db)):
    """Public pricing catalogue: Free plus the four purchasable packages."""
    plans = (db.query(SubscriptionPlanDB)
             .filter(SubscriptionPlanDB.active.is_(True))
             .order_by(SubscriptionPlanDB.display_order,
                       SubscriptionPlanDB.price_pesewas).all())
    return {"plans": [_free_payload()] + [_plan_payload(p) for p in plans],
            "currency": "GHS",
            "payment_methods": ["bank_transfer", "mobile_money"]}


@router.post("/initialize")
async def initialize_payment(user: User = Depends(get_current_user)):
    """Retired card checkout. Refused before any provider call."""
    raise HTTPException(
        status_code=410,
        detail=("Card checkout is no longer available. Please pay by Bank "
                "Transfer or Mobile Money. No payment was taken."),
    )


@router.post("/bank-transfer/charge")
async def bank_transfer_charge(
    req: BankTransferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_plan(db, req.plan_slug)
    try:
        paystack.environment()
    except paystack.PaystackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    tx = _new_tx(db, user, plan, "bank_transfer")
    tx.payment_details = {
        "account_expires_at": (datetime.utcnow() + timedelta(hours=8))
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")
    }
    db.commit()
    try:
        data = paystack.charge_bank_transfer(plan, user, tx.reference)
    except paystack.PaystackError as exc:
        tx.status = "failed"
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    body = _charge_payload(tx, data)
    state = str(data.get("status") or "").lower()
    if state in ("failed", "timeout"):
        tx.status = "failed"
    db.commit()
    _settle_if_success(db, tx, data)
    body.update({"plan": _plan_payload(plan),
                 "status": tx.status,
                 "email": user.email, "currency": "GHS"})
    log_event("paystack_bank_transfer_started", user_id=user.id,
              plan_id=plan.id, reference=tx.reference)
    return body


@router.post("/momo/charge")
async def momo_charge(
    req: MomoChargeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-time Ghana Mobile Money charge (no recurring authorisation)."""
    plan = _get_plan(db, req.plan_slug)
    try:
        code, _phone = paystack.normalize_momo(req.provider, req.phone)
        paystack.environment()
    except paystack.PaystackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    tx = _new_tx(db, user, plan, "mobile_money", code)
    try:
        data = paystack.charge_mobile_money(
            plan, user, tx.reference, req.provider, req.phone)
    except paystack.PaystackError as exc:
        tx.status = "failed"
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    body = _charge_payload(tx, data)
    state = str(data.get("status") or "").lower()
    if state in ("failed", "timeout"):
        tx.status = "failed"
    db.commit()
    _settle_if_success(db, tx, data)
    body.update({"plan": _plan_payload(plan),
                 "status": tx.status,
                 "provider": code,
                 "email": user.email, "currency": "GHS",
                 "awaiting_authorisation": tx.status == "pending"})
    log_event("paystack_momo_charge_started", user_id=user.id,
              plan_id=plan.id, reference=tx.reference, provider=code)
    return body


@router.get("/charge/status/{reference}")
async def charge_status(
    reference: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = (db.query(SubscriptionTransactionDB)
          .filter(SubscriptionTransactionDB.reference == reference,
                  SubscriptionTransactionDB.user_id == user.id).first())
    if tx is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if tx.status == "pending":
        try:
            data = paystack.check_charge(reference)
            _charge_payload(tx, data)
            db.commit()
            _settle_if_success(db, tx, data)
        except paystack.PaystackError:
            _expire_if_needed(db, tx)
        else:
            _expire_if_needed(db, tx)
    sub = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.user_id == user.id).first()
    lic = db.query(UserLicenseDB).filter(
        UserLicenseDB.user_id == user.id).first()
    plan = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.id == tx.plan_id).first()
    return {
        "reference": tx.reference,
        "status": tx.status,
        "charge_status": tx.charge_status,
        "display_text": tx.instructions or "",
        "payment_details": tx.payment_details or {},
        "payment_method": tx.payment_method,
        "plan": _plan_payload(plan) if plan else None,
        "subscription": _sub_payload(sub),
        "licence": _licence_payload(lic) if tx.status == "success" else None,
        "credits": credits.status(db, user.id),
    }


@router.get("/momo/status/{reference}")
async def momo_status(
    reference: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Backward-compatible alias for the general charge status route."""
    return await charge_status(reference, user, db)


@router.get("/credits")
async def my_credits(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return credits.status(db, user.id)


@router.get("/verify/{reference}")
async def verify_payment(
    reference: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = (db.query(SubscriptionTransactionDB)
          .filter(SubscriptionTransactionDB.reference == reference,
                  SubscriptionTransactionDB.user_id == user.id).first())
    if tx is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if tx.status == "success":
        sub = db.query(UserSubscriptionDB).filter(
            UserSubscriptionDB.user_id == user.id).first()
        lic = db.query(UserLicenseDB).filter(
            UserLicenseDB.user_id == user.id).first()
        return {"status": "success", "reference": reference,
                "subscription": _sub_payload(sub), "licence": _licence_payload(lic),
                "credits": credits.status(db, user.id)}
    if tx.status in ("reversed", "refunded"):
        raise HTTPException(
            status_code=409,
            detail="This payment was reversed. It cannot activate a package again.",
        )

    try:
        data = paystack.verify(reference)
    except paystack.PaystackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    state = str(data.get("status") or "").lower()
    if state != "success":
        tx.status = "failed" if state in ("failed", "reversed") else "pending"
        tx.charge_status = state
        db.commit()
        raise HTTPException(
            status_code=402,
            detail="Payment has not been confirmed yet. No package was activated.",
        )

    try:
        paystack._validate_verified_payment(tx, data, user)
        sub, licence = paystack.activate_paid_transaction(db, tx, data)
    except paystack.PaystackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    log_event("paystack_payment_verified", user_id=user.id,
              reference=reference)
    return {"status": "success", "reference": reference,
            "subscription": _sub_payload(sub),
            "licence": _licence_payload(licence),
            "credits": credits.status(db, user.id)}


def _sub_payload(sub: Optional[UserSubscriptionDB]) -> Optional[dict]:
    if sub is None:
        return None
    return {
        "id": sub.id, "status": sub.status, "plan_id": sub.plan_id,
        "paid_through": sub.paid_through.isoformat() if sub.paid_through else None,
        "current_period_start": (sub.current_period_start.isoformat()
                                 if sub.current_period_start else None),
        "current_period_end": (sub.current_period_end.isoformat()
                               if sub.current_period_end else None),
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
        "environment": sub.environment,
        "billing_mode": sub.billing_mode or "prepaid",
        "payment_method": sub.payment_method or "bank_transfer",
        "provider": sub.provider or "",
    }


def _licence_payload(lic: Optional[UserLicenseDB]) -> Optional[dict]:
    if lic is None:
        return None
    return {
        "key": lic.licence_key, "status": lic.status,
        "issued_at": lic.issued_at.isoformat() if lic.issued_at else None,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "plan_id": lic.plan_id,
    }


@router.get("/me")
async def my_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    paystack.expire_overdue(db)
    sub = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.user_id == user.id).first()
    lic = db.query(UserLicenseDB).filter(
        UserLicenseDB.user_id == user.id).first()
    plan = None
    if sub is not None:
        plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.id == sub.plan_id).first()
    history = (db.query(SubscriptionTransactionDB)
               .filter(SubscriptionTransactionDB.user_id == user.id)
               .order_by(SubscriptionTransactionDB.created_at.desc())
               .limit(50).all())
    pending = next((t for t in history if t.status == "pending"), None)
    if pending is not None:
        _expire_if_needed(db, pending)
        if pending.status != "pending":
            pending = None
    pending_plan = None
    if pending is not None:
        pending_plan = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.id == pending.plan_id).first()
    return {
        "subscription": _sub_payload(sub),
        "plan": _plan_payload(plan) if plan else None,
        "licence": _licence_payload(lic),
        "credits": credits.status(db, user.id),
        "pending_payment": ({
            "reference": pending.reference,
            "status": pending.status,
            "charge_status": pending.charge_status,
            "display_text": pending.instructions or "",
            "payment_details": pending.payment_details or {},
            "payment_method": pending.payment_method,
            "plan": _plan_payload(pending_plan) if pending_plan else None,
            "created_at": pending.created_at.isoformat() if pending.created_at else None,
        } if pending is not None else None),
        "payments": [
            {"reference": t.reference, "status": t.status,
             "amount_pesewas": t.amount_pesewas,
             "currency": t.currency,
             "payment_method": t.payment_method,
             "plan_id": t.plan_id,
             "created_at": t.created_at.isoformat() if t.created_at else None,
             "paid_at": t.paid_at.isoformat() if t.paid_at else None}
            for t in history
        ],
    }


@router.post("/cancel")
async def cancel(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(UserSubscriptionDB).filter(
        UserSubscriptionDB.user_id == user.id).first()
    if sub is None:
        raise HTTPException(status_code=404, detail="No subscription found")
    if (sub.billing_mode or "prepaid") == "prepaid":
        raise HTTPException(
            status_code=400,
            detail="Prepaid packages do not renew automatically; there is nothing to cancel.",
        )
    try:
        paystack.cancel_subscription(db, sub)
    except paystack.PaystackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"status": sub.status, "cancel_at_period_end": True,
            "paid_through": sub.paid_through.isoformat() if sub.paid_through else None}


def _process_webhook_event(bind, event_id: str, event: str, data: dict) -> None:
    """Process one recorded event in its own session, after the HTTP ack.

    Delegates to the durable recovery path so the webhook worker and the
    sweeper share exactly one idempotent processing implementation.
    """
    session = sessionmaker(bind=bind)()
    try:
        webhook_sweeper.process_event(
            session, event_id, worker_id="webhook-background",
            fallback_data=data,
        )
    finally:
        session.close()


@router.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    if not paystack.verify_signature(raw, signature):
        log_event("paystack_webhook_rejected", reason="invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        body = json.loads(raw.decode("utf-8"))
        event = str(body.get("event") or "")
        data = body.get("data") or {}
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed event")

    row, fresh = paystack.record_webhook(db, event, data, raw)
    bind = db.get_bind()
    if not fresh:
        # A previous attempt that failed (or a process that died after the ack
        # and left a stale "received" row) is retried; a successfully processed
        # or in-flight duplicate is acknowledged without side effects.
        stale = bool(
            row is not None and row.status == "received" and row.received_at
            and row.received_at < datetime.utcnow() - timedelta(minutes=5)
        )
        if row is not None and (row.status == "failed" or stale):
            background.add_task(_process_webhook_event, bind, row.id, event, data)
            return {"received": True, "retried": True}
        return {"received": True, "duplicate": True}

    # Acknowledge promptly; HMac validation and event recording are already
    # durable. Verification/activation happens immediately after the response.
    background.add_task(_process_webhook_event, bind, row.id, event, data)
    log_event("paystack_webhook_received", event_type=event,
              reference=str(data.get("reference") or ""), event_id=row.id)
    return {"received": True}

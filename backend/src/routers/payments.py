"""
SchemeKnit Payment Router

Handles payment submission, history, admin review,
product plans, and payment configuration.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import shutil

from ..database import get_db, User
from ..auth import get_current_user, require_admin, require_platform_admin
from ..models import (
    PaymentMethod, PaymentStatus, ProductType,
    PaymentConfig, ProductPlan,
)
from ..payment_service import payment_service
from ..logging_config import get_logger, log_event

router = APIRouter()
logger = get_logger()


# ── Request Models ────────────────────────────────────────────────────────────

class PaymentSubmitRequest(BaseModel):
    payment_method: str
    amount: float
    product_type: str
    product_id: str
    product_name: str = ""
    reference: str = ""
    payer_name: str
    payer_phone: str = ""
    notes: str = ""


class PaymentReviewRequest(BaseModel):
    notes: str = ""
    rejection_reason: str = ""


class PaymentConfigUpdateRequest(BaseModel):
    mtn_momo: Optional[dict] = None
    bank_transfer: Optional[dict] = None
    currency: str = "GHS"


# ── User Payment Endpoints ────────────────────────────────────────────────────

@router.get("/config")
async def get_payment_instructions():
    """Get current payment instructions (public)."""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        config = payment_service.get_payment_config(db)
        return {
            "mtn_momo": config.mtn_momo,
            "bank_transfer": config.bank_transfer,
            "currency": config.currency,
        }
    finally:
        db.close()


@router.post("/submit")
async def submit_payment(
    req: PaymentSubmitRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Submit a payment for manual verification."""
    payment = payment_service.create_payment(
        db=db,
        user_id=user.id,
        payment_method=req.payment_method,
        amount=req.amount,
        product_type=req.product_type,
        product_id=req.product_id,
        product_name=req.product_name,
        reference=req.reference,
        payer_name=req.payer_name,
        payer_phone=req.payer_phone,
        notes=req.notes,
    )

    log_event("payment_submitted",
              user_id=user.id, payment_id=payment.id,
              amount=req.amount, product_type=req.product_type)

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "message": "Payment submitted — awaiting verification.",
    }


@router.get("/history")
async def payment_history(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get current user's payment history."""
    payments = payment_service.get_user_payments(db, user.id)
    return {
        "payments": [
            {
                "id": p.id,
                "payment_method": p.payment_method,
                "amount": p.amount,
                "currency": p.currency,
                "product_type": p.product_type,
                "product_id": p.product_id,
                "product_name": p.product_name,
                "reference": p.reference,
                "payer_name": p.payer_name,
                "status": p.status,
                "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
                "rejection_reason": p.rejection_reason if p.status == "rejected" else "",
            }
            for p in payments
        ],
        "total": len(payments),
    }


# ── Product Plans ─────────────────────────────────────────────────────────────
# NOTE: declared BEFORE the /{payment_id} catch-all below so the literal
# /plans path is never shadowed by the path-parameter route (FastAPI matches
# routes in declaration order).

@router.get("/plans")
async def list_product_plans(db=Depends(get_db)):
    """List available product plans (public)."""
    plans = payment_service.get_product_plans(db)
    return {
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "product_type": p.product_type,
                "price": p.price,
                "currency": p.currency,
                "duration_days": p.duration_days,
                "features": p.features,
            }
            for p in plans
        ],
        "total": len(plans),
    }


@router.get("/{payment_id}")
async def get_payment(
    payment_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get a specific payment (own payments only)."""
    payment = payment_service.get_payment(db, payment_id, user.id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "id": payment.id,
        "payment_method": payment.payment_method,
        "amount": payment.amount,
        "currency": payment.currency,
        "product_type": payment.product_type,
        "product_name": payment.product_name,
        "reference": payment.reference,
        "payer_name": payment.payer_name,
        "payer_phone": payment.payer_phone,
        "status": payment.status,
        "submitted_at": payment.submitted_at.isoformat() if payment.submitted_at else None,
        "reviewed_at": payment.reviewed_at.isoformat() if payment.reviewed_at else None,
        "rejection_reason": payment.rejection_reason,
        "notes": payment.notes,
    }


@router.post("/{payment_id}/cancel")
async def cancel_payment(
    payment_id: str,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Cancel a pending payment."""
    try:
        payment = payment_service.cancel_payment(db, payment_id, user.id)
        return {"status": payment.status, "message": "Payment cancelled."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Admin Payment Review ──────────────────────────────────────────────────────

@router.get("/admin/pending")
async def admin_pending_payments(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """List all pending payments (admin only)."""
    payments = payment_service.get_pending_payments(db)
    return {
        "payments": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "payment_method": p.payment_method,
                "amount": p.amount,
                "currency": p.currency,
                "product_type": p.product_type,
                "product_id": p.product_id,
                "product_name": p.product_name,
                "reference": p.reference,
                "payer_name": p.payer_name,
                "payer_phone": p.payer_phone,
                "proof_path": p.proof_path,
                "notes": p.notes,
                "status": p.status,
                "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            }
            for p in payments
        ],
        "total": len(payments),
    }


@router.get("/admin/all")
async def admin_all_payments(
    status: Optional[str] = None,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """List all payments with optional status filter (admin only)."""
    payments = payment_service.get_all_payments(db, status)
    return {
        "payments": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "payment_method": p.payment_method,
                "amount": p.amount,
                "currency": p.currency,
                "product_type": p.product_type,
                "product_name": p.product_name,
                "reference": p.reference,
                "payer_name": p.payer_name,
                "status": p.status,
                "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            }
            for p in payments
        ],
        "total": len(payments),
    }


@router.post("/admin/{payment_id}/verify")
async def admin_verify_payment(
    payment_id: str,
    req: PaymentReviewRequest = PaymentReviewRequest(),
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Verify a pending payment (admin only)."""
    try:
        payment = payment_service.verify_payment(db, payment_id, user.id, req.notes)
        log_event("payment_verified",
                  admin_id=user.id, payment_id=payment_id,
                  amount=payment.amount)
        return {
            "status": payment.status,
            "message": "Payment verified. Entitlement activated.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/{payment_id}/reject")
async def admin_reject_payment(
    payment_id: str,
    req: PaymentReviewRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Reject a pending payment (admin only)."""
    if not req.rejection_reason:
        raise HTTPException(status_code=400, detail="Rejection reason required")
    try:
        payment = payment_service.reject_payment(db, payment_id, user.id, req.rejection_reason)
        log_event("payment_rejected",
                  admin_id=user.id, payment_id=payment_id,
                  reason=req.rejection_reason)
        return {
            "status": payment.status,
            "message": "Payment rejected.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/admin/audit")
async def admin_audit_logs(
    payment_id: Optional[str] = None,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Get payment audit logs (admin only)."""
    logs = payment_service.get_audit_logs(db, payment_id)
    return {
        "logs": [
            {
                "id": l.id,
                "payment_id": l.payment_id,
                "user_id": l.user_id,
                "action": l.action,
                "old_status": l.old_status,
                "new_status": l.new_status,
                "amount": l.amount,
                "performed_by": l.performed_by,
                "notes": l.notes,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            }
            for l in logs
        ],
        "total": len(logs),
    }


@router.get("/admin/revenue")
async def admin_revenue_stats(
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Get revenue statistics (admin only)."""
    return payment_service.get_revenue_stats(db)


@router.put("/admin/config")
async def admin_update_payment_config(
    req: PaymentConfigUpdateRequest,
    user: User = Depends(require_platform_admin),
    db=Depends(get_db),
):
    """Update payment configuration (admin only)."""
    config = payment_service.get_payment_config(db)
    if req.mtn_momo is not None:
        config.mtn_momo = req.mtn_momo
    if req.bank_transfer is not None:
        config.bank_transfer = req.bank_transfer
    config.currency = req.currency

    payment_service.update_payment_config(db, config)
    return {"message": "Payment configuration updated."}
